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
    "career highlights":                "experience",
    "professional highlights":          "experience",
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
    "leadership activities":            "volunteer",
    "leadership and activities":        "volunteer",
    "campus activities":                "volunteer",
    "activities and leadership":        "volunteer",
    "clubs and organizations":          "volunteer",
    "organizations":                    "volunteer",
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

    # ── CONCATENATED VARIANTS (PDF extractors sometimes strip spaces) ─────────
    "professionalexperience":           "experience",
    "professionalexperiences":          "experience",
    "workexperience":                   "experience",
    "workexperiences":                  "experience",
    "employmenthistory":                "experience",
    "projectexperience":                "projects",
    "projectexperiences":               "projects",
    "technicalskills":                  "skills",
    "coretechnicalskills":              "skills",
    "volunteerexperience":              "volunteer",
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

# Date range — used to anchor individual job/project entries.
# \s* (not \s+) allows month and year to be adjacent (PDF extraction artifact).
RE_DATE_RANGE = re.compile(
    r"""
    (?:
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)
        \.?\s*
    )?
    (?:19|20)\d{2}
    \s*[-\u2013\u2014/to]+\s*
    (?:
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)
        \.?\s*
        (?:19|20)\d{2}
        |
        (?:19|20)\d{2}
        |
        present|current|now|ongoing|today
    )
    """,
    re.IGNORECASE | re.VERBOSE,)

# Relaxed date range — used ONLY in _split_into_entries fallback splitting.
# [\dxX]{2} accepts real digits AND placeholder years like "20xx" / "20XX".
# Month prefix is required here (unlike RE_DATE_RANGE) to reduce false positives.
RE_DATE_RANGE_LOOSE = re.compile(
    r"""
    (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|
       jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|
       oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)
    \.?\s*
    (?:19|20)[\dxX]{2}
    (?:
        \s*[-\u2013\u2014/to]+\s*
        (?:
            (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|
               jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|
               oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)
            \.?\s*
        )?
        (?:(?:19|20)[\dxX]{2}|present|current|now|ongoing|today)
    )?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Standalone year (for experience calculation)
RE_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")

# Degree abbreviations
RE_DEGREE = re.compile(
    r"\b(B\.?E\.?|B\.?S\.?|M\.?S\.?|M\.?B\.?A\.?|Ph\.?D\.?|"
    r"B\.?Tech\.?|M\.?Tech\.?|B\.?A\.?|M\.?A\.?|B\.?Sc\.?|M\.?Sc\.?|"
    r"A\.?A\.?S\.?|A\.?S\.?|B\.?B\.?A\.?|D\.?D\.?S\.?|M\.?D\.?|J\.?D\.?|"
    r"Bachelor(?:'s)?|Master(?:'s)?|Doctor(?:ate)?|Associate(?:'s)?)\b",
    re.IGNORECASE,
)

# Section header structural fallback
RE_HEADER_ALLCAPS = re.compile(r"^[A-Z][A-Z\s&/\-]{2,45}:?\s*$")
RE_HEADER_TITLECASE = re.compile(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}):?\s*$")

# Positive confirmation that a line names a company/institution rather than a
# description bullet: the line must end with a city/state or Remote suffix.
LOCATION_SUFFIX = re.compile(
    r'(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*'
    r'(?:[A-Z]{2}|D\.C\.|Washington|Remote)\s*$'
)


def _looks_like_company_line(line: str) -> bool:
    """Return True only when *line* ends with a recognisable location suffix.

    Using location as positive confirmation avoids the action-verb exclusion
    heuristic, which was brittle against bullets that start with proper nouns
    (e.g. "Cultivated strong rapport…" would pass a verb test if 'C' happened
    to look like an org name).  A city/state tail is a strong, unambiguous
    signal that the line is an employer or institution, not a bullet.
    """
    stripped = line.strip()
    if not stripped:
        return False
    return bool(LOCATION_SUFFIX.search(stripped))


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

    Known limitation: pdfplumber maps non-ASCII characters not in its replacement
    table to a space, so accented characters like é become " " (e.g. "Café" → "Caf ").
    This is expected behavior and not fixable without OCR.
    """
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages_default: list[str] = []
            pages_layout: list[str] = []
            for page in pdf.pages:
                t = page.extract_text(x_tolerance=3, y_tolerance=3)
                if t:
                    pages_default.append(t)
                t2 = page.extract_text(layout=True)
                if t2:
                    pages_layout.append(t2)

            result = "\n".join(pages_default)

            # Multi-column detection: if >30% of lines are short (column fragmentation
            # signal), prefer the layout-aware extraction when it gives longer lines.
            all_lines = result.splitlines()
            if all_lines and pages_layout:
                short_ratio = sum(1 for l in all_lines if len(l) < 25) / len(all_lines)
                if short_ratio > 0.30:
                    result_layout = "\n".join(pages_layout)
                    layout_lines = result_layout.splitlines()
                    if layout_lines:
                        avg_default = sum(len(l) for l in all_lines) / len(all_lines)
                        avg_layout = sum(len(l) for l in layout_lines) / len(layout_lines)
                        if avg_layout > avg_default:
                            result = result_layout

            return result
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
    text = re.sub(r"[^\x20-\x7E\n]", lambda m: _normalize_unicode(m.group(0)), text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def _normalize_unicode(char: str) -> str:
    """Map common unicode chars to ASCII equivalents."""
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2015": "-",
        "\u2018": "'", "\u2019": "'",
        "\u201C": '"', "\u201D": '"',
        "\u2022": "-", "\u25A0": "-", "\u25CF": "-",
        "\u00A0": " ",
    }
    return replacements.get(char, " ")


def _fix_concatenated_words(text: str) -> str:
    """
    Re-insert spaces into camelCase/TitleCase concatenated words that
    pdfplumber produces when it loses spacing in certain PDF layouts.

    "EmoryUniversity"                  → "Emory University"
    "BachelorofScienceinCS"            → "Bachelor of Science in CS"
    "ComputerScienceandPhysics"        → "Computer Science and Physics"
    "AtlantaGA"                        → "Atlanta GA"

    Strategy: insert a space before any uppercase letter that is
    immediately preceded by a lowercase letter (standard camelCase split),
    AND before any uppercase letter preceded by another uppercase letter
    that is itself followed by a lowercase letter (e.g. "GAAtlanta").
    Apply only to tokens longer than 8 characters to avoid splitting
    intentional acronyms like "GPA" or "PhD".
    """
    def split_token(token: str) -> str:
        if len(token) <= 8:
            return token
        # Step 0: split embedded lowercase joining words before camelCase split.
        # Matches a known short word that sits between a lowercase and an uppercase
        # letter: "BachelorofScience" → "Bachelor of Science",
        # "ScienceinCS" → "Science in CS", "ScienceandPhysics" → "Science and Physics".
        result = re.sub(
            r'(?<=[a-z])(of|in|and|the|or|to|with|for|at|by|from|as|an)(?=[A-Z])',
            r' \1 ', token,
        )
        # Step 1: insert space before uppercase preceded by lowercase: "ofScience" → "of Science"
        result = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', result)
        # Step 2: insert space before uppercase run followed by lowercase: "GAAtlanta" → "GA Atlanta"
        result = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', result)
        return result

    return ' '.join(split_token(t) for t in text.split())


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
    line = re.sub(r"[:\.\!\?]+$", "", line)
    line = re.sub(r"\s+", " ", line)
    return line


def _is_section_header(line: str) -> tuple[bool, str | None]:
    """
    Determine if a line is a section header.
    Returns (is_header: bool, canonical_name: str | None)
    """
    normalized = _normalize_heading(line)

    # Layer 1a: Exact match
    if normalized in SECTION_SYNONYMS:
        return True, SECTION_SYNONYMS[normalized]

    # Layer 1b: Prefix match
    for key, canonical in SECTION_SYNONYMS.items():
        if normalized.startswith(key) and len(normalized) <= len(key) + 20:
            return True, canonical

    stripped = line.strip()

    # Layer 3a: ALL-CAPS line
    if RE_HEADER_ALLCAPS.match(stripped):
        normalized_fallback = _normalize_heading(stripped)
        canonical = SECTION_SYNONYMS.get(normalized_fallback, normalized_fallback)
        return True, canonical

    # Layer 3b: Title-Case line — ONLY when the normalized form is a known synonym.
    # Without this guard, job titles like "Software Engineer" would be misdetected.
    if RE_HEADER_TITLECASE.match(stripped):
        words = stripped.lower().split()
        if len(words) <= 5 and not any(
            w in ("is", "are", "was", "were", "have", "the", "a", "an") for w in words
        ):
            normalized_fallback = _normalize_heading(stripped)
            canonical = SECTION_SYNONYMS.get(normalized_fallback)
            if canonical:
                return True, canonical

    return False, None


def segment_sections(text: str) -> dict[str, str]:
    """
    Split resume text into sections using the state-machine header detector.

    Returns a dict: {canonical_section_name: raw_section_text}
    The special key "header" holds text before the first detected section.
    """
    lines = text.splitlines()
    sections: dict[str, list[str]] = {"header": []}
    current_section = "header"

    for line in lines:
        stripped = line.strip()

        if not stripped:
            sections.setdefault(current_section, []).append(line)
            continue

        is_header, canonical = _is_section_header(stripped)
        if is_header and canonical:
            current_section = canonical
            sections.setdefault(current_section, [])
        else:
            sections.setdefault(current_section, []).append(line)

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

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip()
            if len(name) >= 3 and "@" not in name and name.replace(" ", "").isalpha():
                return name

    # Fallback: all-caps name (e.g. "MORGAN LANDER") — check before title-case
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and 2 <= len(stripped.split()) <= 4:
            words = stripped.split()
            if all(w.isupper() and w.isalpha() and len(w) >= 2 for w in words):
                return stripped.title()

    # Fallback: first non-empty line that looks like a name (2–4 words, title case)
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
    """Extract start year, end year, and is_current from a date range string."""
    import datetime
    current_year = datetime.datetime.now().year
    # Use simple digit search — avoids \b failures when month+year are concatenated
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", date_range_str)]
    is_current = bool(re.search(r"present|current|now|ongoing|today", date_range_str, re.I))

    start_year = min(years) if years else None
    end_year = current_year if is_current else (max(years) if years else None)
    return start_year, end_year, is_current


def _split_into_entries(section_text: str) -> list[str]:
    """
    Split experience/project/volunteer section text into individual entries.

    Pass 1: if 2+ strict RE_DATE_RANGE matches exist, split at the start of
    each matched line (preserves inline "Title  Month YYYY – Present" headers).

    Pass 2 (fallback for 0–1 strict matches): try blank-line splitting first;
    if that yields only one block, fall back to per-line RE_DATE_RANGE_LOOSE
    scanning so that placeholder dates like "20xx" still split correctly.
    """
    if not section_text.strip():
        return []

    date_matches = list(RE_DATE_RANGE.finditer(section_text))

    if len(date_matches) >= 2:
        # Build a mapping from character position → line-start position
        line_starts: list[int] = []
        pos = 0
        for line in section_text.split("\n"):
            line_starts.append(pos)
            pos += len(line) + 1  # +1 for the '\n'

        def line_start_for(char_pos: int) -> int:
            """Return the character index of the line that contains char_pos."""
            result = 0
            for ls in line_starts:
                if ls <= char_pos:
                    result = ls
                else:
                    break
            return result

        # Collect unique entry-start positions (one per date match, at line start)
        entry_starts: list[int] = sorted(
            {line_start_for(m.start()) for m in date_matches}
        )

        # Split section_text at each entry start
        entries: list[str] = []
        for i, start in enumerate(entry_starts):
            end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(section_text)
            chunk = section_text[start:end].strip()
            if chunk:
                entries.append(chunk)

        return entries

    # Pass 2: try blank-line split, then per-line loose-date scan
    blocks = re.split(r"\n\s*\n", section_text)
    blocks = [b.strip() for b in blocks if b.strip()]
    if len(blocks) > 1:
        return blocks

    # Per-line loose scan: any line matching RE_DATE_RANGE_LOOSE starts a new entry
    groups: list[list[str]] = [[]]
    for line in section_text.splitlines():
        if RE_DATE_RANGE_LOOSE.search(line) and groups[-1]:
            groups.append([line])
        else:
            groups[-1].append(line)
    return ["\n".join(g).strip() for g in groups if any(l.strip() for l in g)]


def _parse_single_job_entry(entry_text: str, nlp) -> dict:
    """
    Parse one job entry block into structured fields.

    Handles two common resume formats:
      A) Header line: "Company, Title Location | DateRange"  (inline, pipe-separated)
      B) Header lines: Title on line N, date on line N+1 or same line without pipe
    """
    lines = [l for l in entry_text.splitlines() if l.strip()]
    if not lines:
        return {}

    # Find the line containing a date range
    date_range_str = None
    date_line_idx = None
    for idx, line in enumerate(lines):
        m = RE_DATE_RANGE.search(line)
        if m:
            date_range_str = m.group(0)
            date_line_idx = idx
            break

    start_year, end_year, is_current = (
        _parse_years_from_range(date_range_str) if date_range_str else (None, None, False)
    )

    title, company = None, None

    # ── Format A: date is on line 0, company+title on same line (pipe separator) ──
    if date_line_idx == 0:
        header_line = lines[0]
        # Strip the date range from the header line to get company+title+location
        left = header_line[:RE_DATE_RANGE.search(header_line).start()].strip()
        left = left.rstrip("|").rstrip().rstrip(",").strip()

        # Try pipe split first: "Company, Title Location | Date"
        if "|" in left:
            left = left[:left.rfind("|")].strip()

        # Split on first comma: "Company, Title Location"
        comma_idx = left.find(",")
        if comma_idx > 0:
            company = left[:comma_idx].strip()
            company = (re.sub(
                r'(?:,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|\s+[A-Z][a-z]+)'
                r',\s*(?:[A-Z]{2}|D\.C\.)\s*$',
                '', company,
            ).strip().rstrip(',')) or company
            title_loc = left[comma_idx + 1:].strip()
            # Strip trailing US-style location ("Atlanta,GA", "Remote", "Suzhou,China")
            loc_m = re.search(
                r"\s+(?:[A-Z][a-z]+(?:,\s*(?:[A-Z]{2}|[A-Z][a-z]+))?|Remote|Hybrid|Online)\s*$",
                title_loc,
            )
            title = title_loc[:loc_m.start()].strip() if loc_m else title_loc
        else:
            title = left

        post_date_lines = lines[1:]

    # ── Format B: date is on a later line, title+company in preceding lines ──
    else:
        pre_date_lines = lines[:date_line_idx] if date_line_idx is not None else lines[:2]
        post_date_lines = lines[date_line_idx + 1:] if date_line_idx is not None else lines[2:]

        if date_line_idx is not None:
            # Check if the date line itself contains a title (text before the date)
            date_match_on_line = RE_DATE_RANGE.search(lines[date_line_idx])
            text_before_date = lines[date_line_idx][:date_match_on_line.start()].strip()
            title_is_on_date_line = len(text_before_date) > 2
        else:
            title_is_on_date_line = False

        if title_is_on_date_line:
            # SUB-FORMAT B1: "Company   City, ST" on line before date,
            # "Title   DateRange" on the date line itself.
            title = text_before_date.rstrip(',-|').strip()
            if pre_date_lines:
                # Strip trailing location suffix from company line
                # e.g. "Ralph Lauren   Washington, D.C." → "Ralph Lauren"
                company_raw = pre_date_lines[0].strip()
                company = re.sub(
                    r'(?:,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|\s+[A-Z][a-z]+)'
                    r',\s*(?:[A-Z]{2}|D\.C\.)\s*$',
                    '',
                    company_raw,
                ).strip().rstrip(',')
                if not company:
                    company = company_raw  # fallback: keep original if stripping fails
        else:
            # SUB-FORMAT B2: date line is date-only, title in pre_date_lines
            pre = pre_date_lines
            if pre:
                title = pre[0].strip()
                company = pre[1].strip() if len(pre) > 1 else None

    # Clean up description bullets (strip leading spaces/bullet chars)
    bullets = []
    for line in post_date_lines:
        cleaned = line.strip().lstrip(
            "\u2022\u25cf\u25e6\u2013-*\u2027\u2043\u204c\u204d\u2219\u25aa\u2012"
        ).strip()
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
        if cleaned:
            bullets.append(cleaned)

    description = "\n".join(bullets).strip()

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
    Parse the projects section into structured entries.

    Handles two date styles:
      - Full range: "Jan 2026 – Mar 2027"
      - Year-only:  "Jan2026" or just "2026" at end of project name line
    Handles tech extraction from:
      - "Tech: Python, FastAPI" prefix
      - Parenthesized tech list at end of description line: "Platform (Python FastAPI SQL)"
    """
    if not section_text.strip():
        return []

    # A non-indented line containing a year = project header
    projects = []
    current_lines: list[str] = []

    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        is_indented = raw_line != stripped
        has_year = bool(RE_YEAR.search(stripped))

        if not is_indented and has_year and current_lines:
            projects.append(_parse_single_project(current_lines))
            current_lines = [stripped]
        else:
            current_lines.append(stripped)

    if current_lines:
        projects.append(_parse_single_project(current_lines))

    return projects[:8]


def _parse_single_project(lines: list[str]) -> dict:
    """Parse one project entry from its collected lines."""
    if not lines:
        return {}

    first_line = lines[0]

    # Extract date: try full range first, then standalone month+year, then bare year
    date_str = None
    name = first_line
    dr = RE_DATE_RANGE.search(first_line)
    if dr:
        date_str = dr.group(0)
        name = first_line[:dr.start()].strip()
    else:
        # Standalone month+year at end of line: "ProjectName Jan2026"
        m_yr = re.search(
            r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\.?\s*(?:19|20)\d{2}",
            first_line, re.IGNORECASE,
        )
        if m_yr:
            date_str = m_yr.group(0)
            name = first_line[:m_yr.start()].strip()
        else:
            # Bare year at end
            yr = RE_YEAR.search(first_line)
            if yr:
                date_str = yr.group(0)
                name = first_line[:yr.start()].strip()

    tech: list[str] = []
    description_lines: list[str] = []

    for line in lines[1:]:
        # Explicit "Tech:" prefix
        tech_match = re.match(r"(?:tech(?:nologies)?|stack|tools?|built with)[:\s]+(.+)", line, re.I)
        if tech_match:
            tech = [t.strip() for t in re.split(r"[,\s]+", tech_match.group(1)) if t.strip()]
            continue

        # Parenthesized tech list at end of line: "Description (Python FastAPI SQL)"
        paren = re.search(r"\(([^)]{5,})\)\s*$", line)
        if paren and not tech:
            inner = paren.group(1)
            # Only treat as tech if it looks like space/comma separated identifiers
            if re.match(r"^[\w\s.#+\-,]+$", inner):
                tech = [t.strip() for t in re.split(r"[\s,]+", inner) if t.strip()]
                # Add the line without the parenthesized tech as description
                desc_part = line[:paren.start()].strip()
                if desc_part:
                    description_lines.append(desc_part)
                continue

        cleaned = line.lstrip("\u2022\u25cf\u25e6\u2013-* ").strip()
        if cleaned:
            description_lines.append(cleaned)

    return {
        "name": name,
        "tech": tech,
        "date_range": date_str,
        "description": "\n".join(description_lines),
    }


def parse_volunteer_section(section_text: str, nlp) -> list[dict]:
    """
    Parse volunteer section — same logic as work experience (date-anchor strategy).
    """
    entries = _split_into_entries(section_text)
    results = []
    for entry in entries:
        parsed = _parse_single_job_entry(entry, nlp)
        if not parsed.get("title"):
            lines = [
                l.strip() for l in entry.splitlines()
                if l.strip() and not RE_DATE_RANGE.search(l)
            ]
            if lines:
                parsed["title"] = lines[0]
        results.append(parsed)
    return results


# ─────────────────────────────────────────────
# EDUCATION PARSING
# ─────────────────────────────────────────────

_DEGREE_LIBERAL = re.compile(
    r"(Bachelor|Master|Doctor(?:ate)?|Associate|Ph\.?D\.?|B\.?S\.?|M\.?S\.?|M\.?B\.?A\.?|"
    r"B\.?A\.?|M\.?A\.?|B\.?Sc\.?|M\.?Sc\.?|B\.?E\.?|M\.?E\.?|B\.?Tech\.?|M\.?Tech\.?)",
    re.IGNORECASE,
)

_EDU_INSTITUTIONS = re.compile(
    r"University|College|Institute|School|Academy|Polytechnic|Tech\b",
    re.IGNORECASE,
)

# Known false-positive ORG entities from NLP context (e.g., course names)
_FALSE_ORG = re.compile(
    r"^(Machine Learning|Deep Learning|Artificial Intelligence|Natural Language|"
    r"Data Science|Computer Science|Algorithms?|Neural Network|Cloud Computing|"
    r"Distributed Systems|Web Development|NLP)$",
    re.IGNORECASE,
)


def parse_education_section(section_text: str, nlp) -> list[dict]:
    """
    Parse education into structured entries.
    Handles concatenated PDF text (e.g., 'BachelorofScienceinCS').
    """
    if not section_text.strip():
        return []

    entries = _split_into_entries(section_text)
    if not entries:
        entries = [section_text]

    results = []
    for entry in entries:
        entry = _fix_concatenated_words(entry)
        entry_lines = [l.strip() for l in entry.splitlines() if l.strip()]
        if not entry_lines:
            continue

        # ── Degree ──
        degree_match = RE_DEGREE.search(entry)
        if not degree_match:
            # Fallback: liberal match without strict word boundaries (handles concatenated text)
            degree_match = _DEGREE_LIBERAL.search(entry)

        degree_str = None
        if degree_match:
            start = degree_match.start()
            # Extract a meaningful chunk: from the degree keyword to a GPA/year/comma
            end_m = re.search(r"GPA|Expected|Graduated|\d{4}", entry[start:])
            if end_m:
                degree_str = entry[start: start + end_m.start()].strip().rstrip(",;")
            else:
                degree_str = entry[start: start + 80].strip()
            degree_str = degree_str[:120]  # cap length

        if degree_str:
            degree_str = re.sub(
                r'\s*(Expected|Graduated|GPA|Cumulative|Dean).*$',
                '', degree_str, flags=re.IGNORECASE
            ).strip().rstrip(',:;')

        # ── GPA ──
        gpa_match = RE_GPA.search(entry)
        if not gpa_match:
            gpa_match = re.search(r"GPA[:\s]?(\d\.\d{1,2})", entry, re.IGNORECASE)
        gpa = float(gpa_match.group(1)) if gpa_match else None

        # ── Year ── (skip RE_YEAR \b boundaries — years may be adjacent to letters)
        years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", entry)]

        # ── Institution ──
        # 1. Look for a line with an institution keyword
        institution = None
        for line in entry_lines[:3]:  # institution usually near the top
            if _EDU_INSTITUTIONS.search(line):
                institution = line
                break

        if not institution:
            # 2. Try spaCy NER, filtering known false positives
            doc = nlp(entry[:300])
            orgs = [
                e.text for e in doc.ents
                if e.label_ == "ORG" and not _FALSE_ORG.match(e.text)
            ]
            institution = orgs[0] if orgs else None

        if not institution and entry_lines:
            # 3. Last resort: first line (likely has institution name)
            institution = entry_lines[0]

        results.append({
            "degree": degree_str,
            "institution": institution,
            "graduation_year": max(years) if years else None,
            "gpa": gpa,
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

    ranges = []
    for entry in work_entries:
        start = entry.get("start_year")
        end = entry.get("end_year") or current_year
        if start and isinstance(start, int) and isinstance(end, int) and start <= end:
            ranges.append((start, end))

    if ranges:
        ranges.sort()
        merged = [list(ranges[0])]
        for start, end in ranges[1:]:
            if start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        # Count at least 1 year per entry to handle single-year internships
        total = sum(max(end - start, 1) for start, end in merged)
        return float(min(total, 50))

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
    """Extract the candidate's professional summary."""
    if "summary" in sections:
        return sections["summary"][:600].strip()

    header = sections.get("header", "")
    if header:
        content_lines = []
        for line in header.splitlines():
            stripped = line.strip()
            if (stripped
                    and not RE_EMAIL.search(stripped)
                    and not RE_PHONE.search(stripped)
                    and not RE_URL_GENERIC.search(stripped)):
                content_lines.append(stripped)
        if content_lines:
            return " ".join(content_lines[:5])[:600]

    return raw_text[:500].strip()


# ─────────────────────────────────────────────
# CERTIFICATIONS + LANGUAGES
# ─────────────────────────────────────────────

def parse_certifications(section_text: str) -> list[str]:
    """Extract certification names as a list (one per line or bullet)."""
    if not section_text.strip():
        return []
    certs = []
    for line in section_text.splitlines():
        cleaned = line.strip().lstrip("-\u2022*\u20130123456789.").strip()
        if cleaned and len(cleaned) > 3:
            certs.append(cleaned)
    return certs[:20]


def parse_languages(section_text: str) -> list[str]:
    """Extract spoken languages from the languages section."""
    if not section_text.strip():
        return []
    langs = []
    items = re.split(r"[,\n\u2022\-\u2013]", section_text)
    for item in items:
        cleaned = re.sub(r"\(.*?\)|\[.*?\]|[-\u2013].*$", "", item).strip()
        cleaned = cleaned.lstrip("-\u2022*").strip()
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
    # Step 1: Extract raw text
    raw_text = extract_text(file_path)
    if not raw_text.strip():
        raise ValueError(
            "Could not extract any text from this resume. "
            "Make sure it is not a scanned image-only PDF."
        )
    raw_text = _clean_text(raw_text)

    # Step 2: Load spaCy (shared instance)
    nlp = spacy.load("en_core_web_md")

    # Step 3: Segment into sections
    sections = segment_sections(raw_text)

    # Step 4: Extract contact info from full text
    name     = extract_name(raw_text, nlp)
    email    = extract_email(raw_text)
    phone    = extract_phone(raw_text)
    linkedin = extract_linkedin(raw_text)
    github   = extract_github(raw_text)

    # Step 5: Parse each section
    work_entries      = parse_experience_section(sections.get("experience", ""), nlp)
    project_entries   = parse_project_section(sections.get("projects", ""))
    volunteer_entries = parse_volunteer_section(sections.get("volunteer", ""), nlp)
    education_entries = parse_education_section(
        _fix_concatenated_words(sections.get("education", "")), nlp
    )
    certifications    = parse_certifications(sections.get("certifications", ""))
    languages         = parse_languages(sections.get("languages", ""))

    # Step 6: Skill extraction — use the dedicated skills section as primary source.
    # Full-text extraction is too noisy for resumes (picks up skills mentioned
    # in context, e.g. "hypothesis testing" from "improving hypothesis testing
    # efficiency"). Fall back to full text only when no skills section exists.
    skills_section_text = sections.get("skills", "")
    if skills_section_text.strip():
        skills_result = extract_skills(skills_section_text)
    else:
        skills_result = extract_skills(raw_text)
    all_skills = list({
        s.lower(): s for s in
        skills_result["required"] + skills_result["preferred"]
    }.values())

    # Step 7: Calculate years of experience
    experience_years = calculate_experience_years(work_entries, raw_text)

    # Step 8: Extract summary
    summary = extract_summary(sections, raw_text)

    return {
        # Core fields (match ResumeProfile DB columns)
        "raw_text":          raw_text,
        "name":              name,
        "email":             email,
        "phone":             phone,
        "parsed_skills":     all_skills,
        "education":         education_entries,
        "experience_years":  experience_years,
        "summary":           summary,
        # Extended fields (v2)
        "work_experience":   work_entries,
        "projects":          project_entries,
        "volunteer":         volunteer_entries,
        "certifications":    certifications,
        "languages":         languages,
        "linkedin_url":      linkedin,
        "github_url":        github,
        "raw_sections":      {k: v[:500] for k, v in sections.items()},
    }
