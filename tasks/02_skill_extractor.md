# Phase 2 — NLP Skill Extraction from Job Descriptions
> Prerequisite: Phases 0 and 1 must be complete.

## Context
The proposal's core NLP contribution is extracting **required** and **preferred** skills from job description text for all 8 platforms using spaCy. Currently, only Naukri returns skills natively from its API. This phase adds a universal NLP skill extractor using spaCy's `PhraseMatcher` against the `data/skills_taxonomy.csv` built in Phase 0.

The extracted skills feed directly into:
- Phase 4 (match scoring — cosine similarity of resume skills vs. job skills)
- Phase 5 (cover letter generation — tells Claude which skills to highlight)
- Frontend skill gap display

---

## Your Job in This Phase
1. Create `jobspy/nlp/skill_extractor.py`
2. Add `required_skills` and `preferred_skills` columns to the `jobs` DB table
3. Update `jobspy/model.py` `JobPost` to carry these fields
4. Call the extractor inside `jobspy/__init__.py` after each scrape
5. Expose the fields in `api/schemas.py` and `api/main.py`

---

## Step 1 — Read These Files First
- `jobspy/model.py` — understand `JobPost` BaseModel; you will add two fields
- `jobspy/database.py` — understand the `Job` SQLAlchemy model; you will add two columns
- `jobspy/__init__.py` — understand where jobs are post-processed after scraping; this is where you'll call the extractor
- `api/schemas.py` — understand `JobResponse` or equivalent response schema; add the new fields here

---

## Step 2 — Create `jobspy/nlp/skill_extractor.py`

```python
"""
skill_extractor.py
Extracts required and preferred skills from job description text using
spaCy PhraseMatcher against a curated skills taxonomy CSV.
"""

from __future__ import annotations
import csv
import re
from pathlib import Path
from functools import lru_cache

import spacy
from spacy.matcher import PhraseMatcher

# Path to the skills taxonomy (populated in Phase 0)
TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "skills_taxonomy.csv"

# Context windows: keywords that indicate a skill is "required" vs "preferred"
REQUIRED_SIGNALS = [
    "required", "must have", "must-have", "you must", "you will need",
    "mandatory", "essential", "minimum requirement", "you need", "requires",
    "expected to have", "need to have",
]
PREFERRED_SIGNALS = [
    "preferred", "nice to have", "nice-to-have", "bonus", "plus", "ideally",
    "desired", "advantageous", "would be great", "good to have", "optional",
    "a plus", "welcomed",
]


@lru_cache(maxsize=1)
def _load_nlp_and_matcher() -> tuple:
    """
    Load spaCy model and build PhraseMatcher from the skills taxonomy.
    Cached so we only do this once per process.
    """
    nlp = spacy.load("en_core_web_md")

    skills = _load_skills_taxonomy()
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    patterns = [nlp.make_doc(skill.lower()) for skill in skills]
    matcher.add("SKILL", patterns)

    return nlp, matcher, skills


def _load_skills_taxonomy() -> list[str]:
    """Load skills list from the CSV taxonomy file."""
    if not TAXONOMY_PATH.exists():
        raise FileNotFoundError(
            f"Skills taxonomy not found at {TAXONOMY_PATH}. "
            "Please run Phase 0 setup first."
        )
    skills = []
    with open(TAXONOMY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skill = row.get("skill", "").strip()
            if skill:
                skills.append(skill)
    return skills


def _get_section_signal(text: str, skill_start: int, window: int = 300) -> str:
    """
    Look at the surrounding text window around the skill mention.
    Returns 'required', 'preferred', or 'unknown'.
    """
    # Look backwards up to `window` chars for section headers
    context_before = text[max(0, skill_start - window): skill_start].lower()

    # Check for section boundaries — find the last section heading
    # If the most recent section keyword is "required", classify as required
    last_required_pos = max(
        (context_before.rfind(sig) for sig in REQUIRED_SIGNALS), default=-1
    )
    last_preferred_pos = max(
        (context_before.rfind(sig) for sig in PREFERRED_SIGNALS), default=-1
    )

    if last_required_pos == -1 and last_preferred_pos == -1:
        return "required"  # default: treat as required if no signal found

    if last_required_pos >= last_preferred_pos:
        return "required"
    return "preferred"


def extract_skills(description: str) -> dict[str, list[str]]:
    """
    Extract required and preferred skills from a job description string.

    Args:
        description: Raw job description text (markdown or plain text)

    Returns:
        {
            "required": ["Python", "SQL", ...],
            "preferred": ["Kubernetes", "Terraform", ...]
        }
    """
    if not description or not description.strip():
        return {"required": [], "preferred": []}

    # Strip markdown formatting for cleaner NLP
    clean_text = re.sub(r"[#*`>\[\]()_~]", " ", description)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    nlp, matcher, _ = _load_nlp_and_matcher()
    doc = nlp(clean_text)
    matches = matcher(doc)

    required: list[str] = []
    preferred: list[str] = []
    seen: set[str] = set()

    for match_id, start, end in matches:
        span = doc[start:end]
        skill_text = span.text  # original casing
        skill_lower = skill_text.lower()

        if skill_lower in seen:
            continue
        seen.add(skill_lower)

        char_start = span.start_char
        signal = _get_section_signal(clean_text, char_start)

        if signal == "preferred":
            preferred.append(skill_text)
        else:
            required.append(skill_text)

    return {
        "required": sorted(set(required)),
        "preferred": sorted(set(preferred)),
    }


def extract_skills_bulk(jobs: list[dict]) -> list[dict]:
    """
    Run skill extraction on a list of job dicts.
    Each dict must have a 'description' key.
    Returns the same list with 'required_skills' and 'preferred_skills' added.
    """
    for job in jobs:
        description = job.get("description") or ""
        skills = extract_skills(description)
        job["required_skills"] = skills["required"]
        job["preferred_skills"] = skills["preferred"]
    return jobs
```

---

## Step 3 — Update `jobspy/model.py`

Find the `JobPost` class (Pydantic BaseModel). Add these two optional fields. Place them near the other list fields like `emails`:

```python
required_skills: list[str] = []
preferred_skills: list[str] = []
```

Note: `skills` (from Naukri API) already exists as a separate field — **do not remove it**. The new fields are separate: `required_skills` and `preferred_skills` come from NLP extraction and apply to ALL platforms.

---

## Step 4 — Update `jobspy/database.py`

Find the `Job` SQLAlchemy model class. Add two new columns. Place them near the `emails` column:

```python
from sqlalchemy import JSON  # add this import if not already present

# Inside the Job class:
required_skills = Column(JSON, nullable=True)    # list of required skills (NLP-extracted)
preferred_skills = Column(JSON, nullable=True)   # list of preferred skills (NLP-extracted)
```

Then find the `save_jobs()` function (or equivalent upsert logic). Look at how other list/JSON fields are stored (like `emails`). Add `required_skills` and `preferred_skills` to the same upsert mapping.

**IMPORTANT:** After adding the columns, you need to handle the DB migration. The simplest approach for SQLite development: drop and recreate the table by deleting `jobs.db` (if it exists) and restarting the app. The schema is recreated automatically via `Base.metadata.create_all(engine)`.

```bash
rm -f jobs.db  # only do this in development
```

---

## Step 5 — Update `jobspy/__init__.py`

Find the `scrape_jobs()` function. After all jobs are scraped and assembled into the DataFrame (but before returning), call the skill extractor on each job's description.

Add the import at the top of the file:
```python
from jobspy.nlp.skill_extractor import extract_skills
```

Find the loop or section where individual `JobPost` objects are being built or post-processed. For each job, add:

```python
# NLP skill extraction — runs on every job from every platform
if job.description:
    skills_result = extract_skills(job.description)
    job.required_skills = skills_result["required"]
    job.preferred_skills = skills_result["preferred"]
```

**Performance note:** spaCy is loaded once (cached via `@lru_cache` in `skill_extractor.py`), so this won't be slow after the first job. The `en_core_web_md` model processes ~10k words/sec.

---

## Step 6 — Update `api/schemas.py`

Find the response schema that represents a job (likely called `JobOut`, `JobResponse`, or similar). Add:

```python
required_skills: list[str] = []
preferred_skills: list[str] = []
```

These need to map to the new DB columns so the API returns them in every job response.

---

## Step 7 — Update `api/main.py`

In the `GET /api/jobs/{job_id}` and `GET /api/jobs` endpoints, confirm that `required_skills` and `preferred_skills` are included in the job serialization. If the endpoints use `.dict()` or `model_validate` from SQLAlchemy rows, the new fields should flow through automatically once added to both the DB model and schema.

---

## Step 8 — Test It

Create and run `tasks/test_skill_extractor.py`:

```python
from jobspy.nlp.skill_extractor import extract_skills

# Test 1: Required skills extraction
desc1 = """
Requirements:
- Python required
- SQL required
- Must have experience with Docker
- React is required

Preferred:
- Kubernetes nice to have
- Terraform preferred
"""
result = extract_skills(desc1)
print("Test 1 - Required:", result["required"])
print("Test 1 - Preferred:", result["preferred"])
assert "Python" in result["required"] or "python" in [s.lower() for s in result["required"]]
assert len(result["required"]) > 0
print("Test 1 passed\n")

# Test 2: Empty description
result2 = extract_skills("")
assert result2 == {"required": [], "preferred": []}
print("Test 2 passed (empty description)\n")

# Test 3: Description with no recognized skills
result3 = extract_skills("We are a great team looking for a motivated individual.")
print("Test 3 - Skills from generic text:", result3)
print("Test 3 passed\n")

print("All skill extractor tests passed!")
```

Run:
```bash
cd /path/to/JobSpy && python tasks/test_skill_extractor.py
```

---

## Step 9 — End-to-End Smoke Test

Start the server, trigger a small scrape (1-2 results from LinkedIn), then fetch the job via `GET /api/jobs/{job_id}` and confirm `required_skills` and `preferred_skills` appear in the response JSON.

---

## Completion Checklist
- [ ] `jobspy/nlp/skill_extractor.py` created and passes all unit tests
- [ ] `required_skills` and `preferred_skills` fields added to `JobPost` in `model.py`
- [ ] `required_skills` and `preferred_skills` columns added to `Job` in `database.py`
- [ ] Skill extraction called inside `scrape_jobs()` in `__init__.py`
- [ ] `api/schemas.py` response schema includes both new fields
- [ ] `GET /api/jobs/{job_id}` response includes `required_skills` and `preferred_skills`
- [ ] Server starts and scrape runs without errors

## What's Next
When done, tell Kenneth "Phase 2 complete" and he will give you `03_resume_parser.md`.
