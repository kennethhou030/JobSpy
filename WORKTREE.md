# JobSpy — Project Worktree
### CS/QTM/LING-329 | NLP-Assisted Job Discovery and Application Generation
> Maps every proposal objective to the current codebase and specifies exactly what to build next.

---

## Legend
- ✅ **DONE** — Already fully implemented in JobSpy
- 🟡 **PARTIAL** — Foundation exists; needs extension
- 🔴 **TODO** — Not yet built; implementation plan below

---

## Goal 1 — Aggregate Job Postings from 8 Platforms Concurrently

**Status: ✅ DONE**

### What's Already Built
- `jobspy/__init__.py` → `scrape_jobs()` runs all scrapers via `ThreadPoolExecutor` (true concurrency)
- All 8 platforms implemented: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs, Bayt, Naukri, BDJobs
- Location-aware platform selection already noted in proposal — **partially done**: Naukri/BDJobs/Bayt scrapers exist and are selected by `site_name` param
- Normalization into unified `JobPost` schema with 34 fields — done in `jobspy/model.py`
- Database persistence (SQLite/PostgreSQL) via SQLAlchemy — done in `jobspy/database.py`
- REST API to trigger scrapes: `POST /api/scrape` — done in `api/main.py`
- Frontend scraper control page: `frontend/scraper.html`

### What Still Needs Doing
- **Automatic location-aware platform selection** — currently the user manually selects which sites to scrape. Add logic in `api/main.py` or a new `platform_selector.py` that auto-includes Naukri if location contains India, Bayt if location is Middle East, BDJobs if Bangladesh. Small helper function, ~30 lines.

```python
# New file: jobspy/platform_selector.py
REGION_PLATFORM_MAP = {
    "india": ["naukri"],
    "middle east": ["bayt"],
    "uae": ["bayt"],
    "bangladesh": ["bdjobs"],
    "us": ["linkedin", "indeed", "glassdoor", "ziprecruiter", "google"],
}
def select_platforms(location: str) -> list[str]:
    location_lower = location.lower()
    platforms = set(["linkedin", "indeed", "glassdoor", "google"])
    for region, extras in REGION_PLATFORM_MAP.items():
        if region in location_lower:
            platforms.update(extras)
    return list(platforms)
```

- **Files to touch:** `api/main.py` (import + call `select_platforms`), new `jobspy/platform_selector.py`

---

## Goal 2 — Extract Structured Information from Job Descriptions (Skills, Job Type)

**Status: 🟡 PARTIAL**

### What's Already Built
- `job_type` — fully extracted and normalized across all platforms (40+ language mappings in `jobspy/util.py`)
- `salary` — extracted from both direct API data and regex from description text
- `is_remote` — detected from title + description + location keywords
- `emails` — regex-extracted from descriptions
- `skills` — extracted natively from **Naukri only** (via their API response)
- `description` stored in markdown/html/plain for downstream use

### What Needs to Be Built

#### 2A — NLP Skill Extraction from Description Text (spaCy)
The proposal calls for extracting required/preferred skills from job description text for ALL platforms (not just Naukri). This is the core NLP component for the class.

**Implementation Plan:**
1. Create `jobspy/nlp/skill_extractor.py`
2. Use spaCy `en_core_web_sm` or `en_core_web_md` model
3. Maintain a curated skills taxonomy (tech skills list — can use ESCO, O*NET, or a custom CSV)
4. Match skills from description against taxonomy using spaCy `PhraseMatcher`
5. Separate **required** (appears near "required", "must have", "you will need") vs **preferred** (appears near "preferred", "nice to have", "bonus")

```python
# jobspy/nlp/skill_extractor.py
import spacy
from spacy.matcher import PhraseMatcher

nlp = spacy.load("en_core_web_sm")

def extract_skills(description: str, skill_taxonomy: list[str]) -> dict:
    doc = nlp(description)
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    patterns = [nlp.make_doc(skill) for skill in skill_taxonomy]
    matcher.add("SKILLS", patterns)
    matches = matcher(doc)
    found_skills = {doc[start:end].text for _, start, end in matches}

    required, preferred = [], []
    for skill in found_skills:
        context = _get_context(doc, skill)
        if any(kw in context for kw in ["required", "must", "need"]):
            required.append(skill)
        else:
            preferred.append(skill)
    return {"required": required, "preferred": preferred}
```

6. Call `extract_skills()` in `jobspy/__init__.py` after scraping, store in new DB columns
7. Add `required_skills` and `preferred_skills` columns to `jobs` table in `jobspy/database.py`
8. Expose these fields in `api/main.py` response schema

**Files to touch:** `jobspy/model.py`, `jobspy/database.py`, `jobspy/__init__.py`, `api/schemas.py`, new `jobspy/nlp/skill_extractor.py`, new `data/skills_taxonomy.csv`

---

## Goal 3 — Parse and Persistently Store User Resumes

**Status: 🔴 TODO**

### What Needs to Be Built

This is a brand new module. The proposal specifies: upload once, store persistently, parse with spaCy, reuse across all applications.

#### 3A — Resume Upload API Endpoint
Add `POST /api/resume/upload` to `api/main.py` that:
- Accepts PDF or DOCX file upload
- Saves file to disk at `data/resumes/{user_id}/resume.pdf`
- Triggers parsing pipeline
- Returns parsed profile JSON

#### 3B — Resume Parser (spaCy NLP)
Create `jobspy/nlp/resume_parser.py`:

```python
# jobspy/nlp/resume_parser.py
import spacy
from pypdf import PdfReader  # or python-docx for .docx
import re

nlp = spacy.load("en_core_web_md")

def parse_resume(file_path: str) -> dict:
    text = extract_text(file_path)  # handles PDF + DOCX
    doc = nlp(text)
    return {
        "raw_text": text,
        "skills": extract_skills_from_text(text),
        "education": extract_education(doc),
        "experience_years": estimate_experience(text),
        "name": extract_name(doc),
        "email": extract_email(text),
        "phone": extract_phone(text),
        "summary": extract_summary(text),
    }

def extract_text(path: str) -> str:
    if path.endswith(".pdf"):
        reader = PdfReader(path)
        return " ".join(page.extract_text() for page in reader.pages)
    elif path.endswith(".docx"):
        from docx import Document
        doc = Document(path)
        return " ".join(p.text for p in doc.paragraphs)
```

#### 3C — Resume Database Table
Add to `jobspy/database.py`:

```python
class ResumeProfile(Base):
    __tablename__ = "resume_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, unique=True, index=True)  # for MVP: single user; expand later
    file_path = Column(String)         # path to original file
    raw_text = Column(Text)            # full extracted text
    parsed_skills = Column(JSON)       # list of extracted skills
    education = Column(JSON)           # list of education entries
    experience_years = Column(Float)   # estimated years of experience
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    summary = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

#### 3D — Frontend Resume Upload UI
Add a "Profile" page (`frontend/profile.html`) with:
- Drag-and-drop file upload zone (PDF/DOCX)
- Parsed skills display with edit capability
- "Update Resume" button for re-upload

**Files to create:** `jobspy/nlp/resume_parser.py`, `frontend/profile.html`
**Files to touch:** `jobspy/database.py`, `api/main.py`, `api/schemas.py`, `frontend/js/api.js`

---

## Goal 4 — Compute Semantic Match Score Between Resume and Job Postings

**Status: 🔴 TODO**

### What Needs to Be Built

The proposal specifies: cosine similarity over TF-IDF vectors of resume skills vs. job requirements, weighted to prioritize required over preferred skills (score 0–100%).

#### 4A — Match Scorer
Create `jobspy/nlp/match_scorer.py`:

```python
# jobspy/nlp/match_scorer.py
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def compute_match_score(
    resume_skills: list[str],
    job_required_skills: list[str],
    job_preferred_skills: list[str],
    required_weight: float = 0.7,
    preferred_weight: float = 0.3,
) -> float:
    """
    Returns a match score 0.0 to 100.0.
    Required skills weighted at 70%, preferred at 30%.
    """
    resume_text = " ".join(resume_skills)
    required_text = " ".join(job_required_skills)
    preferred_text = " ".join(job_preferred_skills)

    def sim(a: str, b: str) -> float:
        if not a.strip() or not b.strip():
            return 0.0
        vect = TfidfVectorizer()
        tfidf = vect.fit_transform([a, b])
        return float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])

    req_score = sim(resume_text, required_text)
    pref_score = sim(resume_text, preferred_text)
    weighted = (req_score * required_weight) + (pref_score * preferred_weight)
    return round(weighted * 100, 1)
```

#### 4B — Integrate Score into Job Query Pipeline
- After a user has an uploaded resume, every `GET /api/jobs` response should include `match_score` per job
- Add `match_score` as a computed (non-stored) field in the API response — calculated on the fly from the stored resume profile
- Add `sort_by=match_score` option to `GET /api/jobs` query params
- Store match scores in a separate `job_match_scores` table for caching (avoid recomputing every request)

#### 4C — Frontend Match Score Display
- Add a `Match %` column to the jobs table in `frontend/index.html`
- Color-coded badge: green (≥75%), yellow (50–74%), red (<50%)
- Add "Sort by Match" toggle in the filter sidebar

**Files to create:** `jobspy/nlp/match_scorer.py`
**Files to touch:** `api/main.py`, `api/schemas.py`, `jobspy/database.py`, `frontend/index.html`, `frontend/js/api.js`

---

## Goal 5 — Skill Gap Analysis

**Status: 🔴 TODO**

### What Needs to Be Built

Show job seekers exactly which skills they are missing for each job — "Missing skills: Kubernetes, Terraform, CI/CD".

#### 5A — Skill Gap Calculator
Add to `jobspy/nlp/match_scorer.py` (or a new `skill_gap.py`):

```python
def compute_skill_gap(
    resume_skills: list[str],
    job_required_skills: list[str],
    job_preferred_skills: list[str],
) -> dict:
    resume_set = {s.lower() for s in resume_skills}
    missing_required = [s for s in job_required_skills if s.lower() not in resume_set]
    missing_preferred = [s for s in job_preferred_skills if s.lower() not in resume_set]
    matched = [s for s in job_required_skills if s.lower() in resume_set]
    return {
        "missing_required": missing_required,
        "missing_preferred": missing_preferred,
        "matched": matched,
    }
```

#### 5B — API Response Extension
Include `skill_gap` in the `GET /api/jobs/{job_id}` response payload alongside `match_score`.

#### 5C — Frontend Skill Gap UI
In the job detail right panel (already exists in `frontend/index.html`):
- Add a "Skill Gap" section below the job description
- Show green checkmarks for matched skills, red X marks for missing required skills, orange dashes for missing preferred

**Files to touch:** `jobspy/nlp/match_scorer.py` or new `jobspy/nlp/skill_gap.py`, `api/schemas.py`, `api/main.py`, `frontend/index.html`

---

## Goal 6 — Cover Letter Generation (Claude API, Resume-Grounded)

**Status: 🔴 TODO**

### What Needs to Be Built

The proposal specifies: resume stored once → combined with specific job description → passed to Claude API → tailored cover letter output. Key differentiator from ChatGPT: no manual copy-paste, automatic grounding.

#### 6A — Cover Letter Generator
Create `jobspy/nlp/cover_letter.py`:

```python
# jobspy/nlp/cover_letter.py
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

COVER_LETTER_PROMPT = """
You are a professional career writer. Generate a tailored, professional cover letter.

CANDIDATE RESUME SUMMARY:
{resume_summary}

Candidate Skills: {resume_skills}
Years of Experience: {experience_years}

TARGET JOB:
Title: {job_title}
Company: {company_name}
Required Skills: {required_skills}
Preferred Skills: {preferred_skills}

Job Description:
{job_description}

INSTRUCTIONS:
- Write a 3-4 paragraph cover letter (opening, skills alignment, culture fit, closing)
- Reference specific skills from the resume that match the job requirements
- Mention the company name and role title naturally
- Address skill gaps constructively if any
- Professional tone, first-person voice
- Do NOT invent credentials not in the resume
- Output only the cover letter text, no preamble
"""

def generate_cover_letter(
    resume: dict,   # parsed resume profile from DB
    job: dict,      # job record from DB
) -> str:
    prompt = COVER_LETTER_PROMPT.format(
        resume_summary=resume["summary"],
        resume_skills=", ".join(resume["parsed_skills"]),
        experience_years=resume["experience_years"],
        job_title=job["title"],
        company_name=job["company"],
        required_skills=", ".join(job.get("required_skills", [])),
        preferred_skills=", ".join(job.get("preferred_skills", [])),
        job_description=job["description"][:3000],  # truncate for token limit
    )
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text
```

#### 6B — Cover Letter API Endpoint
Add to `api/main.py`:
```
POST /api/cover-letter/{job_id}
  → Loads resume from DB
  → Loads job from DB
  → Calls generate_cover_letter()
  → Returns { cover_letter: str }
  → Optionally saves to cover_letters table
```

#### 6C — Cover Letters Database Table
```python
class CoverLetter(Base):
    __tablename__ = "cover_letters"
    id = Column(Integer, primary_key=True)
    job_id = Column(String, ForeignKey("jobs.id"))
    user_id = Column(String)
    cover_letter_text = Column(Text)
    generated_at = Column(DateTime, default=datetime.utcnow)
```

#### 6D — Frontend Cover Letter UI
In the job detail panel (`frontend/index.html`):
- "Generate Cover Letter" button per job card
- Spinner while Claude API call runs
- Display rendered cover letter text in a modal or expandable panel
- "Copy to Clipboard" and "Download as PDF" buttons

**Dependencies to add to `pyproject.toml`:** `anthropic`
**Files to create:** `jobspy/nlp/cover_letter.py`
**Files to touch:** `api/main.py`, `api/schemas.py`, `jobspy/database.py`, `frontend/index.html`, `frontend/js/api.js`

---

## Goal 7 — Unified User-Facing Web Application

**Status: 🟡 PARTIAL**

### What's Already Built
- 3-page frontend: Dashboard (`index.html`), Scraper control (`scraper.html`), Session history (`history.html`)
- Shared API client `frontend/js/api.js` with `window.API` and `window.fmt`
- FastAPI backend with REST API
- Tailwind CSS (CDN), Google Fonts, responsive 3-column layout

### What Needs to Be Added

#### 7A — Profile / Resume Page (new)
`frontend/profile.html` — resume upload, parsed skills view, edit profile
- Navigation link from all pages
- Shows current resume status (uploaded / not uploaded)
- Displays parsed skills, experience, education for review

#### 7B — Enhanced Dashboard (index.html updates)
- Match Score column in jobs table (requires resume to be uploaded)
- Skill gap panel in job detail view
- "Generate Cover Letter" button in job detail view
- Resume upload prompt/banner if no resume uploaded yet

#### 7C — Applications Tracker Page (new, stretch goal)
`frontend/applications.html` — tracks which jobs had cover letters generated, manual status updates (Applied / Interview / Rejected / Offer)

#### 7D — Navigation Bar (shared across all pages)
Currently no shared nav. Add a consistent nav component linking: Dashboard | Scraper | Profile | History | Applications

---

## Evaluation Plan (from Proposal Section 3.2)

### Job Matching Evaluation
- **Task:** Collect 50–100 job postings, manually label relevance (relevant / partial / irrelevant) against a test resume
- **Metrics:** Accuracy, Precision, Recall, F1-score, Precision@K
- **Implementation:** Create `evaluation/match_eval.py` that loads labeled test set, runs `compute_match_score()`, outputs metrics via sklearn

### Cover Letter Evaluation
- **Task:** 5 human reviewers rate generated letters 1–5 Likert across: relevance, fluency, professionalism, groundedness
- **Implementation:** Create `evaluation/cover_letter_eval.py` that generates cover letters for a batch of test jobs, exports them to a Google Form or simple HTML review interface for raters

### Temporal Dataset
- The `scrape_sessions` + `jobs` table with `first_seen_at` / `last_seen_at` columns already supports longitudinal tracking
- Add a daily scheduled scrape (cron job or simple script) to build the dataset over time: `scripts/daily_scrape.py`

---

## Implementation Order (Week-by-Week per Proposal Timeline)

| Week | Goal(s) | Deliverable |
|------|---------|-------------|
| Week 1 | Setup | Repo, dependencies, this worktree |
| Week 2 | Goal 1 (platform selector) + Goal 2 (skill extraction) | `platform_selector.py`, `skill_extractor.py`, updated DB schema |
| Week 3 | Goal 3 (resume parsing) | `resume_parser.py`, `ResumeProfile` table, `/api/resume/upload`, `profile.html` |
| Week 4 | Goals 4+5 (match scoring + skill gap) + Goal 6 (cover letter) | `match_scorer.py`, `cover_letter.py`, `/api/cover-letter/{job_id}` |
| Week 5 | Goal 7 (frontend integration) | Match score column, skill gap UI, cover letter button, nav bar |
| Week 6 | Evaluation | Evaluation scripts, human review setup, demo |
| Week 7 | Report | Final writeup |

---

## File Map — New Files to Create

```
JobSpy/
├── jobspy/
│   ├── platform_selector.py        ← Goal 1 (auto location-aware platform selection)
│   └── nlp/
│       ├── __init__.py
│       ├── skill_extractor.py      ← Goal 2 (spaCy skill NER from descriptions)
│       ├── resume_parser.py        ← Goal 3 (resume PDF/DOCX parsing)
│       ├── match_scorer.py         ← Goals 4+5 (TF-IDF cosine match + skill gap)
│       └── cover_letter.py         ← Goal 6 (Claude API cover letter generation)
├── data/
│   ├── skills_taxonomy.csv         ← Goal 2 (curated skills list for PhraseMatcher)
│   └── resumes/                    ← Goal 3 (uploaded resume storage)
├── evaluation/
│   ├── match_eval.py               ← Evaluation: match scoring metrics
│   └── cover_letter_eval.py        ← Evaluation: cover letter batch generation
├── scripts/
│   └── daily_scrape.py             ← Temporal dataset builder (cron job)
└── frontend/
    ├── profile.html                ← Goal 3+7 (resume upload & profile view)
    └── applications.html           ← Goal 7 (applications tracker, stretch goal)
```

## Files to Modify

```
JobSpy/
├── jobspy/
│   ├── __init__.py         ← Call skill_extractor after scrape, call platform_selector
│   ├── model.py            ← Add required_skills, preferred_skills fields to JobPost
│   └── database.py         ← Add ResumeProfile, CoverLetter tables; new columns on jobs
├── api/
│   ├── main.py             ← New endpoints: /resume/upload, /cover-letter/{job_id}
│   └── schemas.py          ← Add match_score, skill_gap, required_skills to responses
├── frontend/
│   ├── index.html          ← Match score column, skill gap panel, cover letter button
│   ├── scraper.html        ← Minor: location-aware platform auto-check
│   └── js/api.js           ← New API calls: uploadResume(), generateCoverLetter()
└── pyproject.toml          ← Add: anthropic, spacy, scikit-learn, pypdf, python-docx
```

---

## Key Dependencies to Add

| Package | Purpose | Install |
|---------|---------|---------|
| `anthropic` | Claude API for cover letter generation | `pip install anthropic` |
| `spacy` + `en_core_web_md` | Resume parsing + skill extraction NER | `pip install spacy && python -m spacy download en_core_web_md` |
| `scikit-learn` | TF-IDF vectorization + cosine similarity for match scoring | `pip install scikit-learn` |
| `pypdf` | Resume PDF text extraction | `pip install pypdf` |
| `python-docx` | Resume DOCX text extraction | `pip install python-docx` |

---

*Generated from proposal: "JobSpy: NLP-Assisted Job Discovery and Application Generation" — CS/QTM/LING-329*
*Authors: Yida Xu, Miya Fu, Kenneth Hou*
