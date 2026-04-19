"""One-time backfill: re-extract skills on all existing jobs using current taxonomy."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job
from jobspy.nlp.skill_extractor import extract_skills

with SessionLocal() as s:
    jobs = s.query(Job).filter(Job.description.isnot(None)).all()
    total = len(jobs)
    print(f"Backfilling {total} jobs...")
    for i, job in enumerate(jobs, 1):
        result = extract_skills(job.description)
        job.required_skills = result["required"]
        job.preferred_skills = result["preferred"]
        if i % 50 == 0:
            s.commit(); print(f"  backfilled {i}/{total}")
    s.commit()
print("done")
