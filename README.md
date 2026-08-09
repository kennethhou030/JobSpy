# JobSpy

A full-stack job aggregation platform that scrapes 8 major job boards concurrently, enriches results with NLP-powered skill extraction and resume matching, and generates personalized AI cover letters — all through a clean web UI and REST API.

---

## Features

### Multi-Platform Job Scraping
- Scrapes **LinkedIn**, **Indeed**, **Glassdoor**, **Google Jobs**, **ZipRecruiter**, **Bayt**, **Naukri**, and **BDJobs** concurrently via `ThreadPoolExecutor`
- Unified output as a single pandas DataFrame (34 normalized columns)
- Per-scraper failure isolation — one site failing does not stop the rest
- TLS fingerprint rotation for LinkedIn to reduce blocking

### Smart Platform Auto-Selection
- Automatically includes region-specific boards based on location
  - **India** → Naukri (Bangalore, Mumbai, Delhi, Hyderabad, etc.)
  - **Middle East** → Bayt (UAE, Dubai, Saudi Arabia, Qatar, Egypt, etc.)
  - **Bangladesh** → BDJobs (Dhaka, Chittagong)
  - **North America** → ZipRecruiter (USA, Canada)
- User overrides always respected

### Advanced Salary Extraction
- Pulls structured salary data from job board APIs when available
- Falls back to regex extraction from description text
- Handles ranges like `$80k – $120k`, `$45/hr`, `$150,000 - $220,000`
- Auto-normalizes to annual salary (hourly × 2080, monthly × 12, etc.)
- Tracks `salary_source` ("direct_data" vs "description")

### Resume Parsing (PDF & DOCX)
- 3-layer detection system:
  1. **Synonym-based section boundary detection** — 200+ heading synonyms mapped to canonicals (Summary, Skills, Experience, Education, Projects, Volunteer, Certifications, Languages, Awards, Publications, References)
  2. **Date-anchor segmentation** — extracts work/project entries by date range patterns
  3. **Structural fallback** — ALL-CAPS and Title-Case detection for unrecognized headings
- Extracts: name, email, phone, LinkedIn/GitHub URLs, summary, skills, work experience, education, projects, certifications, languages
- Calculates `experience_years` from date ranges

### NLP Skill Extraction
- spaCy `PhraseMatcher` against a curated 1000+ skill taxonomy (`data/skills_taxonomy.csv`)
- Context-aware classification:
  - **Required signals:** "required", "must have", "mandatory", "essential", "you need"
  - **Preferred signals:** "preferred", "nice to have", "bonus", "plus", "ideally", "optional"
  - Defaults to required if no signal found
- Runs automatically on every job description at scrape time

### Job–Resume Match Scoring
- Weighted formula: `(required_match × 0.70) + (preferred_match × 0.30)` → score 0–100%
- 100+ skill alias normalizations (e.g., "nodejs", "node js", "Node.js" all → "node.js")
- Returns full skill gap: matched / missing required / missing preferred
- Results exposed via API and visible in the UI when a resume is uploaded

### AI Cover Letter Generation
- Powered by Claude API (Anthropic) — `claude-opus-4-6`
- System prompt enforces: conversational tone, 3–4 paragraphs of prose, no bullet points, no hollow openers, never invents credentials
- Incorporates candidate profile + job details + matched/missing skills
- Generated letters persisted to DB for later retrieval

### Database Persistence
- SQLAlchemy ORM — SQLite by default, PostgreSQL-ready via `DATABASE_URL` env var
- Upsert strategy: first-seen vs last-seen timestamps, no duplicates on re-scrape
- Tables: `jobs`, `scrape_sessions` (audit log), `resume_profile`, `cover_letter`
- WAL mode enabled on SQLite for concurrent reads

### REST API (FastAPI)
- Full Swagger UI at `/docs`, ReDoc at `/redoc`
- Endpoints for: scraping, job CRUD, resume upload/retrieval, match scoring, cover letter generation/retrieval, session history
- Pagination, filtering (site, title, company, location, remote, min salary, date), and sorting (by date or match score)

### Web Frontend (No Build Step)
- Vanilla JS + Tailwind CSS via CDN — no Node.js, no bundler
- **Dashboard** — filter/sort jobs, click-to-expand job detail with skills, description, salary, apply link
- **Profile** — upload resume (PDF/DOCX), view parsed contact info, skills, experience, education
- **Scraper** — advanced control over all scrape parameters
- **History** — paginated audit log of past scrape sessions

### Proxy & Anti-Bot Support
- Round-robin proxy rotation across all scrapers
- CA certificate pinning support
- `tls-client` for TLS fingerprint rotation (LinkedIn)

---

## Quick Start

### Requirements

- Python >= 3.10
- [Poetry](https://python-poetry.org/) (recommended) or pip

### Install

```bash
git clone https://github.com/kennethhou030/JobSpy.git
cd JobSpy
poetry install
```

Or with pip:

```bash
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...       # Required for cover letter generation
DATABASE_URL=sqlite:///jobspy.db   # Optional; defaults to SQLite
```

### Download spaCy language model

```bash
python -m spacy download en_core_web_sm
```

### Run the API & Frontend

```bash
uvicorn api.main:app --reload --port 8000
```

- Frontend: [http://localhost:8000](http://localhost:8000)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Library Usage

Use JobSpy as a standalone Python library with no API server required:

```python
import csv
from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "linkedin", "zip_recruiter", "google"],
    search_term="software engineer",
    google_search_term="software engineer jobs near San Francisco, CA since yesterday",
    location="San Francisco, CA",
    results_wanted=20,
    hours_old=72,
    country_indeed="USA",
    description_format="markdown",  # "html" or "plain" also supported
    # enforce_annual_salary=True,
    # proxies=["208.195.175.46:65095", "localhost"],
    # linkedin_fetch_description=True,  # slower but richer data
)

print(f"Found {len(jobs)} jobs")
jobs.to_csv("jobs.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
```

### Output Columns

| Column | Description |
|--------|-------------|
| `site` | Source platform |
| `job_url` | Direct link to posting |
| `job_url_direct` | Employer's direct URL (when available) |
| `title` | Job title |
| `company` | Company name |
| `location` | City, state, country |
| `date_posted` | Posting date |
| `job_type` | fulltime / parttime / contract / internship / etc. |
| `salary_source` | "direct_data" or "description" |
| `interval` | yearly / monthly / hourly |
| `min_amount` / `max_amount` | Salary range |
| `currency` | e.g., USD, EUR |
| `is_remote` | Boolean |
| `job_level` | e.g., Senior, Entry Level |
| `job_function` | e.g., Engineering, Marketing |
| `company_industry` | Industry classification |
| `description` | Full job description (markdown/html/plain) |
| `skills` | Platform-provided skills (Naukri) |
| `required_skills` | NLP-extracted required skills |
| `preferred_skills` | NLP-extracted preferred skills |
| `emails` | Contact emails from description |
| `company_logo` | Logo URL |
| `company_url` | Company website |
| `company_url_direct` | Direct company link |
| `company_addresses` | Office addresses |
| `company_num_employees` | Employee count range |
| `company_revenue` | Revenue estimate |
| `company_description` | Company blurb |
| `company_rating` | Platform rating (Naukri, Glassdoor) |
| `ceo_name` / `ceo_photo_url` | CEO info (Glassdoor) |
| `logo_photo_url` / `banner_photo_url` | Media (Glassdoor) |
| `experience_range` | Experience required (Naukri) |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `site_name` | list[str] | all sites | Platforms to scrape |
| `search_term` | str | required | Job search query |
| `google_search_term` | str | None | Override for Google Jobs |
| `location` | str | None | City, state, or country |
| `distance` | int | 50 | Radius in miles |
| `is_remote` | bool | False | Remote jobs only |
| `job_type` | str | None | fulltime / parttime / contract / internship |
| `easy_apply` | bool | False | Easy apply only (LinkedIn) |
| `results_wanted` | int | 15 | Max results per site |
| `country_indeed` | str | "usa" | Country for Indeed/Glassdoor |
| `hours_old` | int | None | Max age of listings in hours |
| `enforce_annual_salary` | bool | False | Filter out non-annual postings |
| `description_format` | str | "markdown" | "markdown" / "html" / "plain" |
| `linkedin_fetch_description` | bool | False | Fetch full LinkedIn descriptions (slower) |
| `linkedin_company_ids` | list[int] | None | Filter LinkedIn by company IDs |
| `proxies` | list[str] | None | Proxy list for rotation |
| `verbose` | int | 0 | Logging verbosity (0–2) |
| `offset` | int | 0 | Pagination offset |

---

## REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sites` | List all supported platforms |
| `GET` | `/api/job_types` | List all job type values |
| `GET` | `/api/platforms?location=<str>` | Auto-selected platforms for location |
| `POST` | `/api/scrape` | Trigger a live scrape, save to DB |
| `GET` | `/api/jobs` | Query jobs with filters + pagination |
| `GET` | `/api/jobs/{id}` | Get single job by ID |
| `DELETE` | `/api/jobs/{id}` | Delete a job |
| `GET` | `/api/jobs/{id}/match` | Match score + skill gap for job |
| `POST` | `/api/resume/upload` | Upload PDF/DOCX resume |
| `GET` | `/api/resume` | Get parsed resume profile |
| `DELETE` | `/api/resume` | Delete resume and profile |
| `POST` | `/api/cover-letter/{job_id}` | Generate AI cover letter |
| `GET` | `/api/cover-letter/{job_id}` | Retrieve generated cover letter |
| `GET` | `/api/cover-letters` | List all generated cover letters |
| `GET` | `/api/sessions` | Scrape session audit log |

---

## Project Structure

```
JobSpy/
├── jobspy/                    # Core library
│   ├── __init__.py            # scrape_jobs() entry point
│   ├── model.py               # Pydantic models (JobPost, ScraperInput, enums)
│   ├── database.py            # SQLAlchemy ORM + upsert logic
│   ├── util.py                # Salary extraction, text helpers
│   ├── platform_selector.py   # Location-aware platform selection
│   ├── nlp/
│   │   ├── resume_parser.py   # 3-layer PDF/DOCX resume parser
│   │   ├── skill_extractor.py # PhraseMatcher skill extraction
│   │   ├── match_scorer.py    # Weighted job-resume scoring
│   │   └── cover_letter.py    # Claude API cover letter generation
│   ├── linkedin/
│   ├── indeed/
│   ├── glassdoor/
│   ├── google/
│   ├── ziprecruiter/
│   ├── bayt/
│   ├── naukri/
│   └── bdjobs/
├── api/
│   ├── main.py                # FastAPI app + all endpoints
│   └── schemas.py             # Request/response Pydantic models
├── frontend/
│   ├── index.html             # Job dashboard
│   ├── profile.html           # Resume upload & display
│   ├── scraper.html           # Scraper control panel
│   ├── history.html           # Scrape session log
│   ├── applications.html      # Application tracker
│   └── js/api.js              # Shared HTTP client + formatters
├── data/
│   └── skills_taxonomy.csv    # 1000+ skills for NLP matching
├── evaluation/                # Match scoring & cover letter eval
├── scripts/                   # Cron jobs, migrations, exports
├── pyproject.toml
└── .env                       # ANTHROPIC_API_KEY, DATABASE_URL
```

---

## Supported Job Types

`fulltime`, `parttime`, `internship`, `contract`, `temporary`, and 35+ multilingual variants (French, German, Spanish, Portuguese, Dutch, Italian, Polish, Swedish, Norwegian, Danish).

## Supported Countries (Indeed/Glassdoor)

60+ countries including USA, UK, Canada, Australia, India, Germany, France, Brazil, Singapore, UAE, and more — each mapped to the correct regional subdomain.

---

## Notes

- LinkedIn scraping uses TLS fingerprint rotation via `tls-client`. For high-volume use, proxies are recommended.
- Cover letter generation requires an `ANTHROPIC_API_KEY` in your `.env`.
- The default database is SQLite (`jobspy.db`). Set `DATABASE_URL` to a PostgreSQL connection string for production.
- spaCy requires downloading a language model: `python -m spacy download en_core_web_sm`
