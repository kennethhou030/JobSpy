"""Diagnostic: print exactly where the signal is being lost."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job, get_resume_profile
from jobspy.nlp.match_scorer import compute_match_score, compute_skill_gap

resume = get_resume_profile(user_id="default")
if not resume:
    print("No resume uploaded."); sys.exit(1)

resume_skills = resume.parsed_skills or []
print(f"Resume: {len(resume_skills)} skills → {resume_skills[:15]}")

with SessionLocal() as s:
    jobs = s.query(Job).filter(Job.description.isnot(None)).limit(10).all()

print(f"\n{'Title':<45} {'Req':<5} {'Pref':<5} {'Score':<6}")
print("-" * 70)
for j in jobs:
    req, pref = j.required_skills or [], j.preferred_skills or []
    score = compute_match_score(resume_skills, req, pref)
    print(f"{(j.title or '')[:44]:<45} {len(req):<5} {len(pref):<5} {score:<6}")

totals = [(len(j.required_skills or []), len(j.preferred_skills or [])) for j in jobs]
avg_req = sum(r for r, _ in totals) / len(totals) if totals else 0
avg_pref = sum(p for _, p in totals) / len(totals) if totals else 0
print(f"\nAvg required skills per job: {avg_req:.1f}")
print(f"Avg preferred skills per job: {avg_pref:.1f}")
