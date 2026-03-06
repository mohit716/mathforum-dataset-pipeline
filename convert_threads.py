# convert_threads.py
# Reads one thread per file inside ./problem_outputs/ named like: thread_1, thread_7, thread_935871, thread_935871.txt, etc.
# Creates ./out_jsonl/train.jsonl, ./out_jsonl/valid.jsonl, ./out_jsonl/test.jsonl
#
# Run (WSL or Linux):
#   cd /path/to/convert_threads
#   python3 convert_threads.py

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List

# ------------------ config ------------------
THREADS_DIR = Path("problem_outputs")  # <-- your thread_* files are here
OUT_DIR     = Path("out_jsonl")        # <-- output folder (separate from raw inputs)

KEEP_PII = False                 # False = redact student name/school
DEDUP_SUBMISSIONS = True         # True = skip duplicate student work within same thread

# ------------------ utils ------------------
def stable_split(key: str) -> str:
    """Deterministic 90/5/5 split so reruns produce same train/valid/test membership."""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % 100
    if h < 90:
        return "train"
    if h < 95:
        return "valid"
    return "test"

def thread_num(path: Path) -> int:
    """
    Extract numeric suffix from 'thread_123'. Used only for nicer ordering.
    Gaps (missing numbers) are totally fine.
    """
    m = re.search(r"thread_(\d+)", path.stem)
    return int(m.group(1)) if m else 10**18

def scrub_or_redact(value: str, keep: bool) -> str:
    return value.strip() if keep else "[REDACTED]"

def normalize_ws(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r\n", "\n")
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()

def short_hash(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]

def parse_rubric_line(text: str) -> Dict[str, int]:
    """
    Input example:
      "Strategy: 2; Interpretation: 1; Completeness: 2; Clarity: 1; Reflection: 1; Accuracy: 1"
    """
    out: Dict[str, int] = {}
    for k, v in re.findall(r"([A-Za-z ]+):\s*(-?\d+)", text):
        key = k.strip().lower().replace(" ", "_")
        out[key] = int(v)
    return out

# ------------------ parser ------------------
def parse_thread_blob(blob: str, keep_pii: bool) -> Dict[str, Any]:
    """
    Parses your plain-text thread format into structured dict:
      problem_statement, student{name,school}, service, submissions[]
    Each submission may include:
      submitted_on, short_answer, long_answer, responded_on, mentor_response, rubric
    """
    t = blob.replace("\r\n", "\n").strip()

    # Header fields
    problem = re.search(
        r"Problem statement:\s*(.*?)(?:\nStudent Name:|\nService:|\nStudent Submission|\Z)",
        t,
        re.S,
    )
    student_name = re.search(r"Student Name:\s*(.*)", t)
    school = re.search(r"School:\s*(.*)", t)
    service = re.search(r"Service:\s*(.*)", t)

    thread: Dict[str, Any] = {
        "problem_statement": normalize_ws(problem.group(1)) if problem else "",
        "student": {
            "name": scrub_or_redact(student_name.group(1), keep_pii) if student_name else "",
            "school": scrub_or_redact(school.group(1), keep_pii) if school else "",
        },
        "service": service.group(1).strip() if service else "",
        "submissions": [],
    }

    # Patterns for repeated blocks
    short_pat = re.compile(
        r"Student Submission\s*\(submitted on\s*(\d+)\)\s*Short Answer\s*(\d+):\s*(.*?)(?=\nStudent Submission|\nMentor Response|\nRubric|\Z)",
        re.S,
    )
    long_pat = re.compile(
        r"Student Submission\s*\(submitted on\s*(\d+)\)\s*Long Answer\s*(\d+):\s*(.*?)(?=\nStudent Submission|\nMentor Response|\nRubric|\Z)",
        re.S,
    )
    mentor_pat = re.compile(
        r"Mentor Response\s*\(responded on\s*(\d+)\)\s*(\d+):\s*(.*?)(?=\nStudent Submission|\nMentor Response|\nRubric|\Z)",
        re.S,
    )
    rubric_pat = re.compile(
        r"Rubric\s*(\d+):\s*(.*?)(?=\nStudent Submission|\nMentor Response|\nRubric|\Z)",
        re.S,
    )

    # Build submission records keyed by N
    by_n: Dict[int, Dict[str, Any]] = {}

    for ts, n, content in short_pat.findall(t):
        n_int = int(n)
        by_n.setdefault(n_int, {"n": n_int})
        by_n[n_int]["submitted_on"] = int(ts)
        by_n[n_int]["short_answer"] = normalize_ws(content)

    for ts, n, content in long_pat.findall(t):
        n_int = int(n)
        by_n.setdefault(n_int, {"n": n_int})
        by_n[n_int]["submitted_on"] = int(ts)
        by_n[n_int]["long_answer"] = normalize_ws(content)

    for ts, n, content in mentor_pat.findall(t):
        n_int = int(n)
        by_n.setdefault(n_int, {"n": n_int})
        by_n[n_int]["responded_on"] = int(ts)
        by_n[n_int]["mentor_response"] = normalize_ws(content)

    for n, content in rubric_pat.findall(t):
        n_int = int(n)
        by_n.setdefault(n_int, {"n": n_int})
        by_n[n_int]["rubric"] = parse_rubric_line(content)

    thread["submissions"] = [by_n[k] for k in sorted(by_n.keys())]
    return thread

# ------------------ example builder ------------------
def thread_to_examples(thread: Dict[str, Any], thread_id: str) -> List[Dict[str, Any]]:
    """
    Creates one JSONL training example per submission that has a mentor_response.
    Each example includes:
      - input: problem + that submission's student work
      - output: mentor_response
    """
    problem = thread.get("problem_statement", "").strip()
    service = thread.get("service", "").strip()

    system = (
        "You are a MathForum-style mentor. "
        "Give feedback on the student's reasoning, ask clarifying questions, "
        "and guide them toward a correct algebraic or pattern-based solution. "
        "Do not just give the final numeric answer."
    )

    examples: List[Dict[str, Any]] = []
    seen_submission_hashes = set()

    for s in thread.get("submissions", []):
        mentor = s.get("mentor_response")
        if not mentor:
            continue

        parts = []
        if s.get("short_answer"):
            parts.append(f"Short answer: {s['short_answer']}")
        if s.get("long_answer"):
            parts.append(f"Long answer: {s['long_answer']}")
        student_work = "\n".join(parts).strip()

        # Optionally skip duplicates within the same thread
        if DEDUP_SUBMISSIONS:
            sig = short_hash(problem + "\n" + student_work)
            if sig in seen_submission_hashes:
                continue
            seen_submission_hashes.add(sig)

        ex = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Service: {service}\n\nProblem:\n{problem}\n\nStudent work:\n{student_work}"},
                {"role": "assistant", "content": mentor},
            ],
            "metadata": {
                "thread_id": thread_id,
                "service": service,
                "submission_n": s.get("n"),
                "submitted_on": s.get("submitted_on"),
                "responded_on": s.get("responded_on"),
                "rubric": s.get("rubric", {}),
            },
        }
        examples.append(ex)

    return examples

# ------------------ main ------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    writers = {
        "train": open(OUT_DIR / "train.jsonl", "w", encoding="utf-8"),
        "valid": open(OUT_DIR / "valid.jsonl", "w", encoding="utf-8"),
        "test":  open(OUT_DIR / "test.jsonl", "w", encoding="utf-8"),
    }

    stats = {
        "threads_seen": 0,
        "threads_with_no_mentor_reply": 0,
        "examples_written": 0,
        "train": 0,
        "valid": 0,
        "test": 0,
        "files_not_matching_pattern": 0,
    }

    files = sorted(THREADS_DIR.glob("thread_*"), key=thread_num)

    for path in files:
        if not path.is_file():
            continue

        # If you have other files in the folder, keep only thread_* ones
        if not path.stem.startswith("thread_"):
            stats["files_not_matching_pattern"] += 1
            continue

        stats["threads_seen"] += 1
        blob = path.read_text(encoding="utf-8", errors="replace")
        thread_id = path.stem  # "thread_935871" (works with/without .txt)

        thread = parse_thread_blob(blob, keep_pii=KEEP_PII)
        examples = thread_to_examples(thread, thread_id=thread_id)

        if not examples:
            stats["threads_with_no_mentor_reply"] += 1
            continue

        bucket = stable_split(thread_id)
        for ex in examples:
            writers[bucket].write(json.dumps(ex, ensure_ascii=False) + "\n")
            stats[bucket] += 1
            stats["examples_written"] += 1

    for f in writers.values():
        f.close()

    print("DONE")
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()

