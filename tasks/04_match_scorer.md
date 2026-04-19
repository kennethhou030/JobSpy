# Phase 4 — Semantic Match Scoring & Skill Gap Analysis
> Prerequisite: Phases 0, 1, 2, and 3 must be complete.

## Context
With the resume profile stored (Phase 3) and skills extracted from job descriptions (Phase 2), we can now compute a match score for every job. The proposal specifies: cosine similarity over TF-IDF vectors of resume skills vs. job requirements, weighted 70% required / 30% preferred (0–100 score). A skill gap list is also shown: which required skills are in the job but absent from the resume.

These two features are the core of the NLP research contribution.

---

## Your Job in This Phase
1. Create `jobspy/nlp/match_scorer.py` with scoring + gap functions
2. Add `GET /api/jobs/{job_id}/match` endpoint
3. Update `GET /api/jobs` to include `match_score` and `skill_gap` in each job response (when a resume is present)
4. Add `sort_by=match_score` support to `GET /api/jobs`

---

## Step 1 — Read These Files First
- `jobspy/database.py` — understand `get_resume_profile()` (from Phase 3) and `get_jobs()`
- `api/main.py` — understand the `GET /api/jobs` endpoint structure and how query params work
- `api/schemas.py` — understand the current job response schema
- `jobspy/nlp/skill_extractor.py` — understand the `extract_skills()` output format (from Phase 2)

---

## Step 2 — Create `jobspy/nlp/match_scorer.py`

```python
"""
match_scorer.py
Computes semantic match scores between a user's resume and job postings
using TF-IDF cosine similarity. Also computes skill gap analysis.

Match Score Formula:
    score = (required_sim * 0.7) + (preferred_sim * 0.3)
    score is scaled to 0–100.

Skill Gap:
    missing_required = job.required_skills - resume.skills
    missing_preferred = job.preferred_skills - resume.skills
    matched = job.required_skills ∩ resume.skills
"""

from __future__ import annotations
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _cosine_sim(text_a: str, text_b: str) -> float:
    """
    Compute cosine similarity between two text strings using TF-IDF.
    Returns 0.0 if either string is empty.
    """
    a = text_a.strip()
    b = text_b.strip()
    if not a or not b:
        return 0.0
    try:
        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),   # unigrams + bigrams for multi-word skills
            min_df=1,
        )
        tfidf_matrix = vectorizer.fit_transform([a, b])
        score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(score)
    except Exception:
        return 0.0


def compute_match_score(
    resume_skills: list[str],
    job_required_skills: list[str],
    job_preferred_skills: list[str],
    required_weight: float = 0.7,
    preferred_weight: float = 0.3,
) -> float:
    """
    Compute a match score (0.0 to 100.0) between a resume's skills
    and a job's required/preferred skills.

    Args:
        resume_skills: Skills extracted from the user's resume
        job_required_skills: Required skills extracted from the job description (Phase 2)
        job_preferred_skills: Preferred skills extracted from the job description (Phase 2)
        required_weight: Weight for required skill similarity (default 0.7)
        preferred_weight: Weight for preferred skill similarity (default 0.3)

    Returns:
        Float 0.0–100.0 representing the match percentage
    """
    if not resume_skills:
        return 0.0
    if not job_required_skills and not job_preferred_skills:
        return 0.0

    resume_text = " ".join(resume_skills)
    required_text = " ".join(job_required_skills) if job_required_skills else ""
    preferred_text = " ".join(job_preferred_skills) if job_preferred_skills else ""

    req_sim = _cosine_sim(resume_text, required_text) if required_text else 0.0
    pref_sim = _cosine_sim(resume_text, preferred_text) if preferred_text else 0.0

    # Adjust weights if one side is empty
    if not required_text:
        weighted = pref_sim
    elif not preferred_text:
        weighted = req_sim
    else:
        weighted = (req_sim * required_weight) + (pref_sim * preferred_weight)

    return round(weighted * 100, 1)


def compute_skill_gap(
    resume_skills: list[str],
    job_required_skills: list[str],
    job_preferred_skills: list[str],
) -> dict:
    """
    Compute which skills the candidate is missing vs. which they have.

    Args:
        resume_skills: Skills from the user's resume
        job_required_skills: Required skills from the job
        job_preferred_skills: Preferred skills from the job

    Returns:
        {
            "matched": [...],           # required skills the candidate HAS
            "missing_required": [...],  # required skills the candidate LACKS
            "missing_preferred": [...], # preferred skills the candidate LACKS
        }
    """
    # Normalize to lowercase for comparison, preserve original casing in output
    resume_lower = {s.lower() for s in resume_skills}

    matched = []
    missing_required = []
    missing_preferred = []

    for skill in job_required_skills:
        if skill.lower() in resume_lower:
            matched.append(skill)
        else:
            missing_required.append(skill)

    for skill in job_preferred_skills:
        if skill.lower() not in resume_lower:
            missing_preferred.append(skill)

    return {
        "matched": sorted(matched),
        "missing_required": sorted(missing_required),
        "missing_preferred": sorted(missing_preferred),
    }


def score_job_against_resume(job: dict, resume_profile: dict) -> dict:
    """
    Convenience function: given a job dict and a resume profile dict,
    compute both match score and skill gap in one call.

    Args:
        job: Job dict with 'required_skills' and 'preferred_skills' keys
        resume_profile: Resume profile dict with 'parsed_skills' key

    Returns:
        {
            "match_score": float,
            "skill_gap": { "matched": [...], "missing_required": [...], "missing_preferred": [...] }
        }
    """
    resume_skills = resume_profile.get("parsed_skills") or []
    required = job.get("required_skills") or []
    preferred = job.get("preferred_skills") or []

    match_score = compute_match_score(resume_skills, required, preferred)
    skill_gap = compute_skill_gap(resume_skills, required, preferred)

    return {
        "match_score": match_score,
        "skill_gap": skill_gap,
    }
```

---

## Step 3 — Add Match Endpoint to `api/main.py`

Add these imports at the top of `api/main.py`:
```python
from jobspy.nlp.match_scorer import score_job_against_resume
from jobspy.database import get_resume_profile, get_job_by_id  # adjust name to match actual function
```

Add this new endpoint:

```python
@app.get("/api/jobs/{job_id}/match")
async def get_job_match(job_id: str):
    """
    Compute match score and skill gap for a specific job against the stored resume.
    Returns 404 if no resume is uploaded, 404 if job not found.
    """
    resume = get_resume_profile(user_id="default")
    if not resume:
        raise HTTPException(
            status_code=404,
            detail="No resume uploaded. Please upload your resume on the Profile page first."
        )

    # Fetch the job from DB — use whatever function get_jobs() or get_job() uses
    # Adjust the DB call to match your existing get_job_by_id() or similar function
    job = get_job_by_id(job_id)  # <-- adjust this to match actual DB function name
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # Convert SQLAlchemy row to dict if needed
    job_dict = {
        "required_skills": job.required_skills or [],
        "preferred_skills": job.preferred_skills or [],
        "title": job.title,
        "company": job.company,
    }
    resume_dict = {
        "parsed_skills": resume.parsed_skills or [],
    }

    result = score_job_against_resume(job_dict, resume_dict)
    return {
        "job_id": job_id,
        "job_title": job.title,
        "company": job.company,
        **result,
    }
```

---

## Step 4 — Update `GET /api/jobs` to Include Match Score

Find the existing `GET /api/jobs` endpoint in `api/main.py`.

After fetching the list of jobs from the DB, check if a resume is present. If yes, compute match scores for all returned jobs and attach them:

```python
@app.get("/api/jobs")
async def query_jobs(
    # ... existing parameters ...
    sort_by: str | None = None,  # ADD THIS: accepts "match_score"
    # ... rest of existing params ...
):
    # ... existing DB query logic ...
    jobs = get_jobs(...)  # existing call

    # Enrich with match scores if resume is present
    resume = get_resume_profile(user_id="default")
    resume_dict = {"parsed_skills": resume.parsed_skills or []} if resume else None

    job_list = []
    for job in jobs:
        job_data = {col: getattr(job, col, None) for col in job.__table__.columns.keys()}

        if resume_dict:
            result = score_job_against_resume(
                {
                    "required_skills": job.required_skills or [],
                    "preferred_skills": job.preferred_skills or [],
                },
                resume_dict,
            )
            job_data["match_score"] = result["match_score"]
            job_data["skill_gap"] = result["skill_gap"]
        else:
            job_data["match_score"] = None
            job_data["skill_gap"] = None

        job_list.append(job_data)

    # Sort by match score if requested
    if sort_by == "match_score" and resume_dict:
        job_list.sort(key=lambda j: j.get("match_score") or 0, reverse=True)

    return {"total": len(job_list), "jobs": job_list}
```

**Note:** If this causes performance issues with large result sets, compute match scores lazily (only for the first 50 results, or only when explicitly requested via `include_match=true` query param). For the course project, computing for all results is fine.

---

## Step 5 — Update `api/schemas.py`

Find the job response schema. Add these two optional fields:

```python
match_score: float | None = None      # 0.0–100.0, None if no resume uploaded
skill_gap: dict | None = None          # {"matched": [], "missing_required": [], "missing_preferred": []}
```

---

## Step 6 — Add a DB Helper `get_job_by_id` (if it doesn't exist)

Check `jobspy/database.py` — if there's no `get_job_by_id()` function, add one:

```python
def get_job_by_id(job_id: str) -> Job | None:
    """Retrieve a single job by its ID."""
    with SessionLocal() as session:
        return session.query(Job).filter(Job.id == job_id).first()
```

---

## Step 7 — Test It

**Unit test (`tasks/test_match_scorer.py`):**

```python
from jobspy.nlp.match_scorer import compute_match_score, compute_skill_gap, score_job_against_resume

# Test 1: Perfect match
resume_skills = ["Python", "SQL", "Docker", "FastAPI"]
required = ["Python", "SQL", "Docker"]
preferred = ["Kubernetes", "AWS"]

score = compute_match_score(resume_skills, required, preferred)
print(f"Test 1 - Score (high match expected): {score}")
assert score > 50.0, f"Expected high score, got {score}"

# Test 2: Zero match
score2 = compute_match_score(["Excel", "PowerPoint"], ["Python", "Kubernetes", "Terraform"], [])
print(f"Test 2 - Score (low match expected): {score2}")
assert score2 < 30.0, f"Expected low score, got {score2}"

# Test 3: Skill gap
gap = compute_skill_gap(
    resume_skills=["Python", "SQL"],
    job_required_skills=["Python", "SQL", "Kubernetes"],
    job_preferred_skills=["Terraform", "AWS"],
)
assert "Kubernetes" in gap["missing_required"]
assert "Python" in gap["matched"]
assert "SQL" in gap["matched"]
assert "Terraform" in gap["missing_preferred"]
print(f"Test 3 - Skill gap: {gap}")
print("Test 3 passed")

# Test 4: Empty resume
score3 = compute_match_score([], ["Python", "SQL"], [])
assert score3 == 0.0
print("Test 4 passed (empty resume)")

# Test 5: score_job_against_resume convenience function
result = score_job_against_resume(
    job={"required_skills": ["Python", "Docker"], "preferred_skills": ["AWS"]},
    resume_profile={"parsed_skills": ["Python", "JavaScript", "Docker"]},
)
assert "match_score" in result
assert "skill_gap" in result
print(f"Test 5 - Combined result: {result}")

print("\nAll match scorer tests passed!")
```

**API test:**

```bash
# Start server
uvicorn api.main:app --port 8000 --reload

# First upload your resume (from Phase 3)
curl -X POST http://localhost:8000/api/resume/upload -F "file=@resume.pdf"

# Then get match score for a specific job
curl http://localhost:8000/api/jobs/{job_id}/match

# Get all jobs sorted by match score
curl "http://localhost:8000/api/jobs?sort_by=match_score"
```

---

## Completion Checklist
- [ ] `jobspy/nlp/match_scorer.py` created with `compute_match_score()`, `compute_skill_gap()`, `score_job_against_resume()`
- [ ] All unit tests pass
- [ ] `GET /api/jobs/{job_id}/match` endpoint added and returns correct JSON
- [ ] `GET /api/jobs` returns `match_score` and `skill_gap` per job when resume is present
- [ ] `sort_by=match_score` query param works
- [ ] `api/schemas.py` updated with `match_score` and `skill_gap` fields
- [ ] `get_job_by_id()` function exists in `database.py`

## What's Next
When done, tell Kenneth "Phase 4 complete" and he will give you `05_cover_letter.md`.
