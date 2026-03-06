# clean_jsonl_v3.py
import json
import re
from pathlib import Path

IN_DIR = Path("out_jsonl")
FILES = ["train.jsonl", "valid.jsonl", "test.jsonl"]

def clean_quotes(text: str) -> str:
    if not text:
        return text

    s = text.replace("\r\n", "\n")

    # 1) Remove leading quote markers at the start of each line
    s = "\n".join(re.sub(r"^\s*(?:>\s*)+", "", line) for line in s.splitlines())

    # 2) Fix flattened quoting where " >X" appears mid-line -> newline
    s = re.sub(r"\s+(>{1,3})\s*(?=[A-Za-z0-9(])", "\n", s)

    # 3) REMOVE dangling '>' at end of line (your current issue)
    s = re.sub(r"(?m)\s*>\s*$", "", s)

    # 4) Remove lines that are only '>'
    s = re.sub(r"(?m)^\s*>\s*$", "", s)

    # 5) Collapse excessive blank lines
    s = re.sub(r"\n{3,}", "\n\n", s).strip()

    return s

def process_file(in_path: Path, out_path: Path) -> tuple[int, int]:
    lines_read = 0
    lines_written = 0

    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue

            lines_read += 1
            obj = json.loads(line)

            for m in obj.get("messages", []):
                if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                    m["content"] = clean_quotes(m["content"])

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            lines_written += 1

    return lines_read, lines_written

def main():
    IN_DIR.mkdir(exist_ok=True)
    for fname in FILES:
        in_path = IN_DIR / fname
        if not in_path.exists():
            print(f"SKIP (not found): {in_path}")
            continue

        out_path = IN_DIR / fname.replace(".jsonl", "_clean_v3.jsonl")
        r, w = process_file(in_path, out_path)
        print(f"{fname} -> {out_path.name} | read={r} wrote={w}")

    print("DONE")

if __name__ == "__main__":
    main()

