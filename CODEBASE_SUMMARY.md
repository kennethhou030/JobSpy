# JobSpy Codebase Summary

This document is a complete reference for the JobSpy project. It is intended to be shared with an AI assistant to provide full context before assigning implementation tasks.

---

## Project Overview

JobSpy is a full-stack job aggregation web application. It scrapes live job postings from multiple job boards, stores them in a database, and presents them through a web frontend. The project is structured as:

- A Python scraping library (`jobspy/`)
- A REST API layer (`api/`)
- A frontend SPA (`frontend/`)

**Start command:**
```
uvicorn api.main:app --reload --port 8000
```
Frontend is served at `http://localhost:8000` (static files mounted at root by FastAPI).

---

## Directory Structure

```
JobSpy/
├── jobspy/
│   ├── __init__.py          # scrape_jobs() entry point
│   ├── model.py             # All Pydantic models + enums (JobPost, ScraperInput, Site, JobType, etc.)
│   ├── database.py          # SQLAlchemy ORM, DB persistence (save_jobs, query_jobs, etc.)
│   ├── util.py              # Shared utilities: salary extraction, text converters, desired_order
│   ├── exception.py         # Custom exceptions
│   ├── linkedin/
│   │   ├── __init__.py      # LinkedIn scraper class
│   │   ├── constant.py      # Headers, URL constants
│   │   └── util.py          # LinkedIn-specific helpers (is_job_remote, etc.)
│   ├── indeed/
│   │   ├── __init__.py      # Indeed scraper (GraphQL API)
│   │   ├── constant.py
│   │   └── util.py
│   ├── glassdoor/
│   │   ├── __init__.py      # Glassdoor scraper
│   │   ├── constant.py
│   │   └── util.py
│   ├── google/
│   │   ├── __init__.py      # Google Jobs scraper
│   │   ├── constant.py
│   │   └── util.py
│   ├── ziprecruiter/
│   │   ├── __init__.py
│   │   ├── constant.py
│   │   └── util.py
│   ├── bayt/
│   │   └── __init__.py      # Bayt scraper (Middle East)
│   ├── naukri/
│   │   ├── __init__.py      # Naukri scraper (India)
│   │   ├── constant.py
│   │   └── util.py
│   └── bdjobs/
│       ├── __init__.py      # BDJobs scraper (Bangladesh)
│       ├── constant.py
│       └── util.py
├── api/
│   ├── __init__.py          # Package marker
│   ├── main.py              # FastAPI app, all REST endpoints
│   └── schemas.py           # Pydantic request/response schemas
├── frontend/
│   ├── index.html           # Dashboard SPA (main page)
│   ├── scraper.html         # Manual scraper control page
│   ├── history.html         # Scrape session audit log page
│   └── js/
│       └── api.js           # Shared API client (window.API) + formatting helpers (window.fmt)
└── jobspy.db                # SQLite database (auto-created on first run)
```

---

## Core Data Models (`jobspy/model.py`)

### `JobPost` (Pydantic BaseModel)
The canonical job record. Fields:
```python
id: str                        # site-prefixed e.g. "linkedin-4012345678"
title: str
company_name: str
job_url: str
job_url_direct: str
location: Location             # city, state, country
description: str               # markdown/html/plain depending on description_format
company_url: str
company_url_direct: str
job_type: list[JobType]
compensation: Compensation     # interval, min_amount, max_amount, currency
date_posted: date
emails: list[str]
is_remote: bool
listing_type: str
job_level: str                 # LinkedIn
company_industry: str          # LinkedIn + Indeed
job_function: str              # LinkedIn
company_addresses: str         # Indeed
company_num_employees: str     # Indeed
company_revenue: str           # Indeed
company_description: str       # Indeed
company_logo: str              # Indeed
banner_photo_url: str          # Indeed
skills: list[str]              # Naukri
experience_range: str          # Naukri
company_rating: float          # Naukri
company_reviews_count: int     # Naukri
vacancy_count: int             # Naukri
work_from_home_type: str       # Naukri ("Hybrid", "Remote")
```

### `ScraperInput` (Pydantic BaseModel)
Input to all scrapers:
```python
site_type: list[Site]
search_term: str
google_search_term: str        # override for Google Jobs only
location: str
country: Country               # default USA
distance: int                  # miles, default 50
is_remote: bool
job_type: JobType
easy_apply: bool               # LinkedIn/Indeed only
offset: int
linkedin_fetch_description: bool
linkedin_company_ids: list[int]
description_format: DescriptionFormat  # markdown | html | plain
results_wanted: int            # default 15
hours_old: int
```

### Key Enums
- `Site`: `linkedin`, `indeed`, `zip_recruiter`, `glassdoor`, `google`, `bayt`, `naukri`, `bdjobs`
- `JobType`: `fulltime`, `parttime`, `contract`, `temporary`, `internship`, `per_diem`, `nights`, `other`, `summer`, `volunteer` (with 40+ language translations)
- `CompensationInterval`: `yearly`, `monthly`, `weekly`, `daily`, `hourly`
- `DescriptionFormat`: `markdown`, `html`, `plain`
- `SalarySource`: `direct_data`, `description`
- `Country`: 60+ countries with Indeed/Glassdoor subdomain mappings

### `Scraper` (Abstract Base Class)
```python
class Scraper(ABC):
    def __init__(self, site: Site, proxies, ca_cert, user_agent): ...
    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...
```
All 8 platform scrapers inherit from this.

---

## Main Entry Point: `scrape_jobs()` (`jobspy/__init__.py`)

```python
def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    user_agent: str = None,
) -> pd.DataFrame
```

**What it does:**
1. Maps `site_name` strings to `Site` enum values
2. Builds a `ScraperInput` object
3. Launches all scrapers concurrently via `ThreadPoolExecutor`
4. For each job returned: normalizes location, job_type, emails, salary (direct or regex-extracted from description)
5. Assembles a `pd.DataFrame` with 34 columns in `desired_order`
6. Sorts by `site` ASC, `date_posted` DESC
7. Returns the DataFrame

**Salary extraction logic:**
- If structured compensation data exists in the API response → use it (`salary_source = "direct_data"`)
- Otherwise (USA only) → run `extract_salary()` regex on description text (`salary_source = "description"`)
- Regex pattern: `r"\$(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)\s*[-—–]\s*(?:\$)?(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)"`
- Thresholds: min < 350 → hourly, min < 30000 → monthly, else yearly
- Annual conversion: hourly × 2080, monthly × 12, weekly × 52, daily × 260

**Canonical DataFrame columns (34 total, `desired_order`):**
```
id, site, job_url, job_url_direct, title, company, location, date_posted,
job_type, salary_source, interval, min_amount, max_amount, currency,
is_remote, job_level, job_function, listing_type, emails, description,
company_industry, company_url, company_logo, company_url_direct,
company_addresses, company_num_employees, company_revenue, company_description,
skills, experience_range, company_rating, company_reviews_count,
vacancy_count, work_from_home_type
```

---

## Scraper Implementations

| Site | File | Method | Notes |
|---|---|---|---|
| LinkedIn | `jobspy/linkedin/__init__.py` | BeautifulSoup HTML parsing | 25 jobs/page, supports company ID filter, easy apply filter |
| Indeed | `jobspy/indeed/__init__.py` | GraphQL API (`apis.indeed.com/graphql`) | 100 jobs/page, cursor-based pagination |
| Glassdoor | `jobspy/glassdoor/__init__.py` | API + BeautifulSoup | Country-aware via `Country.glassdoor_domain_value` |
| Google Jobs | `jobspy/google/__init__.py` | Google Jobs API/scraping | Uses `google_search_term` override |
| ZipRecruiter | `jobspy/ziprecruiter/__init__.py` | API | US/Canada only |
| Bayt | `jobspy/bayt/__init__.py` | HTML scraping | Middle East focus |
| Naukri | `jobspy/naukri/__init__.py` | API | India, returns skills/experience_range/ratings |
| BDJobs | `jobspy/bdjobs/__init__.py` | HTML scraping | Bangladesh |

All scrapers use `create_session()` from `jobspy/util.py` which returns either a `TLSRotating` or `RequestsRotating` session with optional proxy rotation.

---

## Utilities (`jobspy/util.py`)

| Function | Description |
|---|---|
| `extract_salary(salary_str, ...)` | Regex salary extraction from description text |
| `extract_job_type(description)` | Keyword matching for job type from description |
| `extract_emails_from_text(text)` | Regex email extraction |
| `markdown_converter(html)` | HTML → Markdown via `markdownify` |
| `plain_converter(html)` | HTML → plain text via BeautifulSoup |
| `currency_parser(cur_str)` | Normalize currency strings to float |
| `convert_to_annual(job_data)` | Convert hourly/monthly/weekly/daily salary to annual in-place |
| `create_session(...)` | Create TLS or standard rotating proxy HTTP session |
| `map_str_to_site(name)` | Convert string to `Site` enum |
| `get_enum_from_value(value_str)` | Convert string to `JobType` enum |
| `desired_order` | List of 34 canonical column names in order |

**Remote detection** (in scraper util files):
```python
remote_keywords = ["remote", "work from home", "wfh"]
full_string = f'{title} {description} {location}'.lower()
is_remote = any(keyword in full_string for keyword in remote_keywords)
```

---

## Database Layer (`jobspy/database.py`)

**Engine:** SQLAlchemy, defaulting to SQLite (`jobspy.db`). Switch to PostgreSQL via env var:
```
DATABASE_URL=postgresql://user:password@localhost:5432/jobspy
```
SQLite uses WAL mode for concurrent reads.

### ORM Tables

**`jobs` table** — primary key is site-prefixed id (e.g. `"linkedin-4012345678"`):
- All 34 DataFrame columns as typed columns
- `first_seen_at` (DateTime) — set on INSERT, never updated
- `last_seen_at` (DateTime) — updated on every upsert
- Indexes on: `site`, `title`, `company`, `location`, `date_posted`, `is_remote`

**`scrape_sessions` table** — audit log of every scrape run:
- `id`, `created_at`, `site_names`, `search_term`, `location`, `distance`, `is_remote`, `job_type`, `results_wanted`, `results_returned`, `hours_old`, `country_indeed`, etc.

### Public Functions

```python
create_tables() -> None
# Creates all tables if not exist. Called on FastAPI startup.

save_jobs(df: pd.DataFrame) -> int
# Upserts DataFrame into jobs table. Returns count of upserted rows.
# Skips rows without an id. Updates existing rows except first_seen_at.

query_jobs(site, title, company, location, is_remote, min_salary, date_from, limit, offset) -> pd.DataFrame
# Queries jobs table. String filters use ILIKE (case-insensitive substring).
# Sorted: date_posted DESC, first_seen_at DESC.

get_job_by_id(job_id: str) -> dict | None
delete_job(job_id: str) -> bool

create_session_record(...) -> int
# Inserts a ScrapeSession row and returns its auto-generated id.

get_sessions(limit, offset) -> list[dict]
# Returns scrape sessions newest-first.
```

---

## REST API (`api/main.py`)

Built with **FastAPI**. Auto-generates Swagger UI at `/docs` and ReDoc at `/redoc`.

CORS: open to all origins (for development).

Frontend static files served from `frontend/` mounted at `/` (must be last route).

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/sites` | List of supported site names |
| `GET` | `/api/job_types` | List of job type values |
| `POST` | `/api/scrape` | Trigger live scrape + save to DB, returns jobs |
| `GET` | `/api/jobs` | Query stored jobs with filters + pagination |
| `GET` | `/api/jobs/{job_id}` | Get single job by ID |
| `DELETE` | `/api/jobs/{job_id}` | Delete a job |
| `GET` | `/api/sessions` | List past scrape sessions |

### `POST /api/scrape` — `ScrapeRequest` fields:
```
site_name, search_term, google_search_term, location, distance,
is_remote, job_type, easy_apply, results_wanted, country_indeed,
description_format, linkedin_fetch_description, linkedin_company_ids,
offset, hours_old, enforce_annual_salary, verbose
```

### `GET /api/jobs` — Query parameters:
```
site (exact match), title (ILIKE), company (ILIKE), location (ILIKE),
is_remote (bool), min_salary (float >=), date_from (YYYY-MM-DD),
limit (default 50, max 500), offset (default 0)
```

---

## Pydantic Schemas (`api/schemas.py`)

| Schema | Used For |
|---|---|
| `ScrapeRequest` | Body of `POST /api/scrape` |
| `ScrapeResponse` | `{ total_found, total_saved, jobs: list[dict] }` |
| `JobRecord` | Single job (all 30+ fields optional) |
| `JobListResponse` | `{ total, jobs: list[dict] }` |
| `SiteListResponse` | `{ sites: list[str] }` |
| `JobTypeListResponse` | `{ job_types: list[str] }` |

---

## Frontend (`frontend/`)

**Tech stack:** Vanilla JavaScript, Tailwind CSS (CDN), Google Fonts (Plus Jakarta Sans + Material Symbols). No build step.

### Pages

| File | Purpose |
|---|---|
| `index.html` | Main dashboard: search, results table, job detail panel |
| `scraper.html` | Manual scraper control with advanced options |
| `history.html` | Scrape session audit log |

### `frontend/js/api.js` — Shared across all pages via `<script>` tag

**`window.API`** — API client:
```javascript
API.scrapeJobs(params)       // POST /api/scrape
API.queryJobs(filters)       // GET /api/jobs?...
API.getJob(id)               // GET /api/jobs/{id}
API.deleteJob(id)            // DELETE /api/jobs/{id}
API.fetchSites()             // GET /api/sites
API.fetchJobTypes()          // GET /api/job_types
API.fetchSessions(limit, offset)  // GET /api/sessions
```

**`window.fmt`** — formatting helpers:
```javascript
fmt.salary(min, max, interval, currency)  // "$80k – $120k" or "$45/hr"
fmt.relDate(dateStr)                       // "2 days ago", "1w ago"
fmt.siteBadge(site)                        // colored pill HTML
fmt.jobTypeLabel(jt)                       // "fulltime" → "Full-time"
fmt.jobTypeParam(label)                    // "Full-time" → "fulltime"
```

### Dashboard (`index.html`) — Layout

3-column layout:
1. **Left sidebar** — Database filters: remote toggle, min salary slider, site select, company dropdown
2. **Center** — Results table with columns: Source | Job Information | Location | Salary | Link
3. **Right panel** — Job detail panel (hidden until row is clicked)

**Key JS state variables:**
```javascript
let allJobs = [];          // current results array
let selectedJobId = null;
let currentOffset = 0;
let pageSize = 50;
let totalFound = 0, totalSaved = 0;
let filterState = {};      // active filter values
```

**Key JS functions:**
```javascript
runScrape()         // reads form, calls API.scrapeJobs(), renders table
loadFromDB()        // reads filterState, calls API.queryJobs(), renders table
selectJob(idx)      // highlights row, renders detail panel
renderTable(jobs)   // generates all job rows
renderDetailPanel(j)// renders right panel with full job details
```

**Filtering:**
- **Freshly scraped results** — client-side in-memory filtering over `allJobs` array, no network request
- **Saved/DB results** — query parameters sent to `GET /api/jobs`, backend runs SQLAlchemy ILIKE queries

**Job detail panel shows:**
- Company logo, job title, job level/seniority
- Salary box (formatted)
- Apply button (direct URL or proxy)
- Company metadata (industry, size, revenue)
- Skills list (Naukri-sourced jobs)
- Full description (markdown rendered as HTML)
- Delete button (calls `API.deleteJob()`)

---

## What Does NOT Exist Yet (Planned Features)

These features are planned but not yet implemented:

1. **Resume upload + parsing** — PDF/text resume ingestion, NLP extraction of skills/experience/education (planned: spaCy or NLTK)
2. **Job-resume match scoring** — Compare extracted resume keywords against job description, output 0–100% match score displayed in detail panel
3. **Cover letter generation** — Send resume info + job description to OpenAI GPT API via structured prompt, return tailored cover letter via "Generate Cover Letter" button
4. **Job title alias expansion** — Expand user input query to related job titles automatically

---

## Dependencies

Defined in `pyproject.toml` (Poetry):
```
python = "^3.10"
requests = "^2.31.0"
beautifulsoup4 = "^4.12.2"
pandas = "^2.1.0"
numpy = ">=1.26.0"
pydantic = "^2.3.0"
tls-client = "^1.0.1"
markdownify = "^1.1.0"
regex = "^2024.4.28"
fastapi
uvicorn[standard]
sqlalchemy
```

---

## Data Flow Summary

```
User (browser)
  → POST /api/scrape (FastAPI)
    → scrape_jobs() [jobspy/__init__.py]
      → ThreadPoolExecutor runs all scrapers concurrently
        → Each scraper: HTTP requests → parse HTML/JSON → return JobResponse
      → Normalize each job (salary, location, job_type, emails)
      → Assemble DataFrame (34 cols, sorted)
    → save_jobs(df) [jobspy/database.py] — upsert to SQLite/PostgreSQL
    → create_session_record() — log scrape metadata
    → Return ScrapeResponse { total_found, total_saved, jobs }
  ← Browser renders job table
  → User clicks row → detail panel shown
  → User clicks "Load Saved" → GET /api/jobs?filters → SQLAlchemy query → return jobs
```
