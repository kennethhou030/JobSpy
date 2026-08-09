"""
export_dataset.py
Exports the full job posting dataset to CSV for research.
Includes temporal metadata (first_seen_at, last_seen_at) for longitudinal analysis.

Usage:
    python scripts/export_dataset.py --output data/job_dataset.csv
"""

import argparse
import csv
import sys
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
    return len(jobs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export longitudinal job dataset to CSV")
    parser.add_argument("--output", default="data/job_dataset.csv",
                        help="Output CSV path (default: data/job_dataset.csv)")
    args = parser.parse_args()
    export_dataset(args.output)
