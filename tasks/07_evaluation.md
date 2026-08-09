# Phase 7 — Evaluation & Research Dataset
> Prerequisite: All Phases 0 through 6 must be complete.

## Context
The proposal specifies two evaluation dimensions (per Section 3.2):
1. **Job Matching Evaluation** — accuracy, precision, recall, F1-score, Precision@K for the match scorer
2. **Cover Letter Evaluation** — 5 human reviewers rate letters 1–5 Likert across relevance, fluency, professionalism, and groundedness

Additionally, the longitudinal research dataset (daily job collection with `first_seen_at`/`last_seen_at`) is already captured by the existing DB schema — this phase adds a daily scrape script and dataset export.

---

## Your Job in This Phase
1. Create `evaluation/match_eval.py` — automated match scorer evaluation
2. Create `evaluation/cover_letter_eval.py` — batch cover letter generation for human review
3. Create `evaluation/review_form.html` — simple browser-based human review form
4. Create `scripts/daily_scrape.py` — scheduled data collection script
5. Create `scripts/export_dataset.py` — export the longitudinal job dataset to CSV

---

## Step 1 — Read These Files First
- `jobspy/nlp/match_scorer.py` — the function you're evaluating
- `jobspy/database.py` — how to query jobs and resume profiles
- `jobspy/__init__.py` — the scrape_jobs() entry point for daily collection

---

## Step 2 — Create the Labeled Test Set

Before writing evaluation code, create a labeled dataset. Run a scrape for your target role (e.g., "Software Engineer") and manually label 30–50 jobs as:
- `1` = relevant (matches your background)
- `0.5` = partially relevant
- `0` = not relevant

Create `evaluation/labeled_jobs.csv` with this format:

```csv
job_id,label,notes
linkedin-1234567890,1,"Good Python/ML match"
indeed-abc123,0.5,"Right role but wrong seniority"
glassdoor-xyz789,0,"Frontend role, not backend"
```

Add at least 30 rows. You can export job IDs from the DB:
```bash
python -c "
from jobspy.database import SessionLocal, Job
with SessionLocal() as s:
    jobs = s.query(Job.id, Job.title, Job.company).limit(100).all()
    for j in jobs: print(j.id, '|', j.title, '|', j.company)
"
```

---

## Step 3 — Create `evaluation/match_eval.py`

```python
"""
match_eval.py
Evaluates the semantic match scorer against a manually labeled test set.
Computes: Accuracy, Precision, Recall, F1, Precision@K.

Usage:
    python evaluation/match_eval.py --resume-user default --k 10
"""

import argparse
import csv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from jobspy.database import SessionLocal, Job, get_resume_profile
from jobspy.nlp.match_scorer import compute_match_score


LABELED_FILE = Path(__file__).parent / "labeled_jobs.csv"


def load_labels(filepath: Path) -> dict[str, float]:
    """Load labeled jobs from CSV. Returns {job_id: label (0, 0.5, or 1.0)}."""
    labels = {}
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels[row["job_id"]] = float(row["label"])
    return labels


def get_job_features(job_id: str) -> dict | None:
    """Fetch job from DB and return required/preferred skills."""
    with SessionLocal() as session:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        return {
            "required_skills": job.required_skills or [],
            "preferred_skills": job.preferred_skills or [],
            "title": job.title,
            "company": job.company,
        }


def evaluate(resume_user: str = "default", k: int = 10, threshold: float = 50.0):
    """
    Run the full evaluation pipeline.

    Args:
        resume_user: user_id for the resume profile to evaluate against
        k: value of K for Precision@K
        threshold: match score cutoff to classify as "relevant" (default 50.0)
    """
    print(f"Loading resume profile for user: {resume_user}")
    resume = get_resume_profile(user_id=resume_user)
    if not resume:
        print("ERROR: No resume found. Upload a resume first (Phase 3).")
        sys.exit(1)

    resume_skills = resume.parsed_skills or []
    print(f"Resume skills ({len(resume_skills)}): {', '.join(resume_skills[:10])}...")

    print(f"\nLoading labels from: {LABELED_FILE}")
    if not LABELED_FILE.exists():
        print("ERROR: labeled_jobs.csv not found. Create it per Phase 7 instructions.")
        sys.exit(1)

    labels = load_labels(LABELED_FILE)
    print(f"Loaded {len(labels)} labeled jobs.")

    # Compute match scores
    results = []
    skipped = 0
    for job_id, true_label in labels.items():
        job = get_job_features(job_id)
        if not job:
            print(f"  WARNING: Job {job_id} not found in DB, skipping.")
            skipped += 1
            continue

        score = compute_match_score(
            resume_skills,
            job["required_skills"],
            job["preferred_skills"],
        )

        results.append({
            "job_id": job_id,
            "title": job["title"],
            "company": job["company"],
            "true_label": true_label,
            "match_score": score,
            "predicted_label": 1 if score >= threshold else 0,
            "true_binary": 1 if true_label >= 0.5 else 0,
        })

    print(f"Evaluated {len(results)} jobs (skipped {skipped} not found in DB).\n")

    if not results:
        print("No results to evaluate.")
        return

    # Binary classification metrics
    y_true = [r["true_binary"] for r in results]
    y_pred = [r["predicted_label"] for r in results]

    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    # Precision@K — top-K by match score, how many are truly relevant
    sorted_results = sorted(results, key=lambda r: r["match_score"], reverse=True)
    top_k = sorted_results[:k]
    precision_at_k = sum(1 for r in top_k if r["true_binary"] == 1) / k if k > 0 else 0

    # Print results
    print("=" * 50)
    print("MATCH SCORER EVALUATION RESULTS")
    print("=" * 50)
    print(f"Threshold:       {threshold}%")
    print(f"Total jobs:      {len(results)}")
    print(f"K:               {k}")
    print()
    print(f"Accuracy:        {acc:.3f}")
    print(f"Precision:       {prec:.3f}")
    print(f"Recall:          {rec:.3f}")
    print(f"F1 Score:        {f1:.3f}")
    print(f"Precision@{k}:    {precision_at_k:.3f}")
    print()

    print("Top 10 by Match Score:")
    print(f"{'Score':>7}  {'True':>6}  {'Title':<40}  Company")
    print("-" * 75)
    for r in sorted_results[:10]:
        label_str = "✓" if r["true_binary"] == 1 else "✗"
        print(f"{r['match_score']:>6.1f}%  {label_str:>6}  {r['title'][:40]:<40}  {r['company']}")

    # Save full results to CSV
    out_path = Path(__file__).parent / "match_eval_results.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"\nFull results saved to: {out_path}")

    return {"accuracy": acc, "precision": prec, "recall": rec, "f1": f1, f"precision_at_{k}": precision_at_k}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate job match scorer")
    parser.add_argument("--resume-user", default="default")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=50.0)
    args = parser.parse_args()
    evaluate(args.resume_user, args.k, args.threshold)
```

Run it:
```bash
python evaluation/match_eval.py --k 10 --threshold 50
```

---

## Step 4 — Create `evaluation/cover_letter_eval.py`

This script generates cover letters for a batch of jobs and exports them as a reviewable document.

```python
"""
cover_letter_eval.py
Generates cover letters for a batch of labeled jobs and exports them
to a file for human evaluation (5 reviewers, 1–5 Likert scale).

Usage:
    python evaluation/cover_letter_eval.py --n 10 --output evaluation/cl_for_review.md
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job, get_resume_profile
from jobspy.nlp.cover_letter import generate_cover_letter
from jobspy.nlp.match_scorer import compute_match_score


def generate_batch(n: int = 10, output_path: str = "evaluation/cl_for_review.md"):
    """
    Generate cover letters for the top N matching jobs and export for review.
    """
    print(f"Loading resume profile...")
    resume = get_resume_profile(user_id="default")
    if not resume:
        print("ERROR: No resume found.")
        sys.exit(1)

    resume_dict = {
        "name": resume.name,
        "summary": resume.summary,
        "parsed_skills": resume.parsed_skills or [],
        "experience_years": resume.experience_years,
    }

    print(f"Fetching top {n} jobs from DB...")
    with SessionLocal() as session:
        jobs = session.query(Job).filter(
            Job.description.isnot(None)
        ).limit(n * 3).all()  # fetch more, filter below

    # Sort by match score and take top N
    scored = []
    for job in jobs:
        score = compute_match_score(
            resume_dict["parsed_skills"],
            job.required_skills or [],
            job.preferred_skills or [],
        )
        scored.append((score, job))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_jobs = scored[:n]

    print(f"Generating {len(top_jobs)} cover letters...\n")

    output_lines = [
        f"# Cover Letter Human Evaluation",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Candidate: {resume.name}",
        f"",
        f"## Instructions for Reviewers",
        f"Rate each cover letter on a 1–5 Likert scale across 4 criteria:",
        f"- **Relevance** (1–5): How well does it address the specific job?",
        f"- **Fluency** (1–5): Is it well-written and grammatically correct?",
        f"- **Professionalism** (1–5): Does it have an appropriate professional tone?",
        f"- **Groundedness** (1–5): Does it accurately reflect the candidate's actual resume?",
        f"",
        f"---",
        f"",
    ]

    for i, (score, job) in enumerate(top_jobs, 1):
        print(f"  [{i}/{len(top_jobs)}] Generating for: {job.title} @ {job.company}...")
        try:
            job_dict = {
                "title": job.title,
                "company": job.company,
                "location": str(job.location) if job.location else "N/A",
                "description": job.description,
                "required_skills": job.required_skills or [],
                "preferred_skills": job.preferred_skills or [],
            }
            letter = generate_cover_letter(resume_dict, job_dict)

            output_lines += [
                f"## Cover Letter {i}: {job.title} @ {job.company}",
                f"**Job ID:** `{job.id}`",
                f"**Match Score:** {score:.1f}%",
                f"**Required Skills:** {', '.join(job.required_skills or ['none extracted'])}",
                f"**Candidate Skills (from resume):** {', '.join(resume_dict['parsed_skills'][:10])}",
                f"",
                f"### Generated Cover Letter",
                f"```",
                letter,
                f"```",
                f"",
                f"### Reviewer Ratings (fill in below)",
                f"| Criteria | Reviewer 1 | Reviewer 2 | Reviewer 3 | Reviewer 4 | Reviewer 5 | Average |",
                f"|----------|-----------|-----------|-----------|-----------|-----------|---------|",
                f"| Relevance (1–5) | | | | | | |",
                f"| Fluency (1–5) | | | | | | |",
                f"| Professionalism (1–5) | | | | | | |",
                f"| Groundedness (1–5) | | | | | | |",
                f"",
                f"**Notes:**",
                f"",
                f"---",
                f"",
            ]
        except Exception as e:
            print(f"    ERROR generating letter: {e}")
            output_lines.append(f"## Cover Letter {i}: GENERATION FAILED\nError: {e}\n\n---\n")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"\nReview document saved to: {output_file}")
    print("Share this file with your 5 reviewers to fill in the rating table.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate cover letters for human evaluation")
    parser.add_argument("--n", type=int, default=10, help="Number of cover letters to generate")
    parser.add_argument("--output", default="evaluation/cl_for_review.md")
    args = parser.parse_args()
    generate_batch(args.n, args.output)
```

Run it:
```bash
python evaluation/cover_letter_eval.py --n 10 --output evaluation/cl_for_review.md
```

---

## Step 5 — Create `scripts/daily_scrape.py`

Builds the longitudinal dataset. Run this script daily (via cron or task scheduler) to track how jobs appear and disappear over time.

```python
"""
daily_scrape.py
Runs a daily job scrape and logs results.
Designed to be called by a cron job or scheduler.

Usage:
    python scripts/daily_scrape.py --terms "Software Engineer" "Data Scientist" --location "United States"

Cron example (runs every day at 8am):
    0 8 * * * cd /path/to/JobSpy && python scripts/daily_scrape.py >> logs/daily_scrape.log 2>&1
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy import scrape_jobs
from jobspy.platform_selector import select_platforms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


DEFAULT_SEARCH_TERMS = [
    "Software Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
]

DEFAULT_LOCATION = "United States"


def run_daily_scrape(
    search_terms: list[str] = DEFAULT_SEARCH_TERMS,
    location: str = DEFAULT_LOCATION,
    results_per_term: int = 50,
):
    log.info(f"Daily scrape started — {datetime.now().isoformat()}")
    total_saved = 0

    for term in search_terms:
        log.info(f"Scraping: '{term}' in '{location}'")
        try:
            platforms = select_platforms(location)
            log.info(f"  Platforms: {platforms}")

            df = scrape_jobs(
                site_name=platforms,
                search_term=term,
                location=location,
                results_wanted=results_per_term,
                hours_old=26,      # slightly over 24h to avoid gaps
                description_format="markdown",
                verbose=0,
            )

            log.info(f"  Scraped {len(df)} jobs for '{term}'")
            total_saved += len(df)

        except Exception as e:
            log.error(f"  FAILED to scrape '{term}': {e}")

    log.info(f"Daily scrape complete. Total jobs saved/updated: {total_saved}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--terms", nargs="+", default=DEFAULT_SEARCH_TERMS)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--results", type=int, default=50)
    args = parser.parse_args()
    run_daily_scrape(args.terms, args.location, args.results)
```

Create the logs directory:
```bash
mkdir -p logs
echo "logs/" >> .gitignore
```

---

## Step 6 — Create `scripts/export_dataset.py`

Export the full longitudinal job dataset for research use.

```python
"""
export_dataset.py
Exports the full job posting dataset to CSV for research.
Includes temporal metadata (first_seen_at, last_seen_at) for longitudinal analysis.

Usage:
    python scripts/export_dataset.py --output data/job_dataset.csv
"""

import sys
import csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job


def export_dataset(output_path: str = "data/job_dataset.csv"):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        jobs = session.query(Job).order_by(Job.first_seen_at.desc()).all()

    print(f"Exporting {len(jobs)} jobs to {output}...")

    columns = [
        "id", "site", "title", "company", "location", "date_posted",
        "job_type", "is_remote", "job_level",
        "min_amount", "max_amount", "interval", "currency",
        "required_skills", "preferred_skills",
        "first_seen_at", "last_seen_at",
        "job_url",
    ]

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for job in jobs:
            row = {}
            for col in columns:
                val = getattr(job, col, None)
                # Serialize lists to pipe-delimited strings for CSV
                if isinstance(val, list):
                    val = "|".join(str(v) for v in val)
                row[col] = val
            writer.writerow(row)

    print(f"Dataset exported: {len(jobs)} rows, {len(columns)} columns.")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/job_dataset.csv")
    args = parser.parse_args()
    export_dataset(args.output)
```

---

## Step 7 — Create `evaluation/` Directory Structure

```bash
mkdir -p evaluation
touch evaluation/__init__.py
touch evaluation/labeled_jobs.csv   # fill in manually per Step 2
mkdir -p logs
mkdir -p scripts
```

---

## Step 8 — Run All Evaluations

```bash
# 1. Run match scorer evaluation
python evaluation/match_eval.py --k 10 --threshold 50

# 2. Generate cover letters for human review
python evaluation/cover_letter_eval.py --n 10

# 3. Export the dataset
python scripts/export_dataset.py

# 4. Test the daily scrape script
python scripts/daily_scrape.py --terms "Software Engineer" --location "New York" --results 10
```

---

## Completion Checklist
- [ ] `evaluation/labeled_jobs.csv` created with 30+ manually labeled jobs
- [ ] `evaluation/match_eval.py` runs and produces accuracy/precision/recall/F1/P@K metrics
- [ ] `evaluation/cl_for_review.md` generated with 10 cover letters formatted for human review
- [ ] `scripts/daily_scrape.py` runs without errors and adds jobs to DB
- [ ] `scripts/export_dataset.py` exports full dataset to `data/job_dataset.csv`
- [ ] `logs/` directory exists and daily_scrape.py writes to it
- [ ] All scripts have `--help` flags that work

## Project Complete 🎉
When done, tell Kenneth "Phase 7 complete — all phases done." The full system is now built:

1. ✅ 8-platform concurrent job scraping with location-aware selection
2. ✅ NLP skill extraction (required + preferred) from all job descriptions
3. ✅ Resume upload, spaCy parsing, and persistent storage
4. ✅ TF-IDF cosine similarity match scoring (0–100%)
5. ✅ Skill gap analysis (matched / missing required / missing preferred)
6. ✅ Claude-powered resume-grounded cover letter generation
7. ✅ Unified web application with all features integrated
8. ✅ Evaluation pipeline: automated metrics + human review protocol
9. ✅ Longitudinal dataset collection + export for future research
