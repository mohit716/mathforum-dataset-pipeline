# MathForum Mentor Dataset Pipeline

This repo contains a local pipeline that converts raw MathForum-style mentoring threads into **chat-format JSONL** suitable for fine-tuning instruction/chat models (e.g., Llama Instruct).  
**No raw data or generated datasets are included in this repo.** All confidential files are excluded via `.gitignore`.

---

## What this project does

Given a folder of raw thread text files (one file per thread), the pipeline:

1. **Extracts training examples** in chat format:
   - `system`: fixed mentor persona prompt
   - `user`: problem + student work (short/long answer)
   - `assistant`: mentor feedback

2. **Cleans and filters** the dataset:
   - removes threads with no mentor reply / empty assistant
   - removes placeholder content (e.g., "Write your reply here")
   - removes embedded image/base64 blobs
   - removes rubric “Summary / scoring guide” text blocks from assistant output
   - removes “assistant echo” (mentor repeating student short answer at the start)
   - caps extreme lengths to avoid GPU memory issues
   - deduplicates across splits (train/valid/test)
   - supports rubric-based filtering (e.g., >=3, >=4, or avg/min thresholds)

3. Outputs JSONL train/valid/test splits locally for fine-tuning.

---

## Output format (Chat JSONL)

Each line is one JSON object:

```json
{
  "messages": [
    {"role": "system", "content": "You are a MathForum-style mentor..."},
    {"role": "user", "content": "Service: ...\n\nProblem:\n...\n\nStudent work:\nShort answer: ...\nLong answer: ..."},
    {"role": "assistant", "content": "Mentor feedback..."}
  ],
  "metadata": {
    "thread_id": "thread_123",
    "service": "Algebra",
    "rubric": {"accuracy": 3, "strategy": 3, "clarity": 3, "interpretation": 4, "completeness": 3}
  }
}
```

> Note: `metadata` is optional and can be ignored by training code; it’s useful for analysis and filtering.

---

## Toy examples of dataset:

 Below are **synthetic** examples that match the schema.

### Toy eg 1 — Algebra

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a MathForum-style mentor. Give feedback on the student's reasoning, ask clarifying questions, and guide them toward a correct algebraic or pattern-based solution. Do not just give the final numeric answer."
    },
    {
      "role": "user",
      "content": "Service: Algebra\n\nProblem:\nA school club sells stickers. Each sticker costs the same. Maya buys 3 stickers and a notebook for $11. The notebook costs $5. How much does one sticker cost?\n\nStudent work:\nShort answer: $2\nLong answer: I did 11 - 5 = 6. Then I divided 6 by 3 and got 2. So each sticker is $2."
    },
    {
      "role": "assistant",
      "content": "Nice work — your steps match the structure of the problem.\n\nYou correctly subtracted the notebook cost first: $11 - $5 = $6. That $6 is the total cost of the 3 stickers.\n\nThen dividing by 3 makes sense because the stickers all cost the same: $6 ÷ 3 = $2 per sticker.\n\nQuick check: 3 stickers at $2 each is $6, plus the $5 notebook gives $11, which matches the problem.\n\nOne question to make your explanation even clearer: can you write a simple equation for the total, like 3s + 5 = 11, and show how you solved for s?"
    }
  ],
  "metadata": {
    "thread_id": "toy_001",
    "service": "Algebra",
    "submission_n": 1,
    "submitted_on": 0,
    "responded_on": 0,
    "rubric": {
      "strategy": 4,
      "interpretation": 4,
      "completeness": 4,
      "clarity": 4,
      "reflection": 3,
      "accuracy": 4
    }
  }
}
```

### Toy eg 2 — Geometry

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a MathForum-style mentor. Give feedback on the student's reasoning, ask clarifying questions, and guide them toward a correct algebraic or pattern-based solution. Do not just give the final numeric answer."
    },
    {
      "role": "user",
      "content": "Service: Geometry\n\nProblem:\nA rectangle has perimeter 30 cm. Its length is 3 cm more than its width. Find the width and length.\n\nStudent work:\nShort answer: width = 6, length = 9\nLong answer: I used P = 2L + 2W. Since L = W + 3, I did 2(W+3) + 2W = 30. Then 2W+6+2W=30, so 4W=24 and W=6. Then L=W+3=9."
    },
    {
      "role": "assistant",
      "content": "This is a strong solution — you set up the perimeter equation correctly and used the relationship L = W + 3 in a clear way.\n\nYour steps: 2(W+3) + 2W = 30 → 4W + 6 = 30 → 4W = 24 → W = 6 are all correct, and then L = 9 follows.\n\nTo make it even more convincing, add a quick check at the end: does 2·9 + 2·6 = 30?\n\nOne small mentoring-style question: when you substitute L = W + 3 into 2L + 2W, can you explain in words what that substitution means (why it’s valid)?" 
    }
  ],
  "metadata": {
    "thread_id": "toy_002",
    "service": "Geometry",
    "submission_n": 1,
    "submitted_on": 0,
    "responded_on": 0,
    "rubric": {
      "strategy": 4,
      "interpretation": 4,
      "completeness": 4,
      "clarity": 4,
      "reflection": 4,
      "accuracy": 4
    }
  }
}
```

### Toy eg 3 — Math Fundamentals (Patterns)

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a MathForum-style mentor. Give feedback on the student's reasoning, ask clarifying questions, and guide them toward a correct algebraic or pattern-based solution. Do not just give the final numeric answer."
    },
    {
      "role": "user",
      "content": "Service: Math Fundamentals\n\nProblem:\nOne table seats 5 people. When tables are connected in a straight row, each connection removes 2 seats (the touching sides). How many people can sit at 5 connected tables? Write a rule for n tables.\n\nStudent work:\nShort answer: 5 tables = 17 people\nLong answer: I think it’s 5 + 4 + 4 + 4 + 0? I’m not sure. I noticed you lose seats when tables touch but I didn’t make an equation."
    },
    {
      "role": "assistant",
      "content": "Good observation: the key idea is that you *lose seats* each time two tables touch. Let’s turn that into a clean rule.\n\nStart with 1 table: 5 seats.\nWhen you add a 2nd table, you’d expect +5 more seats, but the connection removes 2 seats, so you only add +3.\nSo: 2 tables → 5 + 3 = 8 seats.\n3 tables → 8 + 3 = 11 seats.\n4 tables → 11 + 3 = 14 seats.\n5 tables → 14 + 3 = 17 seats. Your short answer (17) is correct.\n\nRule: for n tables, you start at 5 and add 3 for each additional table: 5 + 3(n-1) = 3n + 2.\n\nQuestion: can you explain (in one sentence) why the +3 happens each time instead of +5?"
    }
  ],
  "metadata": {
    "thread_id": "toy_003",
    "service": "Math Fundamentals",
    "submission_n": 1,
    "submitted_on": 0,
    "responded_on": 0,
    "rubric": {
      "strategy": 4,
      "interpretation": 4,
      "completeness": 4,
      "clarity": 4,
      "reflection": 3,
      "accuracy": 4
    }
  }
}
```

---

## Repo layout

- `convert_threads.py` — main converter (raw thread files → chat JSONL)
- `clean_jsonl.py` — optional post-clean step(s)
- `out_jsonl/` — local outputs (ignored by git)
- `problem_ou tputs/` — raw thread files (ignored by git)

---

## Running the pipeline (example)

> The raw dataset is confidential, so file paths are user-specific.

1. Put raw thread files into a local folder (e.g., `problem_outputs/`)
2. Run the converter:

```bash
python convert_threads.py
```

3. Run any desired cleaning / filtering scripts (examples):
- strip assistant echo
- drop empty assistant
- rubric-based filtering

---

## Confidentiality / data safety

This repo excludes:
- `problem_outputs/` (raw threads)
- all generated `.jsonl` datasets in `out_jsonl/`

See `.gitignore` for exact patterns.

---

## Typical fine-tuning usage

This dataset format is compatible with chat fine-tuning pipelines that use:
- `tokenizer.apply_chat_template()`
- completion-only loss masking (loss computed only on assistant tokens)
- LoRA/QLoRA (PEFT) for GPU-efficient training

Example base model used in experiments:
- `meta-llama/Meta-Llama-3.1-8B-Instruct` (gated on Hugging Face)

---

## Status

- Pipeline implemented and validated via sanity checks (JSON validity, role order, no empty assistant, dedup).
- Clean high-quality subsets can be produced via rubric thresholds (e.g., avg ≥ 3.5 and min ≥ 3).
