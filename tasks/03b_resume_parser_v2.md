# Phase 3B — Resume Parser v2 (Production-Grade)
> **Context:** All previous phases (00–07) are already implemented and running.
> Feed this file to Claude Code now as a targeted upgrade — it replaces `resume_parser.py`,
> safely migrates the existing DB, and adds frontend display for the parsed resume fields.
>
> Three things happen in this phase:
> 1. `jobspy/nlp/resume_parser.py` — full rewrite with robust section detection
> 2. `jobspy/database.py` — safe ALTER TABLE migration (no data loss)
> 3. `frontend/profile.html` + `api/main.py` — display experience, skills, volunteer, projects

## Why v2
The Phase 3 parser used basic spaCy NER and naive text splitting. Research into
real-world resume formats revealed three critical gaps:

1. **Section detection was too brittle** — only ~5 header keywords, missing 80%+ of
   real-world variations ("Areas of Expertise", "What I Bring", "Civic Engagement", etc.)
2. **Work history parsing ignored date anchors** — the most reliable signal for segmenting
   individual job entries is the date range pattern, not line counting
3. **Skill extraction was redundant with Phase 2** — the parser should reuse
   `skill_extractor.py` rather than running its own ad-hoc extraction

This v2 uses a **3-layer architecture**:
- Layer 1: Full synonym-based section boundary detection (state machine)
- Layer 2: Date-anchor segmentation inside experience/project sections
- Layer 3: Structural fallback (ALL-CAPS line = header) for unrecognized headings

---

## Step 1 — Read These Files Before Writing Anything

1. `jobspy/nlp/skill_extractor.py` — you will import `extract_skills()` from here,
   do NOT reimplement skill extraction
2. `jobspy/database.py` — `ResumeProfile` table, `save_resume_profile()` — the dict
   keys you return must match the column names exactly
3. `api/main.py` — `POST /api/resume/upload` calls `parse_resume(file_path)` and
   passes the result dict directly to `save_resume_profile()` — don't break that contract

**The function signature to preserve (other files depend on it):**
```python
def parse_resume(file_path: str) -> dict:
    ...
    return {
        "raw_text":        str,
        "name":            str | None,
        "email":           str | None,
        "phone":           str | None,
        "parsed_skills":   list[str],
        "education":       list[dict],
        "experience_years": float,
        "summary":         str,
        # NEW in v2 — add these columns to ResumeProfile if not present:
        "work_experience": list[dict],   # structured job entries
        "projects":        list[dict],   # structured project entries
        "volunteer":       list[dict],   # structured volunteer entries
        "certifications":  list[str],    # cert/license names
        "languages":       list[str],    # spoken languages
        "raw_sections":    dict,         # {section_name: raw_text} for debugging
    }
```

**DB schema change**: Open `jobspy/database.py` and add these columns to `ResumeProfile`
if they don't already exist. Use `JSON` type for all list/dict fields:
```python
work_experience  = Column(JSON, nullable=True)
projects         = Column(JSON, nullable=True)
volunteer        = Column(JSON, nullable=True)
certifications   = Column(JSON, nullable=True)
languages        = Column(JSON, nullable=True)
raw_sections     = Column(JSON, nullable=True)
```
After adding: `rm -f jobs.db` and restart to recreate the schema.

---

## Step 2 — Full Implementation of `jobspy/nlp/resume_parser.py`

Rewrite the entire file with this implementation:

```python
"""
resume_parser.py  — v2
Production-grade resume parser using a 3-layer detection system:
  Layer 1: Comprehensive synonym-based section boundary detection (state machine)
  Layer 2: Date-anchor segmentation for experience/project entries
  Layer 3: ALL-CAPS / Title-Case structural fallback for unrecognized headings

Supports PDF and DOCX input.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import NamedTuple

import spacy

from jobspy.nlp.skill_extractor import extract_skills  # reuse Phase 2 extractor


# ─────────────────────────────────────────────
# SECTION SYNONYM MASTER TABLE
# Maps every known heading variation → canonical section name.
# Keys are lowercase, stripped of punctuation.
# Extend this list freely — the parser checks every key via startswith + exact match.
# ─────────────────────────────────────────────

SECTION_SYNONYMS: dict[str, str] = {

    # ── SUMMARY / OBJECTIVE ──────────────────────────────────────────────────
    "summary":                          "summary",
    "professional summary":             "summary",
    "career summary":                   "summary",
    "executive summary":                "summary",
    "profile":                          "summary",
    "professional profile":             "summary",
    "career profile":                   "summary",
    "objective":                        "summary",
    "career objective":                 "summary",
    "professional objective":           "summary",
    "personal statement":               "summary",
    "statement of purpose":             "summary",
    "about me":                         "summary",
    "about":                            "summary",
    "overview":                         "summary",
    "highlights":                       "summary",
    "career highlights":                "summary",
    "professional highlights":          "summary",
    "qualifications summary":           "summary",
    "summary of qualifications":        "summary",
    "snapshot":                         "summary",
    "at a glance":                      "summary",
    "background":                       "summary",
    "bio":                              "summary",
    "brief bio":                        "summary",

    # ── SKILLS ───────────────────────────────────────────────────────────────
    "skills":                           "skills",
    "technical skills":                 "skills",
    "core competencies":                "skills",
    "key competencies":                 "skills",
    "areas of expertise":               "skills",
    "expertise":                        "skills",
    "proficiencies":                    "skills",
    "professional skills":              "skills",
    "tools and technologies":           "skills",
    "tools & technologies":             "skills",
    "tech stack":                       "skills",
    "technologies":                     "skills",
    "key skills":                       "skills",
    "skills and abilities":             "skills",
    "skills & abilities":               "skills",
    "abilities":                        "skills",
    "strengths":                        "skills",
    "qualifications":                   "skills",
    "industry knowledge":               "skills",
    "relevant skills":                  "skills",
    "specialized skills":               "skills",
    "software skills":                  "skills",
    "programming languages":            "skills",
    "languages and frameworks":         "skills",
    "languages & frameworks":           "skills",
    "hard skills":                      "skills",
    "soft skills":                      "skills",
    "interpersonal skills":             "skills",
    "functional skills":                "skills",
    "competencies":                     "skills",
    "what i bring":                     "skills",
    "my toolkit":                       "skills",
    "technical expertise":              "skills",
    "technical proficiencies":          "skills",
    "core skills":                      "skills",
    "additional skills":                "skills",

    # ── WORK EXPERIENCE ───────────────────────────────────────────────────────
    "experience":                       "experience",
    "work experience":                  "experience",
    "professional experience":          "experience",
    "employment history":               "experience",
    "work history":                     "experience",
    "career history":                   "experience",
    "relevant experience":              "experience",
    "related experience":               "experience",
    "internship experience":            "experience",
    "internships":                      "experience",
    "practical experience":             "experience",
    "career experience":                "experience",
    "leadership experience":            "experience",
    "executive experience":             "experience",
    "consulting experience":            "experience",
    "client work":                      "experience",
    "freelance experience":             "experience",
    "contract work":                    "experience",
    "prior experience":                 "experience",
    "earlier experience":               "experience",
    "positions held":                   "experience",
    "job history":                      "experience",
    "professional background":          "experience",
    "professional history":             "experience",
    "industry experience":              "experience",
    "military experience":              "experience",
    "research experience":              "experience",
    "clinical experience":              "experience",
    "teaching experience":              "experience",
    "academic experience":              "experience",
    "roles":                            "experience",
    "relevant work":                    "experience",
    "employment":                       "experience",
    "work":                             "experience",

    # ── EDUCATION ─────────────────────────────────────────────────────────────
    "education":                        "education",
    "academic background":              "education",
    "educational background":           "education",
    "academic history":                 "education",
    "academic qualifications":          "education",
    "degrees":                          "education",
    "educational qualifications":       "education",
    "schooling":                        "education",
    "academic training":                "education",
    "academic credentials":             "education",
    "graduate studies":                 "education",
    "undergraduate studies":            "education",
    "higher education":                 "education",
    "training and education":           "education",
    "training & education":             "education",
    "education and training":           "education",
    "education & training":             "education",
    "education and certifications":     "education",
    "education & certifications":       "education",
    "coursework":                       "education",
    "relevant coursework":              "education",
    "academic coursework":              "education",

    # ── PROJECTS ──────────────────────────────────────────────────────────────
    "projects":                         "projects",
    "personal projects":                "projects",
    "academic projects":                "projects",
    "key projects":                     "projects",
    "relevant projects":                "projects",
    "selected projects":                "projects",
    "notable projects":                 "projects",
    "technical projects":               "projects",
    "engineering projects":             "projects",
    "software projects":                "projects",
    "open source projects":             "projects",
    "open-source projects":             "projects",
    "research projects":                "projects",
    "side projects":                    "projects",
    "portfolio":                        "projects",
    "independent projects":             "projects",
    "coursework projects":              "projects",
    "capstone project":                 "projects",
    "capstone":                         "projects",
    "thesis project":                   "projects",
    "thesis":                           "projects",
    "class projects":                   "projects",
    "school projects":                  "projects",
    "extracurricular projects":         "projects",
    "pet projects":                     "projects",
    "project work":                     "projects",
    "project highlights":               "projects",

    # ── VOLUNTEER ──────────────────────────────────────────────────────────────
    "volunteer experience":             "volunteer",
    "volunteer work":                   "volunteer",
    "volunteering":                     "volunteer",
    "volunteer":                        "volunteer",
    "community service":                "volunteer",
    "community involvement":            "volunteer",
    "community engagement":             "volunteer",
    "community work":                   "volunteer",
    "civic engagement":                 "volunteer",
    "civic activities":                 "volunteer",
    "extracurricular activities":       "volunteer",
    "extracurricular involvement":      "volunteer",
    "extracurricular":                  "volunteer",
    "social work":                      "volunteer",
    "nonprofit work":                   "volunteer",
    "non-profit work":                  "volunteer",
    "pro bono work":                    "volunteer",
    "pro bono experience":              "volunteer",
    "outreach":                         "volunteer",
    "service":                          "volunteer",
    "philanthropy":                     "volunteer",
    "service work":                     "volunteer",
    "social impact":                    "volunteer",
    "campus involvement":               "volunteer",
    "student involvement":              "volunteer",
    "activities":                       "volunteer",
    "additional activities":            "volunteer",
    "leadership and involvement":       "volunteer",
    "leadership & involvement":         "volunteer",
    "giving back":                      "volunteer",

    # ── CERTIFICATIONS ──────────────────────────────────────────────────────────
    "certifications":                   "certifications",
    "certification":                    "certifications",
    "professional certifications":      "certifications",
    "licenses":                         "certifications",
    "licenses and certifications":      "certifications",
    "licenses & certifications":        "certifications",
    "certifications and licenses":      "certifications",
    "certifications & licenses":        "certifications",
    "credentials":                      "certifications",
    "professional credentials":         "certifications",
    "accreditations":                   "certifications",
    "training and certifications":      "certifications",
    "training & certifications":        "certifications",
    "courses and certifications":       "certifications",
    "courses & certifications":         "certifications",
    "continuing education":             "certifications",
    "professional development":         "certifications",
    "courses":                          "certifications",
    "online courses":                   "certifications",
    "professional training":            "certifications",
    "workshops":                        "certifications",
    "badges":                           "certifications",
    "awards and certifications":        "certifications",
    "awards & certifications":          "certifications",

    # ── LANGUAGES ──────────────────────────────────────────────────────────────
    "languages":                        "languages",
    "language skills":                  "languages",
    "spoken languages":                 "languages",
    "foreign languages":                "languages",
    "language proficiency":             "languages",
    "linguistic skills":                "languages",

    # ── AWARDS / HONORS ─────────────────────────────────────────────────────────
    "awards":                           "awards",
    "honors":                           "awards",
    "honours":                          "awards",
    "achievements":                     "awards",
    "accomplishments":                  "awards",
    "awards and honors":                "awards",
    "awards & honors":                  "awards",
    "recognition":                      "awards",
    "scholarships":                     "awards",
    "fellowships":                      "awards",

    # ── PUBLICATIONS / RESEARCH ─────────────────────────────────────────────────
    "publications":                     "publications",
    "research":                         "publications",
    "research and publications":        "publications",
    "papers":                           "publications",
    "journal articles":                 "publications",
    "conference papers":                "publications",
    "presentations":                    "publications",

    # ── REFERENCES ──────────────────────────────────────────────────────────────
    "references":                       "references",
    "professional references":          "references",
}


# ─────────────────────────────────────────────
# REGEX PATTERNS (all pre-compiled for performance)
# ─────────────────────────────────────────────

# Email — handles dots, plus, subdomains
RE_EMAIL = re.compile(
    r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+"
)

# Phone — US + international formats
RE_PHONE = re.compile(
    r"(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?)(\d{3}[\s.\-]?\d{4})"
)

# Date range — used to anchor individual job/project entries
# Matches: "Jan 2020 – Mar 2022", "2018 - Present", "06/2021 – current", "2019 to 2021"
RE_DATE_RANGE = re.compile(
    r"""
    (?:
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)
        \.?\s+
    )?
    (?:19|20)\d{2}
    \s*[-–—/to]+\s*
    (?:
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)
        \.?\s+
        (?:19|20)\d{2}
        |
        (?:19|20)\d{2}
        |
        present|current|now|ongoing|today
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Standalone year (for experience calculation)
RE_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")

# Degree abbreviations — normalized before parsing
RE_DEGREE = re.compile(
    r"\b(B\.?E\.?|B\.?S\.?|M\.?S\.?|M\.?B\.?A\.?|Ph\.?D\.?|"
    r"B\.?Tech\.?|M\.?Tech\.?|B\.?A\.?|M\.?A\.?|B\.?Sc\.?|M\.?Sc\.?|"
    r"A\.?A\.?S\.?|A\.?S\.?|B\.?B\.?A\.?|D\.?D\.?S\.?|M\.?D\.?|J\.?D\.?|"
    r"Bachelor(?:'s)?|Master(?:'s)?|Doctor(?:ate)?|Associate(?:'s)?)\b",
    re.IGNORECASE,
)

# Section header structural fallback — ALL-CAPS line or short Title-Case line
# Used when no keyword match is found in SECTION_SYNONYMS
RE_HEADER_ALLCAPS = re.compile(r"^[A-Z][A-Z\s&/\-]{2,45}:?\s*$")
RE_HEADER_TITLECASE = re.compile(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}):?\s*$")

# URL extraction
RE_LINKEDIN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-_%]+", re.IGNORECASE
)
RE_GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-_%]+", re.IGNORECASE
)
RE_URL_GENERIC = re.compile(
    r"https?://[^\s,;>)\"']+|www\.[^\s,;>)\"']+"
)

# GPA
RE_GPA = re.compile(
    r"\b(?:GPA|Grade\s+Point\s+Average)[:\s]+(\d\.\d{1,2})\s*/?\s*(\d\.\d{1,2})?",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
# TEXT EXTRACTION
# ─────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from PDF using pdfplumber (preferred — better layout preservation)
    with pypdf as fallback.
    """
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    pages.append(text)
            return "\n".join(pages)
    except ImportError:
        pass  # fall through to pypdf

    from pypdf import PdfReader
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX preserving paragraph breaks."""
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text(file_path: str) -> str:
    """Route to the correct extractor based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use PDF or DOCX.")


def _clean_text(text: str) -> str:
    """
    Normalize raw extracted text before parsing.
    - Collapse excessive whitespace within lines (but preserve line breaks)
    - Remove null bytes and form feeds
    - Normalize unicode dashes and bullets
    """
    # Remove non-printable characters except newlines
    text = re.sub(r"[^\x20-\x7E\n]", lambda m: _normalize_unicode(m.group(0)), text)
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def _normalize_unicode(char: str) -> str:
    """Map common unicode chars to ASCII equivalents."""
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2015": "-",   # dashes
        "\u2018": "'", "\u2019": "'",                   # smart quotes
        "\u201C": '"', "\u201D": '"',
        "\u2022": "-", "\u25A0": "-", "\u25CF": "-",   # bullets
        "\u00A0": " ",                                  # non-breaking space
    }
    return replacements.get(char, " ")


# ─────────────────────────────────────────────
# SECTION DETECTION — STATE MACHINE (Layer 1 + 3)
# ─────────────────────────────────────────────

def _normalize_heading(line: str) -> str:
    """
    Normalize a line for comparison against SECTION_SYNONYMS.
    - Lowercase
    - Strip leading/trailing whitespace
    - Remove trailing colon and punctuation
    - Collapse internal whitespace
    """
    line = line.lower().strip()
    line = re.sub(r"[:\.\!\?]+$", "", line)   # strip trailing : . ! ?
    line = re.sub(r"\s+", " ", line)           # collapse whitespace
    return line


def _is_section_header(line: str) -> tuple[bool, str | None]:
    """
    Determine if a line is a section header.
    Returns (is_header: bool, canonical_name: str | None)

    Detection order:
    1. Exact match in SECTION_SYNONYMS (highest confidence)
    2. startswith match (catches "Work Experience & Internships")
    3. ALL-CAPS structural fallback
    4. Title-Case structural fallback (≤5 words, no verb phrases)
    """
    normalized = _normalize_heading(line)

    # Layer 1a: Exact match
    if normalized in SECTION_SYNONYMS:
        return True, SECTION_SYNONYMS[normalized]

    # Layer 1b: Prefix match (e.g., "skills & tools" starts with "skills")
    for key, canonical in SECTION_SYNONYMS.items():
        if normalized.startswith(key) and len(normalized) <= len(key) + 20:
            return True, canonical

    stripped = line.strip()

    # Layer 3a: ALL-CAPS line
    if RE_HEADER_ALLCAPS.match(stripped):
        # Map it to canonical if we can, else use normalized as-is
        normalized_fallback = _normalize_heading(stripped)
        canonical = SECTION_SYNONYMS.get(normalized_fallback, normalized_fallback)
        return True, canonical

    # Layer 3b: Title-Case line (short, no period, no comma after 2nd word)
    if RE_HEADER_TITLECASE.match(stripped):
        # Extra guard: real section headers rarely contain verbs like "is", "are", "have"
        words = stripped.lower().split()
        if len(words) <= 5 and not any(w in ("is", "are", "was", "were", "have", "the", "a", "an") for w in words):
            normalized_fallback = _normalize_heading(stripped)
            canonical = SECTION_SYNONYMS.get(normalized_fallback, normalized_fallback)
            return True, canonical

    return False, None


def segment_sections(text: str) -> dict[str, str]:
    """
    Split resume text into sections using the state-machine header detector.

    Returns a dict: {canonical_section_name: raw_section_text}
    The special key "header" holds text before the first detected section
    (usually name, contact info, and summary).
    """
    lines = text.splitlines()
    sections: dict[str, list[str]] = {"header": []}
    current_section = "header"

    for line in lines:
        stripped = line.strip()

        # Skip empty lines only at section boundaries
        if not stripped:
            sections.setdefault(current_section, []).append(line)
            continue

        is_header, canonical = _is_section_header(stripped)
        if is_header and canonical:
            current_section = canonical
            sections.setdefault(current_section, [])
            # Don't append the header line itself into the section body
        else:
            sections.setdefault(current_section, []).append(line)

    # Convert lists to strings, strip leading/trailing blank lines per section
    return {
        section: "\n".join(lines).strip()
        for section, lines in sections.items()
        if "\n".join(lines).strip()
    }


# ─────────────────────────────────────────────
# CONTACT INFO EXTRACTION
# ─────────────────────────────────────────────

def extract_email(text: str) -> str | None:
    match = RE_EMAIL.search(text)
    return match.group(0).strip() if match else None


def extract_phone(text: str) -> str | None:
    # Pre-clean: normalize spaces around phone delimiters
    cleaned = re.sub(r"\s*[-.\s]\s*", "-", text)
    match = RE_PHONE.search(cleaned)
    return match.group(0).strip() if match else None


def extract_linkedin(text: str) -> str | None:
    match = RE_LINKEDIN.search(text)
    return match.group(0).strip() if match else None


def extract_github(text: str) -> str | None:
    match = RE_GITHUB.search(text)
    return match.group(0).strip() if match else None


def extract_name(text: str, nlp) -> str | None:
    """
    Extract candidate name using spaCy NER on the first 500 chars (header area).
    Falls back to first non-empty line if no PERSON entity found.
    """
    header_text = text[:500]
    doc = nlp(header_text)

    # Try spaCy PERSON entity first
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip()
            # Filter out clearly wrong extractions (too short, contains @, etc.)
            if len(name) >= 3 and "@" not in name and name.replace(" ", "").isalpha():
                return name

    # Fallback: first non-empty line that looks like a name (2 words, title case)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and 2 <= len(stripped.split()) <= 4:
            words = stripped.split()
            if all(w[0].isupper() and w[1:].islower() for w in words if w.isalpha()):
                return stripped

    return None


# ─────────────────────────────────────────────
# WORK EXPERIENCE PARSING — DATE-ANCHOR STRATEGY (Layer 2)
# ─────────────────────────────────────────────

class JobEntry(NamedTuple):
    title: str | None
    company: str | None
    date_range: str | None
    start_year: int | None
    end_year: int | None
    is_current: bool
    description: str
    raw: str


def _parse_years_from_range(date_range_str: str) -> tuple[int | None, int | None, bool]:
    """
    Extract start year, end year, and is_current from a date range string.
    Examples: "Jan 2020 – Mar 2022" → (2020, 2022, False)
              "2019 – Present"       → (2019, 2024, True)
    """
    import datetime
    current_year = datetime.datetime.now().year
    years = [int(y) for y in RE_YEAR.findall(date_range_str)]
    is_current = bool(re.search(r"present|current|now|ongoing|today", date_range_str, re.I))

    start_year = min(years) if years else None
    end_year = current_year if is_current else (max(years) if years else None)
    return start_year, end_year, is_current


def _split_into_entries(section_text: str) -> list[str]:
    """
    Split experience/project/volunteer section text into individual entries
    using date range patterns as anchors.

    Strategy: find all date range matches → use their positions as split points.
    Everything between two date ranges = one entry.
    """
    if not section_text.strip():
        return []

    # Find all date range positions
    date_matches = list(RE_DATE_RANGE.finditer(section_text))

    if not date_matches:
        # No dates found — fall back to double-newline splitting
        blocks = re.split(r"\n\s*\n", section_text)
        return [b.strip() for b in blocks if b.strip()]

    entries = []
    # Each date range anchors an entry; the entry text starts some lines above it
    for i, match in enumerate(date_matches):
        # Entry start: beginning of the block between previous date match and this one
        entry_start = date_matches[i - 1].end() if i > 0 else 0
        # Entry end: next date match start, or end of text
        entry_end = date_matches[i + 1].start() if i + 1 < len(date_matches) else len(section_text)
        entry_text = section_text[entry_start:entry_end].strip()
        if entry_text:
            entries.append(entry_text)

    return entries


def _parse_single_job_entry(entry_text: str, nlp) -> dict:
    """
    Parse one job entry block into structured fields.
    Lines above the date range = title + company.
    Lines below = description/bullets.
    """
    lines = [l for l in entry_text.splitlines() if l.strip()]
    if not lines:
        return {}

    # Find the date range line
    date_range_str = None
    date_line_idx = None
    for idx, line in enumerate(lines):
        if RE_DATE_RANGE.search(line):
            date_range_str = RE_DATE_RANGE.search(line).group(0)
            date_line_idx = idx
            break

    start_year, end_year, is_current = _parse_years_from_range(date_range_str) if date_range_str else (None, None, False)

    # Title and company are in the line(s) BEFORE the date range
    pre_date_lines = lines[:date_line_idx] if date_line_idx is not None else lines[:2]
    post_date_lines = lines[date_line_idx + 1:] if date_line_idx is not None else lines[2:]

    title, company = None, None
    if pre_date_lines:
        # First pre-date line = job title (usually bold/largest in original PDF)
        title = pre_date_lines[0].strip()
        # Second pre-date line = company name
        if len(pre_date_lines) > 1:
            company = pre_date_lines[1].strip()
        else:
            # Try NER on the title line for ORG entities
            doc = nlp(title)
            orgs = [e.text for e in doc.ents if e.label_ == "ORG"]
            if orgs:
                company = orgs[0]
                # If company and title are the same line, try to split on " at " or " @ "
                for sep in [" at ", " @ ", " — ", " - "]:
                    if sep in title:
                        parts = title.split(sep, 1)
                        title, company = parts[0].strip(), parts[1].strip()
                        break

    description = "\n".join(post_date_lines).strip()

    return {
        "title": title,
        "company": company,
        "date_range": date_range_str,
        "start_year": start_year,
        "end_year": end_year,
        "is_current": is_current,
        "description": description,
    }


def parse_experience_section(section_text: str, nlp) -> list[dict]:
    """Parse the work experience section into a list of structured job entries."""
    entries = _split_into_entries(section_text)
    return [_parse_single_job_entry(e, nlp) for e in entries if e]


def parse_project_section(section_text: str) -> list[dict]:
    """
    Parse the projects section. Each project is a bullet block or double-newline block.
    First line = project name, remaining lines = description.
    """
    # Split on bullet characters or double newlines
    raw_entries = re.split(r"\n(?=[-•*–]|\d+\.|\s*\n)", section_text)
    projects = []
    for entry in raw_entries:
        lines = [l.strip().lstrip("-•*–").strip() for l in entry.splitlines() if l.strip()]
        if not lines:
            continue
        name = lines[0]
        # Try to extract tech stack: look for "Tech:" / "Technologies:" / "Stack:" prefix
        tech = []
        description_lines = []
        for line in lines[1:]:
            tech_match = re.match(r"(?:tech(?:nologies)?|stack|tools?|built with)[:\s]+(.+)", line, re.I)
            if tech_match:
                tech = [t.strip() for t in re.split(r"[,|/]", tech_match.group(1))]
            else:
                description_lines.append(line)
        # Extract date range if present in any line
        date_range = None
        for line in lines:
            m = RE_DATE_RANGE.search(line)
            if m:
                date_range = m.group(0)
                break
        projects.append({
            "name": name,
            "tech": tech,
            "date_range": date_range,
            "description": " ".join(description_lines),
        })
    return projects


def parse_volunteer_section(section_text: str, nlp) -> list[dict]:
    """
    Parse volunteer section — same logic as work experience (date-anchor strategy).
    Volunteer entries often lack formal job titles so we fall back gracefully.
    """
    entries = _split_into_entries(section_text)
    results = []
    for entry in entries:
        parsed = _parse_single_job_entry(entry, nlp)
        if not parsed.get("title"):
            # Use first non-date line as the role description
            lines = [l.strip() for l in entry.splitlines() if l.strip() and not RE_DATE_RANGE.search(l)]
            if lines:
                parsed["title"] = lines[0]
        results.append(parsed)
    return results


# ─────────────────────────────────────────────
# EDUCATION PARSING
# ─────────────────────────────────────────────

def parse_education_section(section_text: str, nlp) -> list[dict]:
    """
    Parse education into structured entries: degree, institution, year, GPA.
    Uses degree regex + NER for institution names.
    """
    if not section_text.strip():
        return []

    entries = _split_into_entries(section_text)
    if not entries:
        entries = [section_text]  # single-entry fallback

    results = []
    for entry in entries:
        degree_match = RE_DEGREE.search(entry)
        gpa_match = RE_GPA.search(entry)
        years = [int(y) for y in RE_YEAR.findall(entry)]

        # Use NER to find the institution name
        doc = nlp(entry[:300])
        orgs = [e.text for e in doc.ents if e.label_ == "ORG"]

        results.append({
            "degree": degree_match.group(0).strip() if degree_match else None,
            "institution": orgs[0] if orgs else None,
            "graduation_year": max(years) if years else None,
            "gpa": float(gpa_match.group(1)) if gpa_match else None,
            "raw": entry[:200],
        })

    return results


# ─────────────────────────────────────────────
# EXPERIENCE YEARS CALCULATION
# ─────────────────────────────────────────────

def calculate_experience_years(work_entries: list[dict], raw_text: str) -> float:
    """
    Calculate total years of experience from parsed work entries.
    Accounts for overlapping date ranges (doesn't double-count concurrent jobs).
    Falls back to earliest-year heuristic if no structured entries.
    """
    import datetime
    current_year = datetime.datetime.now().year

    # Build a list of (start, end) year ranges
    ranges = []
    for entry in work_entries:
        start = entry.get("start_year")
        end = entry.get("end_year") or current_year
        if start and isinstance(start, int) and isinstance(end, int) and start <= end:
            ranges.append((start, end))

    if ranges:
        # Merge overlapping ranges to avoid double-counting
        ranges.sort()
        merged = [ranges[0]]
        for start, end in ranges[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        total = sum(end - start for start, end in merged)
        return float(min(total, 50))  # cap at 50 years

    # Fallback: earliest year in full text
    years = [int(y) for y in RE_YEAR.findall(raw_text)]
    if years:
        earliest = max(min(years), 1990)
        return float(min(current_year - earliest, 50))

    return 0.0


# ─────────────────────────────────────────────
# SUMMARY EXTRACTION
# ─────────────────────────────────────────────

def extract_summary(sections: dict[str, str], raw_text: str) -> str:
    """
    Extract the candidate's professional summary.
    Tries the summary section first, falls back to header area text.
    """
    # Try the detected summary section
    if "summary" in sections:
        return sections["summary"][:600].strip()

    # Try header area (text before first detected section)
    header = sections.get("header", "")
    if header:
        # Skip contact info lines (email, phone, URL lines)
        content_lines = []
        for line in header.splitlines():
            stripped = line.strip()
            if stripped and not RE_EMAIL.search(stripped) and not RE_PHONE.search(stripped) and not RE_URL_GENERIC.search(stripped):
                content_lines.append(stripped)
        if content_lines:
            return " ".join(content_lines[:5])[:600]

    # Last resort: first 500 chars of raw text
    return raw_text[:500].strip()


# ─────────────────────────────────────────────
# CERTIFICATIONS + LANGUAGES (simple list extraction)
# ─────────────────────────────────────────────

def parse_certifications(section_text: str) -> list[str]:
    """Extract certification names as a list (one per line or bullet)."""
    if not section_text.strip():
        return []
    certs = []
    for line in section_text.splitlines():
        cleaned = line.strip().lstrip("-•*–0123456789.").strip()
        if cleaned and len(cleaned) > 3:
            certs.append(cleaned)
    return certs[:20]  # cap at 20


def parse_languages(section_text: str) -> list[str]:
    """Extract spoken languages from the languages section."""
    if not section_text.strip():
        return []
    langs = []
    # Split on commas, newlines, bullets
    items = re.split(r"[,\n•\-–]", section_text)
    for item in items:
        # Strip proficiency levels: "English (Fluent)", "Spanish – B2"
        cleaned = re.sub(r"\(.*?\)|\[.*?\]|[-–].*$", "", item).strip()
        cleaned = cleaned.lstrip("-•*").strip()
        if 2 <= len(cleaned) <= 30 and cleaned.replace(" ", "").isalpha():
            langs.append(cleaned)
    return langs[:15]


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def parse_resume(file_path: str) -> dict:
    """
    Full resume parsing pipeline v2.

    Args:
        file_path: Absolute path to a PDF or DOCX resume file.

    Returns:
        Structured dict with all extracted fields.
        Keys match ResumeProfile DB column names exactly.

    Raises:
        ValueError: If the file cannot be parsed or yields no text.
    """
    # ── Step 1: Extract raw text ──────────────────────────────────────────────
    raw_text = extract_text(file_path)
    if not raw_text.strip():
        raise ValueError(
            "Could not extract any text from this resume. "
            "Make sure it is not a scanned image-only PDF."
        )
    raw_text = _clean_text(raw_text)

    # ── Step 2: Load spaCy (shared instance) ─────────────────────────────────
    nlp = spacy.load("en_core_web_md")

    # ── Step 3: Segment into sections ────────────────────────────────────────
    sections = segment_sections(raw_text)

    # ── Step 4: Extract contact info from full text (not just header) ────────
    name  = extract_name(raw_text, nlp)
    email = extract_email(raw_text)
    phone = extract_phone(raw_text)
    linkedin = extract_linkedin(raw_text)
    github   = extract_github(raw_text)

    # ── Step 5: Parse each section ────────────────────────────────────────────
    work_entries      = parse_experience_section(sections.get("experience", ""), nlp)
    project_entries   = parse_project_section(sections.get("projects", ""))
    volunteer_entries = parse_volunteer_section(sections.get("volunteer", ""), nlp)
    education_entries = parse_education_section(sections.get("education", ""), nlp)
    certifications    = parse_certifications(sections.get("certifications", ""))
    languages         = parse_languages(sections.get("languages", ""))

    # ── Step 6: Skill extraction via Phase 2 extractor (full resume text) ────
    # Combine skills from dedicated section (highest signal) + full text (catches
    # skills embedded in job descriptions)
    skills_from_section  = extract_skills(sections.get("skills", ""))
    skills_from_fulltext = extract_skills(raw_text)
    all_skills = list({
        s.lower(): s for s in
        skills_from_section["required"]
        + skills_from_section["preferred"]
        + skills_from_fulltext["required"]
        + skills_from_fulltext["preferred"]
    }.values())

    # ── Step 7: Calculate years of experience ────────────────────────────────
    experience_years = calculate_experience_years(work_entries, raw_text)

    # ── Step 8: Extract summary ───────────────────────────────────────────────
    summary = extract_summary(sections, raw_text)

    return {
        # Core fields (match ResumeProfile DB columns from Phase 3)
        "raw_text":          raw_text,
        "name":              name,
        "email":             email,
        "phone":             phone,
        "parsed_skills":     all_skills,
        "education":         education_entries,
        "experience_years":  experience_years,
        "summary":           summary,
        # Extended fields (new in v2 — add to ResumeProfile DB if not present)
        "work_experience":   work_entries,
        "projects":          project_entries,
        "volunteer":         volunteer_entries,
        "certifications":    certifications,
        "languages":         languages,
        "linkedin_url":      linkedin,
        "github_url":        github,
        "raw_sections":      {k: v[:500] for k, v in sections.items()},  # truncated for DB
    }
```

---

## Step 3 — Install pdfplumber (Better PDF Extraction)

The v2 parser prefers `pdfplumber` over `pypdf` for layout-aware PDF extraction:

```bash
pip install pdfplumber --break-system-packages
python -c "import pdfplumber; print('pdfplumber OK')"
```

Add to `pyproject.toml`:
```toml
pdfplumber = ">=0.10"
```

---

## Step 4 — Safe DB Migration (NO data loss)

> ⚠️ Do NOT delete `jobs.db`. Previous phases have already populated it.
> Use SQLite `ALTER TABLE` to add new columns to the existing `resume_profiles` table.

### 4A — Add columns to the `ResumeProfile` class in `jobspy/database.py`

Open `database.py`. Find the `ResumeProfile` class. Add these columns **only if they are not already present**:

```python
work_experience  = Column(JSON, nullable=True)   # list[dict] of job entries
projects         = Column(JSON, nullable=True)   # list[dict] of project entries
volunteer        = Column(JSON, nullable=True)   # list[dict] of volunteer entries
certifications   = Column(JSON, nullable=True)   # list[str]
languages        = Column(JSON, nullable=True)   # list[str]
linkedin_url     = Column(String, nullable=True)
github_url       = Column(String, nullable=True)
raw_sections     = Column(JSON, nullable=True)   # {section_name: text_preview}
```

### 4B — Run the migration script to apply columns to the live DB

Create and run this script as `scripts/migrate_resume_v2.py`. It uses `ALTER TABLE` so
existing rows and all scraped job data are preserved:

```python
"""
migrate_resume_v2.py
Adds new columns to resume_profiles table without dropping any data.
Safe to run multiple times — skips columns that already exist.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Find the DB file — adjust path if yours is named differently or in a subdirectory
DB_PATH = Path("jobs.db")
if not DB_PATH.exists():
    # Try one level up or in a data/ folder
    for candidate in [Path("../jobs.db"), Path("data/jobs.db")]:
        if candidate.exists():
            DB_PATH = candidate
            break

if not DB_PATH.exists():
    print("ERROR: jobs.db not found. Check the path.")
    sys.exit(1)

NEW_COLUMNS = [
    ("work_experience",  "TEXT"),   # JSON stored as text
    ("projects",         "TEXT"),
    ("volunteer",        "TEXT"),
    ("certifications",   "TEXT"),
    ("languages",        "TEXT"),
    ("linkedin_url",     "TEXT"),
    ("github_url",       "TEXT"),
    ("raw_sections",     "TEXT"),
]

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Get existing columns
cursor.execute("PRAGMA table_info(resume_profiles)")
existing = {row[1] for row in cursor.fetchall()}

if not existing:
    print("WARNING: resume_profiles table not found — it will be created when the app starts.")
    conn.close()
    sys.exit(0)

added = []
skipped = []
for col_name, col_type in NEW_COLUMNS:
    if col_name in existing:
        skipped.append(col_name)
    else:
        cursor.execute(f"ALTER TABLE resume_profiles ADD COLUMN {col_name} {col_type}")
        added.append(col_name)

conn.commit()
conn.close()

print(f"Migration complete.")
print(f"  Added:   {added if added else 'none (all already exist)'}")
print(f"  Skipped: {skipped}")
print(f"  DB:      {DB_PATH.resolve()}")
print("\nNo data was lost. Existing resume profiles will have NULL for new columns until re-uploaded.")
```

Run it:
```bash
python scripts/migrate_resume_v2.py
```

Confirm output shows the columns were added (or already existed). Then restart the server:
```bash
uvicorn api.main:app --port 8000 --reload
```

---

## Step 5 — Update `api/main.py` — Richer Upload + GET Responses

### 5A — Update `POST /api/resume/upload` return value:

```python
return {
    "message":           "Resume uploaded and parsed successfully.",
    "name":              profile.name,
    "email":             profile.email,
    "phone":             profile.phone,
    "skills_count":      len(profile.parsed_skills or []),
    "experience_years":  profile.experience_years,
    "education_count":   len(profile.education or []),
    "work_entries":      len(profile.work_experience or []),
    "projects_count":    len(profile.projects or []),
    "volunteer_count":   len(profile.volunteer or []),
    "certifications":    profile.certifications or [],
    "languages":         profile.languages or [],
    "linkedin_url":      getattr(profile, "linkedin_url", None),
    "github_url":        getattr(profile, "github_url", None),
    "sections_detected": list((profile.raw_sections or {}).keys()),
}
```

### 5B — Update `GET /api/resume` to return ALL fields the frontend needs:

Find the existing `GET /api/resume` endpoint. Replace its return statement with:

```python
@app.get("/api/resume")
async def get_resume():
    profile = get_resume_profile(user_id="default")
    if not profile:
        raise HTTPException(status_code=404, detail="No resume uploaded yet.")
    return {
        # Contact
        "name":              profile.name,
        "email":             profile.email,
        "phone":             profile.phone,
        "linkedin_url":      getattr(profile, "linkedin_url", None),
        "github_url":        getattr(profile, "github_url", None),
        # Summary
        "summary":           profile.summary,
        "experience_years":  profile.experience_years,
        # Skills (for match scoring + display)
        "parsed_skills":     profile.parsed_skills or [],
        # Structured sections (NEW — used by frontend profile page)
        "work_experience":   profile.work_experience or [],
        "projects":          profile.projects or [],
        "volunteer":         profile.volunteer or [],
        "education":         profile.education or [],
        "certifications":    getattr(profile, "certifications", None) or [],
        "languages":         getattr(profile, "languages", None) or [],
        # Meta
        "original_filename": profile.original_filename,
        "uploaded_at":       profile.uploaded_at.isoformat() if profile.uploaded_at else None,
        "sections_detected": list((getattr(profile, "raw_sections", None) or {}).keys()),
    }
```

> Note: Use `getattr(profile, "field", None)` for all new v2 columns in case
> someone's profile was uploaded before the migration. This prevents AttributeError
> on old records that predate the column additions.

---

## Step 6 — Frontend: Display Parsed Resume in `frontend/profile.html`

This is the full profile page rewrite. Read the existing `frontend/profile.html` first to
understand the current structure, then replace the profile display section entirely.
Keep the upload form at the top unchanged — only update the section that renders
the parsed profile data below it.

### 6A — Update `frontend/js/api.js`

The existing `getResume()` already calls `GET /api/resume`. No changes needed to the
call itself — but confirm the method exists and works. If it currently returns only
partial fields, the updated endpoint from Step 5B will now return everything.

### 6B — Replace the profile display section in `frontend/profile.html`

Find the section in `profile.html` that renders the parsed profile (it probably shows
name, skills count, experience years). Replace it entirely with the following rich layout.
Keep everything above (the upload card) exactly as-is. Only swap out the results display.

The new display should call `window.API.getResume()` on page load and render all fields.
Here is the complete JavaScript + HTML to inject into the page:

```html
<!-- ── PROFILE DISPLAY (shown after resume is loaded) ── -->
<div id="profile-display" class="hidden mt-6 space-y-6 max-w-4xl mx-auto px-4">

  <!-- Contact Card -->
  <div class="bg-white rounded-xl border border-gray-200 p-5">
    <div class="flex items-start justify-between">
      <div>
        <h2 id="profile-name" class="text-xl font-bold text-gray-900"></h2>
        <div class="flex flex-wrap gap-4 mt-2 text-sm text-gray-500">
          <span id="profile-email" class="hidden"></span>
          <span id="profile-phone" class="hidden"></span>
          <a id="profile-linkedin" href="#" target="_blank"
             class="hidden text-indigo-600 hover:underline">LinkedIn</a>
          <a id="profile-github" href="#" target="_blank"
             class="hidden text-indigo-600 hover:underline">GitHub</a>
        </div>
        <p id="profile-summary" class="mt-3 text-sm text-gray-600 leading-relaxed max-w-2xl"></p>
      </div>
      <div class="text-right text-xs text-gray-400 shrink-0 ml-4">
        <div id="profile-exp-years" class="text-2xl font-bold text-indigo-600"></div>
        <div>yrs experience</div>
        <div id="profile-filename" class="mt-1 text-gray-400"></div>
        <div id="profile-uploaded" class="text-gray-300"></div>
      </div>
    </div>
  </div>

  <!-- Skills Card -->
  <div class="bg-white rounded-xl border border-gray-200 p-5">
    <h3 class="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
      <span>Skills</span>
      <span id="skills-count"
            class="text-xs font-normal bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">
      </span>
    </h3>
    <div id="skills-chips" class="flex flex-wrap gap-1.5"></div>
  </div>

  <!-- Work Experience Card -->
  <div id="experience-card" class="bg-white rounded-xl border border-gray-200 p-5 hidden">
    <h3 class="text-sm font-semibold text-gray-700 mb-4">Work Experience</h3>
    <div id="experience-list" class="space-y-4"></div>
  </div>

  <!-- Projects Card -->
  <div id="projects-card" class="bg-white rounded-xl border border-gray-200 p-5 hidden">
    <h3 class="text-sm font-semibold text-gray-700 mb-4">Projects</h3>
    <div id="projects-list" class="space-y-3"></div>
  </div>

  <!-- Volunteer Card -->
  <div id="volunteer-card" class="bg-white rounded-xl border border-gray-200 p-5 hidden">
    <h3 class="text-sm font-semibold text-gray-700 mb-4">Volunteer & Community</h3>
    <div id="volunteer-list" class="space-y-4"></div>
  </div>

  <!-- Education Card -->
  <div id="education-card" class="bg-white rounded-xl border border-gray-200 p-5 hidden">
    <h3 class="text-sm font-semibold text-gray-700 mb-3">Education</h3>
    <div id="education-list" class="space-y-2"></div>
  </div>

  <!-- Certifications + Languages Row -->
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div id="certs-card" class="bg-white rounded-xl border border-gray-200 p-5 hidden">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Certifications</h3>
      <ul id="certs-list" class="space-y-1 text-sm text-gray-700"></ul>
    </div>
    <div id="langs-card" class="bg-white rounded-xl border border-gray-200 p-5 hidden">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Languages</h3>
      <div id="langs-chips" class="flex flex-wrap gap-1.5"></div>
    </div>
  </div>

</div>

<!-- Empty state: no resume yet -->
<div id="profile-empty" class="hidden mt-10 text-center text-gray-400 text-sm py-12">
  <p class="text-4xl mb-3">📄</p>
  <p class="font-medium text-gray-500">No resume uploaded yet.</p>
  <p class="mt-1">Upload your PDF or DOCX above to see your parsed profile here.</p>
</div>
```

### 6C — JavaScript to populate the profile display

Add this `<script>` block to `profile.html` (before `</body>`). It calls `GET /api/resume`
on page load and fills every card:

```html
<script>
// ── Helpers ──────────────────────────────────────────────────────────────
function chip(label, colorClass) {
  return `<span class="px-2 py-0.5 text-xs rounded-full font-medium ${colorClass}">${label}</span>`;
}

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
function setText(id, val) { if (val) document.getElementById(id).textContent = val; }

function renderJobEntry(entry) {
  const dateStr   = entry.date_range || '';
  const current   = entry.is_current
    ? '<span class="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full ml-2">Current</span>'
    : '';
  const desc      = entry.description
    ? `<p class="mt-1.5 text-xs text-gray-500 leading-relaxed">${entry.description.slice(0, 300)}${entry.description.length > 300 ? '…' : ''}</p>`
    : '';
  return `
    <div class="border-l-2 border-indigo-200 pl-4">
      <div class="flex items-center justify-between flex-wrap gap-1">
        <span class="text-sm font-semibold text-gray-800">${entry.title || 'Role'}</span>
        <span class="text-xs text-gray-400">${dateStr}${current}</span>
      </div>
      ${entry.company ? `<div class="text-xs text-indigo-600 mt-0.5">${entry.company}</div>` : ''}
      ${desc}
    </div>`;
}

function renderProjectEntry(proj) {
  const techChips = (proj.tech || [])
    .map(t => chip(t, 'bg-gray-100 text-gray-600'))
    .join('');
  const desc = proj.description
    ? `<p class="text-xs text-gray-500 mt-1">${proj.description.slice(0, 200)}${proj.description.length > 200 ? '…' : ''}</p>`
    : '';
  return `
    <div class="border-l-2 border-purple-200 pl-4">
      <div class="flex items-center justify-between flex-wrap gap-1">
        <span class="text-sm font-semibold text-gray-800">${proj.name || 'Project'}</span>
        <span class="text-xs text-gray-400">${proj.date_range || ''}</span>
      </div>
      ${techChips ? `<div class="flex flex-wrap gap-1 mt-1">${techChips}</div>` : ''}
      ${desc}
    </div>`;
}

function renderVolunteerEntry(entry) {
  return `
    <div class="border-l-2 border-amber-200 pl-4">
      <div class="flex items-center justify-between flex-wrap gap-1">
        <span class="text-sm font-semibold text-gray-800">${entry.title || 'Role'}</span>
        <span class="text-xs text-gray-400">${entry.date_range || ''}</span>
      </div>
      ${entry.company ? `<div class="text-xs text-amber-600 mt-0.5">${entry.company}</div>` : ''}
      ${entry.description ? `<p class="text-xs text-gray-500 mt-1">${entry.description.slice(0, 200)}…</p>` : ''}
    </div>`;
}

function renderEducationEntry(edu) {
  const gpa = edu.gpa ? ` · GPA ${edu.gpa}` : '';
  return `
    <div class="flex items-start justify-between gap-2">
      <div>
        <span class="text-sm font-medium text-gray-800">${edu.degree || 'Degree'}</span>
        ${edu.institution ? `<span class="text-xs text-gray-500 ml-2">@ ${edu.institution}</span>` : ''}
        <span class="text-xs text-gray-400 ml-2">${gpa}</span>
      </div>
      <span class="text-xs text-gray-400 shrink-0">${edu.graduation_year || ''}</span>
    </div>`;
}

// ── Main Render Function ───────────────────────────────────────────────────
async function loadProfile() {
  let resume;
  try {
    resume = await window.API.getResume();
  } catch (e) {
    resume = null;
  }

  if (!resume) {
    show('profile-empty');
    hide('profile-display');
    return;
  }

  hide('profile-empty');
  show('profile-display');

  // ── Contact ──
  setText('profile-name', resume.name || 'Your Name');
  if (resume.email) {
    const el = document.getElementById('profile-email');
    el.textContent = '✉ ' + resume.email;
    el.classList.remove('hidden');
  }
  if (resume.phone) {
    const el = document.getElementById('profile-phone');
    el.textContent = '☎ ' + resume.phone;
    el.classList.remove('hidden');
  }
  if (resume.linkedin_url) {
    const el = document.getElementById('profile-linkedin');
    el.href = resume.linkedin_url.startsWith('http') ? resume.linkedin_url : 'https://' + resume.linkedin_url;
    el.classList.remove('hidden');
  }
  if (resume.github_url) {
    const el = document.getElementById('profile-github');
    el.href = resume.github_url.startsWith('http') ? resume.github_url : 'https://' + resume.github_url;
    el.textContent = 'GitHub';
    el.classList.remove('hidden');
  }
  setText('profile-summary',  resume.summary?.slice(0, 400));
  setText('profile-exp-years', (resume.experience_years || 0).toFixed(0));
  setText('profile-filename',  resume.original_filename || '');
  setText('profile-uploaded',  resume.uploaded_at ? 'Uploaded ' + new Date(resume.uploaded_at).toLocaleDateString() : '');

  // ── Skills ──
  const skills = resume.parsed_skills || [];
  document.getElementById('skills-count').textContent = skills.length + ' skills';
  document.getElementById('skills-chips').innerHTML = skills
    .map(s => chip(s, 'bg-indigo-50 text-indigo-700 border border-indigo-100'))
    .join('');

  // ── Work Experience ──
  const workEntries = resume.work_experience || [];
  if (workEntries.length > 0) {
    document.getElementById('experience-list').innerHTML =
      workEntries.map(renderJobEntry).join('');
    show('experience-card');
  }

  // ── Projects ──
  const projects = resume.projects || [];
  if (projects.length > 0) {
    document.getElementById('projects-list').innerHTML =
      projects.map(renderProjectEntry).join('');
    show('projects-card');
  }

  // ── Volunteer ──
  const volunteer = resume.volunteer || [];
  if (volunteer.length > 0) {
    document.getElementById('volunteer-list').innerHTML =
      volunteer.map(renderVolunteerEntry).join('');
    show('volunteer-card');
  }

  // ── Education ──
  const education = resume.education || [];
  if (education.length > 0) {
    document.getElementById('education-list').innerHTML =
      education.map(renderEducationEntry).join('');
    show('education-card');
  }

  // ── Certifications ──
  const certs = resume.certifications || [];
  if (certs.length > 0) {
    document.getElementById('certs-list').innerHTML =
      certs.map(c => `<li class="flex items-start gap-1.5"><span class="text-green-500 mt-0.5">✓</span>${c}</li>`).join('');
    show('certs-card');
  }

  // ── Languages ──
  const langs = resume.languages || [];
  if (langs.length > 0) {
    document.getElementById('langs-chips').innerHTML =
      langs.map(l => chip(l, 'bg-blue-50 text-blue-700')).join('');
    show('langs-card');
  }
}

// Run on page load
loadProfile();

// Re-run after upload success (hook into the existing upload success handler)
// Find the existing upload success callback and add: loadProfile();
// It likely looks like: .then(result => { /* show success */ })
// Add loadProfile() inside that .then() block after showing the success message.
</script>
```

### 6D — Hook profile reload into the upload success handler

In `profile.html`, find the existing JavaScript that handles the upload form submission.
It likely has a `.then()` callback that shows a success message. Add `loadProfile()` inside
that callback so the profile cards refresh immediately after upload without a page reload:

```javascript
// BEFORE (existing pattern):
window.API.uploadResume(formData).then(result => {
  // shows success message...
});

// AFTER:
window.API.uploadResume(formData).then(result => {
  // existing success message code...
  loadProfile();  // ← add this line
});
```

---

## Step 7 — Write and Run the Test Suite

Create `tasks/test_resume_parser_v2.py`:

```python
"""
Full test suite for resume_parser.py v2.
Run from the project root: python tasks/test_resume_parser_v2.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.nlp.resume_parser import (
    _normalize_heading,
    _is_section_header,
    segment_sections,
    extract_email,
    extract_phone,
    extract_linkedin,
    parse_certifications,
    parse_languages,
    calculate_experience_years,
    RE_DATE_RANGE,
)

errors = []

def check(name, condition, detail=""):
    if not condition:
        errors.append(f"FAIL [{name}] {detail}")
        print(f"  ✗ {name}: {detail}")
    else:
        print(f"  ✓ {name}")

print("\n── Section Header Detection ──")
tests = [
    ("work experience",        True, "experience"),
    ("WORK EXPERIENCE",        True, "experience"),
    ("Professional Background",True, "experience"),
    ("SKILLS",                 True, "skills"),
    ("Areas of Expertise",     True, "skills"),
    ("Core Competencies",      True, "skills"),
    ("Volunteer Experience",   True, "volunteer"),
    ("Community Involvement",  True, "volunteer"),
    ("EXTRACURRICULAR",        True, "volunteer"),
    ("Projects",               True, "projects"),
    ("Open Source Projects",   True, "projects"),
    ("Certifications",         True, "certifications"),
    ("Licenses & Certifications", True, "certifications"),
    ("EDUCATION",              True, "education"),
    ("Academic Background",    True, "education"),
    ("Summary",                True, "summary"),
    ("About Me",               True, "summary"),
    ("Languages",              True, "languages"),
    ("I developed a feature.", False, None),  # sentence, not header
    ("The team shipped it.",   False, None),
]
for line, expected_is_header, expected_canonical in tests:
    is_h, canon = _is_section_header(line)
    check(
        f"header: '{line}'",
        is_h == expected_is_header and (canon == expected_canonical or not expected_is_header),
        f"got is_header={is_h}, canonical={canon}"
    )

print("\n── Regex Patterns ──")
check("email basic",    extract_email("Contact: jane.doe@gmail.com") == "jane.doe@gmail.com")
check("email plus",     extract_email("user+tag@example.co.uk") == "user+tag@example.co.uk")
check("phone US",       extract_phone("(404) 555-1234") is not None)
check("phone intl",     extract_phone("+1 800 555 9999") is not None)
check("linkedin",       extract_linkedin("linkedin.com/in/janedoe") is not None)
check("date range 1",   bool(RE_DATE_RANGE.search("Jan 2020 – Mar 2022")))
check("date range 2",   bool(RE_DATE_RANGE.search("2018 - Present")))
check("date range 3",   bool(RE_DATE_RANGE.search("September 2019 to December 2021")))
check("no date match",  not RE_DATE_RANGE.search("We have 2020 goals"))

print("\n── Section Segmentation ──")
sample_resume = """
Jane Doe
jane@example.com | (555) 123-4567

SUMMARY
Experienced software engineer with 5 years building scalable systems.

WORK EXPERIENCE
Software Engineer — Acme Corp
Jan 2021 – Present
- Built REST APIs with FastAPI
- Led migration to PostgreSQL

Junior Developer — StartupXYZ
Jun 2019 – Dec 2020
- Developed React frontend

SKILLS
Python, FastAPI, Docker, PostgreSQL, React, SQL

EDUCATION
B.S. Computer Science — Georgia Tech
2015 – 2019

PROJECTS
JobSpy — Personal Project
Built a job scraper using Python and FastAPI
Tech: Python, FastAPI, SQLite

Volunteer Experience
Code for Atlanta
2020 – 2021
Taught Python workshops to high school students

CERTIFICATIONS
AWS Certified Solutions Architect
Google Cloud Professional Data Engineer
"""
sections = segment_sections(sample_resume)
check("detects experience section", "experience" in sections)
check("detects skills section",     "skills" in sections)
check("detects education section",  "education" in sections)
check("detects projects section",   "projects" in sections)
check("detects volunteer section",  "volunteer" in sections)
check("detects certifications",     "certifications" in sections)
check("skills content correct",     "Python" in sections.get("skills", ""))

print("\n── Experience Year Calculation ──")
entries = [
    {"start_year": 2019, "end_year": 2021, "is_current": False},
    {"start_year": 2021, "end_year": 2024, "is_current": True},
]
yrs = calculate_experience_years(entries, "")
check("experience years ~5", 4 <= yrs <= 6, f"got {yrs}")

overlapping = [
    {"start_year": 2018, "end_year": 2022, "is_current": False},
    {"start_year": 2020, "end_year": 2024, "is_current": True},
]
yrs2 = calculate_experience_years(overlapping, "")
check("overlap not double-counted", yrs2 <= 7, f"got {yrs2}")

print("\n── Certifications & Languages ──")
cert_text = "- AWS Certified Solutions Architect\n• Google Cloud Professional\n- Certified Scrum Master"
certs = parse_certifications(cert_text)
check("parses 3 certs", len(certs) == 3, str(certs))

lang_text = "English (Fluent), Spanish – B2, Mandarin (Conversational)"
langs = parse_languages(lang_text)
check("parses 3 languages", len(langs) == 3, str(langs))

print("\n" + "="*50)
if errors:
    print(f"FAILED: {len(errors)} test(s)")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"ALL TESTS PASSED")
```

Run:
```bash
python tasks/test_resume_parser_v2.py
```

All tests must pass before moving on.

---

## Step 7 — End-to-End Smoke Test

Start the server, upload a real resume PDF, and verify the response:

```bash
uvicorn api.main:app --port 8000 --reload &

# Upload a real resume
curl -X POST http://localhost:8000/api/resume/upload \
  -F "file=@/path/to/real_resume.pdf" | python -m json.tool

# Should show: sections_detected, work_entries > 0, skills_count > 0
```

Check `GET /api/resume` returns all new fields including `work_experience`, `projects`, `volunteer`.

---

## Completion Checklist

**Parser**
- [ ] `pdfplumber` installed and verified
- [ ] `jobspy/nlp/resume_parser.py` fully replaced with v2 implementation
- [ ] All unit tests in `tasks/test_resume_parser_v2.py` pass

**Database (safe migration — no data loss)**
- [ ] New columns added to `ResumeProfile` class in `database.py`
- [ ] `scripts/migrate_resume_v2.py` created and run successfully
- [ ] Migration output confirms columns added (or already existed)
- [ ] Server restarts cleanly after migration

**API**
- [ ] `POST /api/resume/upload` returns enriched response with all new fields
- [ ] `GET /api/resume` returns `work_experience`, `projects`, `volunteer`,
      `education`, `certifications`, `languages`, `linkedin_url`, `github_url`
- [ ] All `getattr(profile, "field", None)` guards in place (no AttributeError on old records)

**Frontend (`frontend/profile.html`)**
- [ ] Contact card shows name, email, phone, LinkedIn, GitHub links
- [ ] Skills card shows all skill chips (indigo badges)
- [ ] Work Experience card shows job entries with title, company, date range,
      current badge, description preview
- [ ] Projects card shows project entries with tech stack chips
- [ ] Volunteer card shows volunteer entries (amber left border)
- [ ] Education card shows degree, institution, graduation year, GPA
- [ ] Certifications card shows list with green checkmarks
- [ ] Languages card shows language chips (blue badges)
- [ ] Cards that have no data stay hidden (not shown as empty)
- [ ] Profile reloads automatically after a new resume is uploaded (no page refresh needed)
- [ ] Upload form still works and shows success message

**End-to-end**
- [ ] Upload a real PDF → all cards populate correctly
- [ ] Visit `GET /api/resume` directly → all fields present in JSON response
- [ ] Existing scraped jobs in DB are unaffected

## What's Next
When done, tell Kenneth **"Phase 3B complete"**.

Since match scoring (Phase 4) and cover letter generation (Phase 5) are already
built, no further changes are needed to those files — `parsed_skills` output
format is unchanged, so `match_scorer.py` and `cover_letter.py` will automatically
benefit from the improved skill extraction in the v2 parser.

The only remaining consideration: if you want the **cover letter generation** to
also reference `work_experience` entries (for richer prompts), that would be a
small enhancement to `jobspy/nlp/cover_letter.py` — but it is optional and not
required for the core functionality to work.
