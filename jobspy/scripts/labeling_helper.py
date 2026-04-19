"""Interactive job labeler — writes rows to evaluation/labeled_jobs.csv.

Filters to SWE-relevant titles only (software/engineer/developer/programmer).
Prints current match score for each job as a spot-check aid.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import or_
from jobspy.database import SessionLocal, Job, get_resume_profile
from jobspy.nlp.match_scorer import score_job_against_resume

OUT = Path("evaluation/labeled_jobs.csv")

existing_ids: set = set()
if OUT.exists():
    with open(OUT) as f:
        existing_ids = {row["job_id"] for row in csv.DictReader(f)}

resume = get_resume_profile("default")
if resume is None:
    print("ERROR: No resume profile found for 'default'. Upload a resume first.")
    sys.exit(1)

resume_dict = {
    "parsed_skills": resume.parsed_skills or [],
}

SWE_KEYWORDS = ["%software%", "%engineer%", "%developer%", "%programmer%"]

with SessionLocal() as s:
    jobs = (
        s.query(Job)
        .filter(
            Job.description.isnot(None),
            or_(*[Job.title.ilike(kw) for kw in SWE_KEYWORDS]),
        )
        .order_by(Job.first_seen_at.desc())
        .limit(50)
        .all()
    )

print(f"Pool: {len(jobs)} SWE-relevant jobs ({len(existing_ids)} already labeled)")

rows = []
for job in jobs:
    if str(job.id) in existing_ids:
        continue

    job_dict = {
        "required_skills": job.required_skills or [],
        "preferred_skills": job.preferred_skills or [],
    }
    score_result = score_job_against_resume(job_dict, resume_dict)
    match_score = score_result.get("match_score", 0)

    print("\n" + "=" * 70)
    print(f"Title:      {job.title}")
    print(f"Company:    {job.company}")
    print(f"Location:   {job.location}")
    print(f"Score:      {match_score:.1f}  (informational — label from JD content)")
    print(f"Req:        {(job.required_skills or [])[:8]}")
    print(f"Pref:       {(job.preferred_skills or [])[:8]}")
    print(f"Desc:       {(job.description or '')[:300]}...")

    label = input("\nLabel (0 / 0.5 / 1 / s=skip / q=quit): ").strip()
    if label == "q":
        break
    if label == "s":
        continue
    if label not in ("0", "0.5", "1", "1.0"):
        print("Invalid, skipping")
        continue
    rows.append({"job_id": job.id, "label": label, "notes": ""})

file_exists = OUT.exists() and OUT.stat().st_size > 0
with open(OUT, "a", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["job_id", "label", "notes"])
    if not file_exists:
        writer.writeheader()
    writer.writerows(rows)

print(f"\nAppended {len(rows)} labels. Total needed: ~25–30.")
