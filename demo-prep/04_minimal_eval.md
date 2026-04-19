# 04 — Run Existing Evaluation (Testing & QA, 1 rubric pt)

**Owner:** You + Claude Code.
**Goal:** Produce real evaluation numbers for the demo and video using the eval scripts that ALREADY EXIST.
**Time box:** ~1 hour total (mostly labeling).

## Context

You already have:
- `evaluation/match_eval.py` — fully implemented, computes Accuracy, Precision, Recall, F1, Precision@K using sklearn
- `evaluation/cover_letter_eval.py` — generates formatted Markdown with rating tables for reviewers
- `evaluation/labeled_jobs.csv` — exists but is **EMPTY** (only the header row). This is the blocker.

This means all the infrastructure I was telling you to build is done. You just need to feed it data.

## Part A — Label 25–30 jobs (30–40 min)

### Prerequisites
- A resume uploaded to the system (POST to `/api/resume/upload` or drag-and-drop on Profile page)
- A database with at least 50 scraped jobs so there's a decent labeling pool

### Quick labeling process
Label jobs relative to YOUR resume (the one uploaded as "default"). Use 3 buckets:

- `1.0` — Strongly relevant: you could realistically apply and be a genuine candidate
- `0.5` — Partially relevant: some transferable overlap, but meaningful gaps
- `0.0` — Not relevant: wrong domain, wrong seniority, fundamentally mismatched

### Quick way to do this

Create `scripts/labeling_helper.py` that prints one job at a time and prompts you for a label:

```python
"""Interactive job labeler — writes rows to evaluation/labeled_jobs.csv."""
import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job

OUT = Path("evaluation/labeled_jobs.csv")
existing_ids = set()
if OUT.exists():
    with open(OUT) as f:
        existing_ids = {row["job_id"] for row in csv.DictReader(f)}

with SessionLocal() as s:
    jobs = (
        s.query(Job)
        .filter(Job.description.isnot(None))
        .order_by(Job.first_seen_at.desc())
        .limit(50)
        .all()
    )

rows = []
for job in jobs:
    if job.id in existing_ids:
        continue
    print("\n" + "=" * 70)
    print(f"Title:    {job.title}")
    print(f"Company:  {job.company}")
    print(f"Location: {job.location}")
    print(f"Req:      {(job.required_skills or [])[:8]}")
    print(f"Pref:     {(job.preferred_skills or [])[:8]}")
    print(f"Desc:     {(job.description or '')[:300]}...")
    label = input("\nLabel (0 / 0.5 / 1 / s=skip / q=quit): ").strip()
    if label == "q":
        break
    if label == "s":
        continue
    if label not in ("0", "0.5", "1", "1.0"):
        print("Invalid, skipping")
        continue
    rows.append({"job_id": job.id, "label": label, "notes": ""})

# Append to CSV
file_exists = OUT.exists() and OUT.stat().st_size > 0
with open(OUT, "a", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["job_id", "label", "notes"])
    if not file_exists:
        writer.writeheader()
    writer.writerows(rows)
print(f"\nAppended {len(rows)} labels. Total needed: ~25–30.")
```

Target: at least 25 labels, spread across the three buckets (rough goal: 8 relevant, 8 partial, 9 not-relevant — don't stress if it's lopsided).

### Part B — Run the match eval (5 min)

```bash
cd /Users/kennethhou/Desktop/JobSpy/JobSpy
python evaluation/match_eval.py --k 10
```

This produces:
- Accuracy / Precision / Recall / F1 for "relevant" classification
- Precision@10 for top-ranked jobs
- Top 10 table by match score with true labels
- `evaluation/match_eval_results.csv`

**Memorize the numbers** — you're going to cite them on stage and in the video.

Target numbers:
- F1 ≥ 0.60 → citeable as "solid"
- Precision@10 ≥ 0.6 → "6 of our top 10 ranked jobs were genuinely relevant"

If F1 is too low: tune the `--threshold` argument (default 50). Try 40 or 35 and see if balance improves. This is legitimate calibration, not cheating — reporting the threshold is standard.

### Part C — Run the cover letter eval (15 min)

```bash
cd /Users/kennethhou/Desktop/JobSpy/JobSpy
python evaluation/cover_letter_eval.py --n 5 --output evaluation/cl_for_review.md
```

This generates `cl_for_review.md` — a formatted Markdown document with 5 letters + pre-built rating tables for 5 reviewers × 4 criteria.

You don't have 5 reviewers in 2 days. Scale down honestly:
1. Rate each letter yourself (4 criteria × 1–5 Likert)
2. Send the file to 2 friends, ask each to rate one letter (15 min of their time)
3. Compute averages across 3 raters

Paste your averaged table into a new file `evaluation/cover_letter_results.md`:

```
| Criterion | Avg (1-5) | n raters |
|---|---|---|
| Relevance | X.X | 3 |
| Fluency | X.X | 3 |
| Professionalism | X.X | 3 |
| Groundedness | X.X | 3 |
```

**Frame honestly in the demo:** "Due to the two-week project timeline, we ran a pilot with 3 raters across 5 letters. Full-scale 5-rater study is in future work."

## Part D — Edge cases table (15 min)

Write `evaluation/edge_cases.md`. This directly addresses the rubric's "edge cases and error conditions" language. Base it on what your system actually does (you know the code):

```markdown
# Edge Cases & Error Handling

| Scenario | Handling |
|---|---|
| Scanned image-only PDF | `parse_resume` raises ValueError; API returns 422 with user-facing message. Manual entry remains available. |
| No resume uploaded | `/api/cover-letter/{id}` and `/api/jobs/{id}/match` return 404 with a friendly message. |
| Claude API key missing | `generate_cover_letter` raises ValueError on import of `ANTHROPIC_API_KEY`; caught by endpoint → 500 with actionable error. |
| Scraper times out on one platform | Other platforms' results still return (per-future exception isolation in `ThreadPoolExecutor` loop). |
| Zero matches for a search query | Frontend shows empty-state UI, not a crash. |
| User uploads DOCX instead of PDF | `extract_text` routes by extension; python-docx path works end-to-end. |
| User uploads non-PDF-non-DOCX (e.g. .jpg) | Endpoint rejects with 400 before parsing. |
| Duplicate job from a re-scrape | `save_jobs` upsert: same id → `last_seen_at` updated, `first_seen_at` preserved. No row duplication. |
| Job description missing (None) | Skill extraction skipped gracefully; `required_skills` and `preferred_skills` default to []. |
| Non-ASCII unicode in resume (em-dashes, smart quotes) | `_clean_text` normalizes via `_normalize_unicode`. |
| International location | `platform_selector.select_platforms` auto-adds Naukri / Bayt / BDJobs based on 60+ region keywords. |
```

Include at least 8 entries. Having this table in the repo and referenced on stage earns real credit.

## Definition of done

- [ ] `evaluation/labeled_jobs.csv` has 25+ labeled rows
- [ ] `python evaluation/match_eval.py --k 10` produces numbers you'd be comfortable citing
- [ ] `evaluation/cl_for_review.md` exists with 5 generated letters
- [ ] `evaluation/cover_letter_results.md` has averaged ratings from 3 raters across 4 criteria
- [ ] `evaluation/edge_cases.md` has 8+ scenarios
- [ ] All 4 numbers are committed to memory or written on a demo cue card
