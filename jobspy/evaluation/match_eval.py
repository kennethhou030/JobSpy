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

    if not labels:
        print("ERROR: labeled_jobs.csv is empty. Add at least 30 labeled job rows.")
        sys.exit(1)

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
