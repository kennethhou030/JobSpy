# Phase 3 — Resume Parser & Persistent Storage
> Prerequisite: Phases 0, 1, and 2 must be complete.

## Context
Users upload their resume once. It is parsed with spaCy + pypdf/python-docx to extract: name, email, phone, skills, education, experience years, and summary. The parsed data is stored in a new `resume_profiles` database table and reused automatically for all subsequent match scoring and cover letter generation — no copy-paste required.

This is the project's key UX innovation over general-purpose LLMs.

---

## Your Job in This Phase
1. Create `jobspy/nlp/resume_parser.py`
2. Add `ResumeProfile` table to `jobspy/database.py`
3. Add resume upload and retrieval API endpoints to `api/main.py`
4. Create `frontend/profile.html` — the resume upload page

---

## Step 1 — Read These Files First
- `jobspy/database.py` — understand the existing `Base`, `engine`, `SessionLocal` pattern so you match it exactly
- `api/main.py` — understand how file upload works in FastAPI (look for any existing file handling, or note that we're adding it fresh)
- `api/schemas.py` — understand the response schema pattern
- `frontend/index.html` — understand the HTML/JS/Tailwind style so `profile.html` matches

---

## Step 2 — Create `jobspy/nlp/resume_parser.py`

```python
"""
resume_parser.py
Parses resume files (PDF or DOCX) and extracts structured profile information
using spaCy NER + regex patterns.
"""

from __future__ import annotations
import re
from pathlib import Path

import spacy

# Import skill extractor from Phase 2 to reuse the same taxonomy
from jobspy.nlp.skill_extractor import extract_skills


def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF file using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    return "\n".join(pages_text)


def extract_text_from_docx(file_path: str) -> str:
    """Extract raw text from a DOCX file using python-docx."""
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(file_path: str) -> str:
    """Extract text from PDF or DOCX. Raises ValueError for unsupported formats."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use PDF or DOCX.")


def extract_email(text: str) -> str | None:
    """Extract first email address found in text."""
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


def extract_phone(text: str) -> str | None:
    """Extract first phone number found in text."""
    match = re.search(
        r"(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?)(\d{3}[\s.\-]?\d{4})", text
    )
    return match.group(0).strip() if match else None


def extract_name(doc) -> str | None:
    """
    Extract the candidate's name using spaCy NER.
    Falls back to the first PERSON entity, or the first line of the resume.
    """
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text.strip()
    return None


def estimate_experience_years(text: str) -> float:
    """
    Estimate years of experience by finding the earliest year mentioned
    in work experience and computing the difference from today.
    """
    import datetime
    current_year = datetime.datetime.now().year

    # Find all 4-digit years in the text (1980–current year)
    years_found = re.findall(r"\b(19[89]\d|20[0-2]\d)\b", text)
    if not years_found:
        return 0.0

    years_int = [int(y) for y in years_found]
    earliest = min(years_int)
    # Cap earliest at 1990 and don't count future years
    earliest = max(earliest, 1990)
    earliest = min(earliest, current_year)

    return float(current_year - earliest)


def extract_education(doc) -> list[dict]:
    """
    Extract education entries (institution names + years) from the resume.
    Uses spaCy NER to find ORG entities near year patterns.
    """
    education = []
    orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]

    # Common degree keywords
    degree_pattern = re.compile(
        r"(B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|Ph\.?D\.?|Bachelor|Master|Doctor|Associate)",
        re.IGNORECASE,
    )

    text = doc.text
    for match in degree_pattern.finditer(text):
        # Get surrounding context
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 100)
        snippet = text[start:end].strip()

        # Find any org name nearby
        nearby_org = None
        for org in orgs:
            if org.lower() in snippet.lower():
                nearby_org = org
                break

        # Find any year nearby
        year_match = re.search(r"\b(19[89]\d|20[0-2]\d)\b", snippet)

        education.append({
            "degree": match.group(0),
            "institution": nearby_org,
            "year": int(year_match.group(0)) if year_match else None,
            "snippet": snippet[:120],
        })

    # Deduplicate by snippet similarity
    seen = set()
    deduped = []
    for entry in education:
        key = (entry.get("degree", "").lower(), entry.get("institution", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(entry)

    return deduped[:5]  # cap at 5 entries


def extract_summary(text: str) -> str:
    """
    Extract the professional summary/objective section from the resume text.
    Returns the first ~500 chars of the summary section if found, else first 500 chars.
    """
    summary_pattern = re.compile(
        r"(summary|objective|profile|about me)[:\n\r\s]+(.{50,500})",
        re.IGNORECASE | re.DOTALL,
    )
    match = summary_pattern.search(text)
    if match:
        return match.group(2).strip()[:500]
    # Fallback: first 500 characters (often the header/summary area)
    return text[:500].strip()


def parse_resume(file_path: str) -> dict:
    """
    Full resume parsing pipeline. Extracts all structured fields.

    Args:
        file_path: Absolute path to the resume file (PDF or DOCX)

    Returns:
        dict with keys: raw_text, name, email, phone, skills, education,
                        experience_years, summary
    """
    # Step 1: Extract raw text
    raw_text = extract_text(file_path)

    if not raw_text.strip():
        raise ValueError("Could not extract any text from the resume file. "
                         "Make sure it's not a scanned image-only PDF.")

    # Step 2: Run spaCy
    nlp = spacy.load("en_core_web_md")
    doc = nlp(raw_text[:10000])  # limit to 10k chars for performance

    # Step 3: Extract all fields
    skills_result = extract_skills(raw_text)
    all_skills = list(set(skills_result["required"] + skills_result["preferred"]))

    return {
        "raw_text": raw_text,
        "name": extract_name(doc),
        "email": extract_email(raw_text),
        "phone": extract_phone(raw_text),
        "parsed_skills": all_skills,
        "education": extract_education(doc),
        "experience_years": estimate_experience_years(raw_text),
        "summary": extract_summary(raw_text),
    }
```

---

## Step 3 — Add `ResumeProfile` Table to `jobspy/database.py`

Add the following imports at the top if not already present:
```python
from sqlalchemy import Text, Float, JSON
```

Add the `ResumeProfile` model class to `database.py`, after the existing model classes:

```python
class ResumeProfile(Base):
    __tablename__ = "resume_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, unique=True, index=True, nullable=False)
    # "default" for single-user MVP; can expand to multi-user later
    file_path = Column(String, nullable=True)       # path to original uploaded file
    original_filename = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)          # full extracted text
    parsed_skills = Column(JSON, nullable=True)     # list[str] of all skills
    education = Column(JSON, nullable=True)         # list[dict]
    experience_years = Column(Float, nullable=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Then add these two helper functions to `database.py`:

```python
def save_resume_profile(profile_data: dict, user_id: str = "default") -> ResumeProfile:
    """Upsert a resume profile for the given user_id."""
    with SessionLocal() as session:
        existing = session.query(ResumeProfile).filter_by(user_id=user_id).first()
        if existing:
            for key, val in profile_data.items():
                setattr(existing, key, val)
            existing.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(existing)
            return existing
        else:
            profile = ResumeProfile(user_id=user_id, **profile_data)
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return profile


def get_resume_profile(user_id: str = "default") -> ResumeProfile | None:
    """Retrieve the resume profile for the given user_id."""
    with SessionLocal() as session:
        return session.query(ResumeProfile).filter_by(user_id=user_id).first()
```

After adding the model, delete `jobs.db` and restart the app to recreate the schema:
```bash
rm -f jobs.db
```

---

## Step 4 — Add Resume API Endpoints to `api/main.py`

Add these imports near the top of `api/main.py`:

```python
import shutil
import os
from fastapi import UploadFile, File, HTTPException
from jobspy.nlp.resume_parser import parse_resume
from jobspy.database import save_resume_profile, get_resume_profile
```

Add these three endpoints:

```python
@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload a resume (PDF or DOCX). Parses it and stores the profile persistently.
    For the MVP, uses user_id='default' (single-user mode).
    """
    # Validate file type
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    # Save uploaded file to data/resumes/
    save_dir = Path("data/resumes")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"default_resume{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse the resume
    try:
        parsed = parse_resume(str(save_path))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse resume: {str(e)}")

    # Save to DB
    profile_data = {
        "file_path": str(save_path),
        "original_filename": filename,
        **parsed,
    }
    profile = save_resume_profile(profile_data, user_id="default")

    return {
        "message": "Resume uploaded and parsed successfully.",
        "name": profile.name,
        "email": profile.email,
        "skills_count": len(profile.parsed_skills or []),
        "experience_years": profile.experience_years,
        "education_count": len(profile.education or []),
    }


@app.get("/api/resume")
async def get_resume():
    """Retrieve the currently stored resume profile."""
    profile = get_resume_profile(user_id="default")
    if not profile:
        raise HTTPException(status_code=404, detail="No resume uploaded yet.")
    return {
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "parsed_skills": profile.parsed_skills or [],
        "education": profile.education or [],
        "experience_years": profile.experience_years,
        "summary": profile.summary,
        "original_filename": profile.original_filename,
        "uploaded_at": profile.uploaded_at.isoformat() if profile.uploaded_at else None,
    }


@app.delete("/api/resume")
async def delete_resume():
    """Delete the stored resume profile and the uploaded file."""
    from jobspy.database import SessionLocal, ResumeProfile
    with SessionLocal() as session:
        profile = session.query(ResumeProfile).filter_by(user_id="default").first()
        if not profile:
            raise HTTPException(status_code=404, detail="No resume found.")
        # Delete file from disk
        if profile.file_path and Path(profile.file_path).exists():
            Path(profile.file_path).unlink()
        session.delete(profile)
        session.commit()
    return {"message": "Resume deleted."}
```

---

## Step 5 — Create `frontend/profile.html`

Create a new page that matches the visual style of the existing `frontend/index.html` (same Tailwind CDN, same Google Fonts, same color scheme). This page should have:

**Layout:**
- Same top navigation/header bar as `index.html`
- A centered card for the "Upload Resume" area
- A second card that shows the parsed profile once a resume is uploaded

**Upload Card:**
- `<input type="file" accept=".pdf,.docx">` with a styled drag-drop area
- Upload button that calls `POST /api/resume/upload`
- Shows a spinner during upload
- Shows success confirmation with name, skill count, experience years

**Profile Display Card** (shown after upload or on page load if resume exists):
- Candidate name and email
- Skills as badge chips (green)
- Education list
- Years of experience
- Summary text (truncated, expandable)
- "Delete Resume" button (calls `DELETE /api/resume`)
- "Re-upload" button

**JavaScript pattern** — follow the same `window.API` pattern from `frontend/js/api.js`. Add new methods to `api.js`:

```javascript
// Add these to window.API in frontend/js/api.js
uploadResume(formData) {
  return fetch('/api/resume/upload', {
    method: 'POST',
    body: formData,  // FormData with the file
  }).then(r => r.json());
},
getResume() {
  return fetch('/api/resume').then(r => {
    if (r.status === 404) return null;
    return r.json();
  });
},
deleteResume() {
  return fetch('/api/resume', { method: 'DELETE' }).then(r => r.json());
},
```

---

## Step 6 — Test It

**API test (use curl or the FastAPI docs at `http://localhost:8000/docs`):**

```bash
# Upload a test resume PDF
curl -X POST http://localhost:8000/api/resume/upload \
  -F "file=@/path/to/your/resume.pdf"

# Get the stored profile
curl http://localhost:8000/api/resume

# Delete it
curl -X DELETE http://localhost:8000/api/resume
```

**Parser unit test (`tasks/test_resume_parser.py`):**

```python
from jobspy.nlp.resume_parser import (
    extract_email, extract_phone, estimate_experience_years, extract_skills
)

# Test email extraction
assert extract_email("Contact me at john.doe@example.com for details") == "john.doe@example.com"
print("Email test passed")

# Test phone extraction
phone = extract_phone("Call me at (404) 555-1234 anytime")
assert phone is not None
print(f"Phone test passed: {phone}")

# Test experience years
years = estimate_experience_years("Worked at Google from 2018 to 2023. Joined Microsoft in 2023.")
assert years > 0
print(f"Experience years test passed: {years}")

print("All resume parser tests passed!")
```

---

## Completion Checklist
- [ ] `jobspy/nlp/resume_parser.py` created and all helper functions work
- [ ] `ResumeProfile` table added to `database.py`
- [ ] `save_resume_profile()` and `get_resume_profile()` functions added to `database.py`
- [ ] `POST /api/resume/upload`, `GET /api/resume`, `DELETE /api/resume` endpoints added
- [ ] `data/resumes/` directory is created on upload
- [ ] `frontend/profile.html` created with upload form and profile display
- [ ] `frontend/js/api.js` updated with `uploadResume()`, `getResume()`, `deleteResume()`
- [ ] Upload → parse → store → retrieve round-trip works end to end

## What's Next
When done, tell Kenneth "Phase 3 complete" and he will give you `04_match_scorer.md`.
