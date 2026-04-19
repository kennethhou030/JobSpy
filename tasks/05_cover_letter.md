# Phase 5 — AI Cover Letter Generation (Claude API)
> Prerequisite: Phases 0 through 4 must be complete.

## Context
The final NLP deliverable: resume-grounded cover letter generation via Claude. The key differentiator from ChatGPT is that JobSpy stores the user's resume once and automatically grounds every cover letter in that profile + the specific job description — zero copy-paste. The proposal specifies using the Claude API (`claude-opus-4-6`).

Cover letters are stored in a `cover_letters` DB table so users can retrieve and download previously generated ones.

---

## Your Job in This Phase
1. Set up the `ANTHROPIC_API_KEY` environment variable
2. Create `jobspy/nlp/cover_letter.py`
3. Add `CoverLetter` table to `jobspy/database.py`
4. Add `POST /api/cover-letter/{job_id}` and `GET /api/cover-letter/{job_id}` endpoints
5. Test end to end

---

## Step 1 — Read These Files First
- `jobspy/database.py` — understand the Base/SessionLocal pattern (adding new table)
- `api/main.py` — understand how to add endpoints that depend on both job + resume data
- `jobspy/nlp/match_scorer.py` — you'll reuse `compute_skill_gap()` to tell Claude which skills to emphasize

---

## Step 2 — Set Up the API Key

The `anthropic` package reads `ANTHROPIC_API_KEY` from the environment. Create a `.env` file in the project root (if one doesn't exist) and add:

```
ANTHROPIC_API_KEY=your_key_here
```

Then confirm `api/main.py` loads `.env` at startup. If it doesn't, add this near the top of `api/main.py`:

```python
from dotenv import load_dotenv
load_dotenv()
```

Also install python-dotenv if not present:
```bash
pip install python-dotenv --break-system-packages
```

Add `python-dotenv` to `pyproject.toml` dependencies.

**IMPORTANT:** Add `.env` to `.gitignore` if it's not already there. Never commit API keys.

---

## Step 3 — Create `jobspy/nlp/cover_letter.py`

```python
"""
cover_letter.py
Generates personalized, resume-grounded cover letters using the Claude API.
The resume profile (stored in DB from Phase 3) and job description are automatically
combined into a structured prompt — no manual copy-paste required.
"""

from __future__ import annotations
import os
import anthropic

# The model to use for generation (as specified in the proposal)
CLAUDE_MODEL = "claude-opus-4-6"

# Maximum tokens for cover letter (roughly 400–600 words)
MAX_TOKENS = 1024

COVER_LETTER_SYSTEM = """You are an expert career coach and professional writer specializing in
job application materials. You write tailored, authentic cover letters that:
- Are specific to the company and role
- Highlight only skills and experiences actually present in the candidate's resume
- Are professional but not generic or formulaic
- Are 3–4 paragraphs: opening hook, skills alignment, culture/motivation, closing call-to-action
- Never invent credentials or experience not present in the resume
- Sound like a real person, not a template"""

COVER_LETTER_PROMPT = """Please write a tailored cover letter for the following job application.

=== CANDIDATE PROFILE ===
Name: {name}
Years of Experience: {experience_years}
Summary: {summary}
Skills: {resume_skills}

=== TARGET JOB ===
Role: {job_title}
Company: {company_name}
Location: {location}

Required Skills: {required_skills}
Preferred Skills: {preferred_skills}

Matched Skills (candidate already has): {matched_skills}
Missing Required Skills (candidate lacks): {missing_required}

Job Description (excerpt):
{job_description}

=== INSTRUCTIONS ===
Write a 3–4 paragraph cover letter. Structure:
1. Opening: Mention the specific role and company. Lead with the strongest relevant qualification.
2. Skills paragraph: Highlight 2–3 specific skills from the candidate's profile that align with required skills. Be concrete.
3. Motivation paragraph: Why this company/role specifically? Connect the job description to the candidate's career goals.
4. Closing: Express enthusiasm, reference next steps, sign off.

Do NOT mention skills from "Missing Required Skills" as things the candidate has.
Output ONLY the cover letter text — no preamble, no "Here is your cover letter:", just the letter itself starting with "Dear Hiring Manager," or a specific name if available."""


def generate_cover_letter(resume: dict, job: dict) -> str:
    """
    Generate a tailored cover letter using Claude.

    Args:
        resume: Parsed resume profile dict (from get_resume_profile())
                Expected keys: name, summary, parsed_skills, experience_years
        job: Job dict with title, company, location, description, required_skills, preferred_skills

    Returns:
        Cover letter as a string
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Add it to your .env file or export it in your shell."
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Compute skill alignment for the prompt
    from jobspy.nlp.match_scorer import compute_skill_gap
    gap = compute_skill_gap(
        resume_skills=resume.get("parsed_skills") or [],
        job_required_skills=job.get("required_skills") or [],
        job_preferred_skills=job.get("preferred_skills") or [],
    )

    # Truncate job description to stay within token limits
    description = (job.get("description") or "")[:3000]

    prompt = COVER_LETTER_PROMPT.format(
        name=resume.get("name") or "the candidate",
        experience_years=resume.get("experience_years") or "N/A",
        summary=(resume.get("summary") or "")[:400],
        resume_skills=", ".join(resume.get("parsed_skills") or [])[:500],
        job_title=job.get("title") or "the position",
        company_name=job.get("company") or "the company",
        location=job.get("location") or "N/A",
        required_skills=", ".join(job.get("required_skills") or []),
        preferred_skills=", ".join(job.get("preferred_skills") or []),
        matched_skills=", ".join(gap.get("matched") or []),
        missing_required=", ".join(gap.get("missing_required") or []),
        job_description=description,
    )

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=COVER_LETTER_SYSTEM,
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    return message.content[0].text.strip()
```

---

## Step 4 — Add `CoverLetter` Table to `jobspy/database.py`

Add this model class (after `ResumeProfile`):

```python
class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False, default="default")
    cover_letter_text = Column(Text, nullable=False)
    job_title = Column(String, nullable=True)     # denormalized for quick display
    company_name = Column(String, nullable=True)
    match_score = Column(Float, nullable=True)    # score at time of generation
    generated_at = Column(DateTime, default=datetime.utcnow)
```

Add these two helper functions:

```python
def save_cover_letter(
    job_id: str,
    cover_letter_text: str,
    job_title: str | None = None,
    company_name: str | None = None,
    match_score: float | None = None,
    user_id: str = "default",
) -> CoverLetter:
    """Save a generated cover letter to the DB. Overwrites if one exists for this job."""
    with SessionLocal() as session:
        existing = session.query(CoverLetter).filter_by(job_id=job_id, user_id=user_id).first()
        if existing:
            existing.cover_letter_text = cover_letter_text
            existing.job_title = job_title
            existing.company_name = company_name
            existing.match_score = match_score
            existing.generated_at = datetime.utcnow()
            session.commit()
            session.refresh(existing)
            return existing
        cl = CoverLetter(
            job_id=job_id,
            user_id=user_id,
            cover_letter_text=cover_letter_text,
            job_title=job_title,
            company_name=company_name,
            match_score=match_score,
        )
        session.add(cl)
        session.commit()
        session.refresh(cl)
        return cl


def get_cover_letter(job_id: str, user_id: str = "default") -> CoverLetter | None:
    """Retrieve stored cover letter for a job."""
    with SessionLocal() as session:
        return session.query(CoverLetter).filter_by(job_id=job_id, user_id=user_id).first()


def list_cover_letters(user_id: str = "default") -> list[CoverLetter]:
    """List all generated cover letters for the user."""
    with SessionLocal() as session:
        return (
            session.query(CoverLetter)
            .filter_by(user_id=user_id)
            .order_by(CoverLetter.generated_at.desc())
            .all()
        )
```

Delete `jobs.db` and restart to apply the new schema:
```bash
rm -f jobs.db
```

---

## Step 5 — Add API Endpoints to `api/main.py`

Add these imports:
```python
from jobspy.nlp.cover_letter import generate_cover_letter
from jobspy.database import save_cover_letter, get_cover_letter, list_cover_letters
```

Add these endpoints:

```python
@app.post("/api/cover-letter/{job_id}")
async def create_cover_letter(job_id: str):
    """
    Generate a tailored cover letter for the given job using the stored resume.
    Requires a resume to be uploaded first (Phase 3).
    The generated letter is saved and can be retrieved later.
    """
    # Check resume exists
    resume = get_resume_profile(user_id="default")
    if not resume:
        raise HTTPException(
            status_code=404,
            detail="No resume uploaded. Please upload your resume on the Profile page first."
        )

    # Check job exists
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    resume_dict = {
        "name": resume.name,
        "summary": resume.summary,
        "parsed_skills": resume.parsed_skills or [],
        "experience_years": resume.experience_years,
    }

    job_dict = {
        "title": job.title,
        "company": job.company,
        "location": str(job.location) if job.location else None,
        "description": job.description,
        "required_skills": job.required_skills or [],
        "preferred_skills": job.preferred_skills or [],
    }

    try:
        cover_letter_text = generate_cover_letter(resume_dict, job_dict)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {str(e)}")

    # Compute match score to store alongside the letter
    from jobspy.nlp.match_scorer import compute_match_score
    match_score = compute_match_score(
        resume_dict["parsed_skills"],
        job_dict["required_skills"],
        job_dict["preferred_skills"],
    )

    # Save to DB
    cl = save_cover_letter(
        job_id=job_id,
        cover_letter_text=cover_letter_text,
        job_title=job.title,
        company_name=job.company,
        match_score=match_score,
    )

    return {
        "job_id": job_id,
        "job_title": job.title,
        "company": job.company,
        "match_score": match_score,
        "cover_letter": cover_letter_text,
        "generated_at": cl.generated_at.isoformat(),
    }


@app.get("/api/cover-letter/{job_id}")
async def get_cover_letter_endpoint(job_id: str):
    """Retrieve a previously generated cover letter for a job."""
    cl = get_cover_letter(job_id=job_id, user_id="default")
    if not cl:
        raise HTTPException(
            status_code=404,
            detail=f"No cover letter found for job '{job_id}'. Generate one first."
        )
    return {
        "job_id": cl.job_id,
        "job_title": cl.job_title,
        "company": cl.company_name,
        "match_score": cl.match_score,
        "cover_letter": cl.cover_letter_text,
        "generated_at": cl.generated_at.isoformat(),
    }


@app.get("/api/cover-letters")
async def list_cover_letters_endpoint():
    """List all generated cover letters for the current user."""
    letters = list_cover_letters(user_id="default")
    return {
        "total": len(letters),
        "cover_letters": [
            {
                "job_id": cl.job_id,
                "job_title": cl.job_title,
                "company": cl.company_name,
                "match_score": cl.match_score,
                "generated_at": cl.generated_at.isoformat(),
                "preview": cl.cover_letter_text[:200] + "...",
            }
            for cl in letters
        ],
    }
```

---

## Step 6 — Update `frontend/js/api.js`

Add these three methods to the `window.API` object:

```javascript
generateCoverLetter(jobId) {
  return fetch(`/api/cover-letter/${jobId}`, { method: 'POST' }).then(r => r.json());
},
getCoverLetter(jobId) {
  return fetch(`/api/cover-letter/${jobId}`).then(r => {
    if (r.status === 404) return null;
    return r.json();
  });
},
listCoverLetters() {
  return fetch('/api/cover-letters').then(r => r.json());
},
```

---

## Step 7 — Test It

**Unit test (`tasks/test_cover_letter.py`):**

```python
import os

# Make sure your API key is set before running this test
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: Set ANTHROPIC_API_KEY before running this test")
    exit(1)

from jobspy.nlp.cover_letter import generate_cover_letter

resume = {
    "name": "Alex Johnson",
    "summary": "Software engineer with 4 years of experience in Python and backend development.",
    "parsed_skills": ["Python", "FastAPI", "SQL", "Docker", "React"],
    "experience_years": 4.0,
}

job = {
    "title": "Backend Software Engineer",
    "company": "Acme Corp",
    "location": "San Francisco, CA",
    "description": "We are looking for a backend engineer with Python and Docker experience...",
    "required_skills": ["Python", "Docker", "SQL"],
    "preferred_skills": ["Kubernetes", "AWS"],
}

print("Generating cover letter (this makes a real API call)...")
letter = generate_cover_letter(resume, job)
print("\n--- Generated Cover Letter ---")
print(letter)
print("\n--- End ---")

assert len(letter) > 200, "Cover letter seems too short"
assert "Acme Corp" in letter or "acme" in letter.lower(), "Company name should appear in letter"
assert "Python" in letter, "Key matched skill should appear in letter"
print("\nCover letter generation test passed!")
```

**API test:**

```bash
# Generate a cover letter for a job (replace JOB_ID with a real job ID from your DB)
curl -X POST http://localhost:8000/api/cover-letter/linkedin-1234567890

# Retrieve the saved letter
curl http://localhost:8000/api/cover-letter/linkedin-1234567890

# List all generated letters
curl http://localhost:8000/api/cover-letters
```

---

## Completion Checklist
- [ ] `ANTHROPIC_API_KEY` set in `.env` and loaded at startup
- [ ] `.env` added to `.gitignore`
- [ ] `jobspy/nlp/cover_letter.py` created and tested
- [ ] `CoverLetter` table added to `database.py`
- [ ] `save_cover_letter()`, `get_cover_letter()`, `list_cover_letters()` functions added
- [ ] `POST /api/cover-letter/{job_id}` endpoint added and generates a real letter
- [ ] `GET /api/cover-letter/{job_id}` endpoint retrieves saved letter
- [ ] `GET /api/cover-letters` lists all generated letters
- [ ] `frontend/js/api.js` updated with the 3 new API methods
- [ ] End-to-end test passes (upload resume → scrape job → generate cover letter → retrieve it)

## What's Next
When done, tell Kenneth "Phase 5 complete" and he will give you `06_frontend.md`.
