# 02 — Debug Resume Parser (for Claude Code)

**Owner:** Claude Code.
**Goal:** Identify and fix the real parsing failures. Parser is already sophisticated — this is debugging, not rebuilding.
**Time box:** 1–2 hours.

## Context for CC

`jobspy/nlp/resume_parser.py` is a mature 3-layer parser:
- Layer 1: 200+ heading synonym dictionary (`SECTION_SYNONYMS`)
- Layer 2: Date-anchor segmentation for work/project entries
- Layer 3: ALL-CAPS + Title-Case structural fallback

Test suite at `tasks/test_resume_parser_v2.py` covers section detection, regex, segmentation, experience calc, certs, and languages. Uses `pdfplumber` (preferred) + `pypdf` (fallback) for PDF, `python-docx` for DOCX.

User reports: parser fails on "certain resume formats." No specifics given. Goal is to identify the actual failure modes empirically.

## Tasks

### Step 1 — Run the existing test suite (5 min)

```bash
cd /Users/kennethhou/Desktop/JobSpy/JobSpy
python tasks/test_resume_parser_v2.py
```

Confirm all tests pass. If any fail, fix those first — they're unit-level issues.

### Step 2 — Test against diverse real resumes (45 min)

Collect or create 5 diverse sample resumes in `data/resumes/test_samples/`:
- `01_standard_cs_onepage.pdf` — typical CS student, single column, standard section headers
- `02_twocol_pdf.pdf` — two-column PDF (most common failure mode)
- `03_docx_standard.docx` — DOCX with bullet points
- `04_minimal_sections.pdf` — resume that uses nonstandard headings like "Career Snapshot", "My Toolkit"
- `05_longform_5page.pdf` — senior engineer, 4+ pages, many work entries

If you don't have these, generate 2–3 synthetic ones using the text block below (save as .docx via Word/Pages, then export to PDF). Minimum: test with at least 3 real resumes.

Create `scripts/test_parser_real.py`:

```python
"""Run parse_resume on a directory of sample resumes and print diagnostic output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.nlp.resume_parser import parse_resume, segment_sections, extract_text

SAMPLES = Path("data/resumes/test_samples")

for resume_file in sorted(SAMPLES.glob("*")):
    if resume_file.suffix.lower() not in (".pdf", ".docx"):
        continue
    print(f"\n{'='*70}\n{resume_file.name}\n{'='*70}")

    try:
        raw = extract_text(str(resume_file))
        print(f"Raw text length: {len(raw)} chars")
        print(f"First 200 chars: {raw[:200]!r}")

        sections = segment_sections(raw)
        print(f"Sections detected: {list(sections.keys())}")

        result = parse_resume(str(resume_file))
        print(f"Name:            {result['name']}")
        print(f"Email:           {result['email']}")
        print(f"Phone:           {result['phone']}")
        print(f"Skills ({len(result['parsed_skills'])}): {result['parsed_skills'][:10]}")
        print(f"Experience yrs:  {result['experience_years']}")
        print(f"Work entries:    {len(result['work_experience'])}")
        print(f"Education:       {len(result['education'])}")
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")
```

Run it. Screenshot or copy the output. **Identify the failure patterns**, don't guess.

### Step 3 — Fix the top 2 failures (30–45 min)

Based on Step 2 output, the most likely failure patterns and their fixes:

**Failure A — Two-column PDF scrambles text order**
- `pdfplumber` already has `x_tolerance=3, y_tolerance=3` set, but it doesn't handle strict two-column layouts
- Fix: detect column structure by looking at x0 coordinates of text objects, extract each column separately
- Snippet to add to `extract_text_from_pdf`:

```python
with pdfplumber.open(file_path) as pdf:
    pages = []
    for page in pdf.pages:
        words = page.extract_words(x_tolerance=3)
        if not words:
            continue
        # Detect if this is a 2-column layout
        xs = sorted({round(w["x0"]) for w in words})
        page_width = page.width
        is_two_col = len(xs) > 10 and any(
            x0 > page_width * 0.45 and x0 < page_width * 0.55 for x0 in xs
        )
        if is_two_col:
            left = [w for w in words if w["x0"] < page_width / 2]
            right = [w for w in words if w["x0"] >= page_width / 2]
            left_text = " ".join(w["text"] for w in sorted(left, key=lambda w: (w["top"], w["x0"])))
            right_text = " ".join(w["text"] for w in sorted(right, key=lambda w: (w["top"], w["x0"])))
            pages.append(left_text + "\n" + right_text)
        else:
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                pages.append(text)
    return "\n".join(pages)
```

**Failure B — Skills section has zero skills extracted**
- Root cause is usually small `skills_taxonomy.csv` (see `03_fix_match_score.md`)
- Resume parser correctly prefers the skills section when present
- If the resume uses words like "Tableau" or "Snowflake" that aren't in the taxonomy, they won't appear
- Fix per `03_fix_match_score.md`, not this file

**Failure C — Parser raises ValueError "Could not extract any text"**
- Scanned image-only PDF. No cheap fix — OCR is out of scope for 48 hours
- Manual entry fallback in `frontend/profile.html` already handles this (user can type their skills)
- In the demo: frame this as "we explicitly catch scanned PDFs and route to manual entry — because silently mis-parsing an image would be worse than asking the user to confirm"

### Step 4 — Verify the manual-entry fallback actually works (15 min)

Check `frontend/profile.html`:
- When `/api/resume/upload` returns 422, does the UI show a useful error?
- Is there a way for the user to manually add skills if parsing was thin?

If not, add a minimal "Add skill" text input on the Profile page that POSTs to a new or existing endpoint to append to `parsed_skills`.

## Definition of done

- [ ] Existing test suite (`tasks/test_resume_parser_v2.py`) passes
- [ ] `scripts/test_parser_real.py` runs against 3+ real resumes with diagnostic output
- [ ] Top 2 observed failure modes addressed OR documented as known limits in `eval/edge_cases.md`
- [ ] Manual-entry path works when parsing is thin

## Demo framing

This is one of the project's most technically-impressive components. Use it.

> "Resume parsing is a 3-layer system: 200+ heading synonyms cover wording variations like 'Career Highlights' or 'My Toolkit', date-anchor segmentation extracts individual job entries, and structural ALL-CAPS / Title-Case fallback catches anything we didn't anticipate. When extraction is ambiguous, we route to a confirmation step rather than silently mis-parse — human-in-the-loop for the edge cases."
