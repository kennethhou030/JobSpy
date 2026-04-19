# JobSpy Full-Stack — 前端技术策划书 (Frontend Technical Specification)

**Version:** 1.0
**Backend:** FastAPI + JobSpy scraping library + SQLite/PostgreSQL
**Frontend Target:** React (recommended) or any SPA framework; spec is Stitch AI-compatible
**Base API URL:** `http://localhost:8000`

---

## 1. System Overview (系统概述)

```
┌──────────────────────────────────────────────────────────┐
│                     Browser / SPA                        │
│                                                          │
│  [Search Form]  →  POST /api/scrape  →  [Results Table]  │
│  [Filter Panel] →  GET  /api/jobs   →  [Job Detail Card] │
└──────────────────────────────────────────────────────────┘
         │                                      ↑
         ▼                                      │
┌──────────────────────────────────────────────────────────┐
│              FastAPI  (api/main.py)                       │
│                                                          │
│  POST /api/scrape   →  scrape_jobs()  →  save_jobs()     │
│  GET  /api/jobs     →  query_jobs()                      │
│  GET  /api/sites    →  list of Site enum values          │
│  GET  /api/job_types→  list of JobType enum values       │
│  GET  /api/jobs/:id →  single job record                 │
│  DELETE /api/jobs/:id → remove job                       │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│            SQLite / PostgreSQL                            │
│  tables: jobs, scrape_sessions                           │
└──────────────────────────────────────────────────────────┘
```

---

## 2. API Mapping (API 映射)

### 2.1 Endpoints Required by the Frontend

| Method | Path | Purpose | Called by |
|--------|------|---------|-----------|
| `GET` | `/api/sites` | Populate the site checkboxes | App init |
| `GET` | `/api/job_types` | Populate the job-type dropdown | App init |
| `POST` | `/api/scrape` | Trigger a fresh scrape | Search button |
| `GET` | `/api/jobs` | Query stored jobs with filters | Filter panel / pagination |
| `GET` | `/api/jobs/{id}` | Show full job detail | Row click |
| `DELETE` | `/api/jobs/{id}` | Remove a saved job | Detail panel button |

### 2.2 POST /api/scrape — Request Body

```jsonc
// Maps exactly to ScrapeRequest in api/schemas.py
{
  "site_name":              ["linkedin", "indeed"],   // array of strings
  "search_term":            "Software Engineer",
  "google_search_term":     null,
  "location":               "San Francisco, CA",
  "distance":               50,
  "is_remote":              false,
  "job_type":               "fulltime",               // or null
  "easy_apply":             null,
  "results_wanted":         25,
  "country_indeed":         "usa",
  "description_format":     "markdown",
  "linkedin_fetch_description": false,
  "linkedin_company_ids":   null,
  "offset":                 0,
  "hours_old":              72,
  "enforce_annual_salary":  true,
  "verbose":                0
}
```

### 2.3 POST /api/scrape — Response Shape

```jsonc
{
  "total_found": 48,
  "total_saved": 48,
  "jobs": [
    {
      "id": "linkedin-4012345678",
      "site": "linkedin",
      "job_url": "https://www.linkedin.com/jobs/view/4012345678",
      "job_url_direct": "https://acme.com/apply?job=123",
      "title": "Senior Software Engineer",
      "company": "Acme Corp",
      "location": "San Francisco, CA",
      "date_posted": "2024-01-15",
      "job_type": "fulltime",
      "salary_source": "direct_data",
      "interval": "yearly",
      "min_amount": 150000,
      "max_amount": 220000,
      "currency": "USD",
      "is_remote": false,
      "job_level": "Senior",
      "job_function": "Engineering",
      "listing_type": null,
      "emails": null,
      "description": "## About the role\n...",
      "company_industry": "Technology",
      "company_url": "https://acme.com/careers",
      "company_logo": "https://cdn.linkedin.com/logo.png",
      "company_url_direct": "https://acme.com",
      "company_addresses": null,
      "company_num_employees": "1001-5000",
      "company_revenue": null,
      "company_description": null,
      "skills": null,
      "experience_range": null,
      "company_rating": null,
      "company_reviews_count": null,
      "vacancy_count": null,
      "work_from_home_type": null
    }
    // ...
  ]
}
```

### 2.4 GET /api/jobs — Query Parameters

| Param | Type | Description |
|-------|------|-------------|
| `site` | string | Exact match: `linkedin`, `indeed`, etc. |
| `title` | string | Substring search (case-insensitive) |
| `company` | string | Substring search |
| `location` | string | Substring search |
| `is_remote` | boolean | `true` / `false` |
| `min_salary` | number | Minimum `min_amount` value |
| `date_from` | string | ISO date `YYYY-MM-DD` |
| `limit` | integer | Page size (1–500, default 50) |
| `offset` | integer | Pagination offset (default 0) |

---

## 3. State Variables (状态变量)

All state variables below are named to **match backend field names exactly** so no mapping layer is needed.

### 3.1 Search Form State (`searchForm`)

```typescript
interface SearchFormState {
  // ── Mirrors ScrapeRequest fields ──────────────────────────────────────
  site_name:                string[];          // default: ["linkedin","indeed"]
  search_term:              string;            // default: ""
  location:                 string;            // default: ""
  distance:                 number;            // default: 50
  is_remote:                boolean;           // default: false
  job_type:                 string | null;     // default: null
  easy_apply:               boolean | null;    // default: null
  results_wanted:           number;            // default: 25
  country_indeed:           string;            // default: "usa"
  description_format:       string;            // default: "markdown"
  linkedin_fetch_description: boolean;         // default: false
  hours_old:                number | null;     // default: null (no filter)
  enforce_annual_salary:    boolean;           // default: false

  // ── UI-only state ─────────────────────────────────────────────────────
  isLoading:                boolean;
  error:                    string | null;
}
```

### 3.2 Filter Panel State (`filterState`)

```typescript
// Controls GET /api/jobs parameters for querying the stored database
interface FilterState {
  site:         string | null;    // maps to ?site=
  title:        string;           // maps to ?title=
  company:      string;           // maps to ?company=
  location:     string;           // maps to ?location=
  is_remote:    boolean | null;
  min_salary:   number | null;
  date_from:    string | null;    // "YYYY-MM-DD"
  limit:        number;           // default: 50
  offset:       number;           // default: 0
}
```

### 3.3 Results State (`resultsState`)

```typescript
interface ResultsState {
  jobs:         JobRecord[];      // array of job objects from API
  total_found:  number;           // from scrape response
  total_saved:  number;           // from scrape response
  selectedJob:  JobRecord | null; // job currently shown in detail panel
}
```

### 3.4 App State (metadata, loaded once)

```typescript
interface AppMetaState {
  availableSites:     string[];   // from GET /api/sites
  availableJobTypes:  string[];   // from GET /api/job_types
}
```

### 3.5 JobRecord Type (mirrors API response)

```typescript
interface JobRecord {
  id:                   string | null;
  site:                 string | null;
  job_url:              string | null;
  job_url_direct:       string | null;
  title:                string | null;
  company:              string | null;
  location:             string | null;
  date_posted:          string | null;   // "YYYY-MM-DD"
  job_type:             string | null;
  salary_source:        string | null;
  interval:             string | null;
  min_amount:           number | null;
  max_amount:           number | null;
  currency:             string | null;
  is_remote:            boolean | null;
  job_level:            string | null;
  job_function:         string | null;
  listing_type:         string | null;
  emails:               string | null;
  description:          string | null;
  company_industry:     string | null;
  company_url:          string | null;
  company_logo:         string | null;
  company_url_direct:   string | null;
  company_addresses:    string | null;
  company_num_employees:string | null;
  company_revenue:      string | null;
  company_description:  string | null;
  skills:               string | null;
  experience_range:     string | null;
  company_rating:       number | null;
  company_reviews_count:number | null;
  vacancy_count:        number | null;
  work_from_home_type:  string | null;
}
```

---

## 4. UI Components (界面组件)

### 4.1 Component Tree

```
<App>
├── <NavBar />                      # Logo + app title
├── <SearchPanel />                 # Main scrape trigger
│   ├── <SearchBar />               # search_term text input
│   ├── <LocationInput />           # location text input
│   ├── <SiteCheckboxGroup />       # site_name checkboxes
│   ├── <JobTypeSelect />           # job_type dropdown
│   ├── <DistanceSlider />          # distance (0–200 miles)
│   ├── <ResultsLimitInput />       # results_wanted number input
│   ├── <AdvancedOptionsPanel />    # collapsible
│   │   ├── <CountrySelect />       # country_indeed
│   │   ├── <HoursOldInput />       # hours_old
│   │   ├── <RemoteToggle />        # is_remote
│   │   ├── <EasyApplyToggle />     # easy_apply
│   │   ├── <AnnualSalaryToggle />  # enforce_annual_salary
│   │   └── <LinkedInOptions />     # linkedin_fetch_description
│   └── <SearchButton />            # triggers POST /api/scrape
│
├── <FilterPanel />                 # Filters for stored DB jobs
│   ├── <SiteFilter />              # ?site=
│   ├── <TitleFilter />             # ?title=
│   ├── <CompanyFilter />           # ?company=
│   ├── <LocationFilter />          # ?location=
│   ├── <RemoteFilter />            # ?is_remote=
│   ├── <SalaryFilter />            # ?min_salary=
│   └── <DateFromFilter />          # ?date_from= (date picker)
│
├── <ResultsSection />
│   ├── <ResultsStats />            # "X jobs found, Y saved"
│   ├── <ResultsTable />            # paginated table of JobRecord[]
│   │   └── <JobRow />              # one row, click opens detail
│   └── <Pagination />              # limit/offset controls
│
└── <JobDetailPanel />              # Side panel or modal
    ├── <JobHeader />               # title, company, location, date
    ├── <SalaryBadge />             # min_amount–max_amount interval currency
    ├── <MetaTags />                # site, job_type, is_remote, job_level
    ├── <CompanyCard />             # logo, industry, num_employees, revenue
    ├── <DescriptionBody />         # rendered markdown/html description
    ├── <SkillsTags />              # skills (Naukri)
    └── <ActionButtons />           # "Open URL", "Open Direct URL", "Delete"
```

### 4.2 Component Specifications

#### `<SearchBar />`
- Type: `<input type="text">`
- Bound to: `searchForm.search_term`
- Placeholder: "Job title, keywords, or company"
- On Enter key: submit form

#### `<LocationInput />`
- Type: `<input type="text">`
- Bound to: `searchForm.location`
- Placeholder: "City, State, or Country (e.g. Austin, TX)"

#### `<SiteCheckboxGroup />`
- Renders one `<input type="checkbox">` per item in `availableSites`
- Label map: `{ linkedin: "LinkedIn", indeed: "Indeed", zip_recruiter: "ZipRecruiter", glassdoor: "Glassdoor", google: "Google Jobs", bayt: "Bayt", naukri: "Naukri", bdjobs: "BDJobs" }`
- Bound to: `searchForm.site_name` (array — add/remove on toggle)
- Default checked: `["linkedin", "indeed"]`

#### `<JobTypeSelect />`
- Type: `<select>`
- Options: `["(any)", ...availableJobTypes]`
- Bound to: `searchForm.job_type` (null when "(any)" is selected)
- Display labels: `{ fulltime: "Full Time", parttime: "Part Time", contract: "Contract", temporary: "Temporary", internship: "Internship" }`

#### `<DistanceSlider />`
- Type: `<input type="range" min="0" max="200" step="5">`
- Bound to: `searchForm.distance`
- Shows live value label: "50 miles"

#### `<ResultsLimitInput />`
- Type: `<input type="number" min="1" max="500">`
- Bound to: `searchForm.results_wanted`
- Default: `25`

#### `<CountrySelect />`
- Type: `<select>` (searchable)
- Options: full country list from `jobspy/model.py` Country enum
- Key values: `usa, uk, canada, australia, germany, france, india, ...`
- Bound to: `searchForm.country_indeed`

#### `<HoursOldInput />`
- Type: `<input type="number" min="1">`
- Bound to: `searchForm.hours_old`
- Placeholder: "Leave blank for all time"

#### `<SearchButton />`
- Triggers: `POST /api/scrape` with `searchForm` as body
- Shows: loading spinner while `searchForm.isLoading === true`
- Disabled when: `searchForm.search_term` is empty OR no sites selected

#### `<ResultsTable />`
Columns (left to right):

| Column Header | Field | Format |
|---------------|-------|--------|
| Source | `site` | Badge with color per site |
| Title | `title` | Clickable link → job detail |
| Company | `company` | Text + logo thumbnail if `company_logo` |
| Location | `location` | Text |
| Posted | `date_posted` | Relative date ("3 days ago") |
| Type | `job_type` | Badge |
| Remote | `is_remote` | ✓ / ✗ icon |
| Salary | `min_amount` + `max_amount` + `interval` | "$120k–$180k/yr" |
| Level | `job_level` | Text |
| Link | `job_url` | External link icon |

#### `<JobDetailPanel />`
- Opens as right-side drawer or modal on row click
- Populates from `resultsState.selectedJob`
- Description rendered as Markdown (use `react-markdown` or similar)
- "Open Job URL" button: `window.open(job.job_url)`
- "Apply Direct" button: `window.open(job.job_url_direct)` (hidden if null)
- "Delete" button: `DELETE /api/jobs/{job.id}` then remove from list

---

## 5. Data Flow (数据流)

### 5.1 App Initialization

```
Browser loads SPA
    │
    ├── GET /api/sites      →  appMeta.availableSites    = ["linkedin","indeed",...]
    └── GET /api/job_types  →  appMeta.availableJobTypes = ["fulltime","parttime",...]
```

### 5.2 Scrape Flow (new search)

```
User fills SearchPanel → clicks [Search]
    │
    ▼
searchForm.isLoading = true
    │
    ▼
POST /api/scrape
Body: {
    site_name: searchForm.site_name,          // ← exact field name match
    search_term: searchForm.search_term,
    location: searchForm.location,
    distance: searchForm.distance,
    is_remote: searchForm.is_remote,
    job_type: searchForm.job_type,
    easy_apply: searchForm.easy_apply,
    results_wanted: searchForm.results_wanted,
    country_indeed: searchForm.country_indeed,
    hours_old: searchForm.hours_old,
    enforce_annual_salary: searchForm.enforce_annual_salary,
    linkedin_fetch_description: searchForm.linkedin_fetch_description,
    description_format: searchForm.description_format,
}
    │
    ▼
Response: { total_found, total_saved, jobs: JobRecord[] }
    │
    ├── resultsState.jobs        = response.jobs
    ├── resultsState.total_found = response.total_found
    ├── resultsState.total_saved = response.total_saved
    └── searchForm.isLoading = false
    │
    ▼
ResultsTable re-renders with resultsState.jobs
```

### 5.3 Filter Flow (query stored jobs)

```
User adjusts FilterPanel controls
    │
    ▼
Debounced (300ms) GET /api/jobs?
    site=filterState.site
    &title=filterState.title
    &company=filterState.company
    &location=filterState.location
    &is_remote=filterState.is_remote
    &min_salary=filterState.min_salary
    &date_from=filterState.date_from
    &limit=filterState.limit
    &offset=filterState.offset
    │
    ▼
Response: { total, jobs: JobRecord[] }
    │
    ▼
resultsState.jobs = response.jobs
ResultsTable re-renders
```

### 5.4 Pagination Flow

```
User clicks page N in <Pagination />
    │
    ▼
filterState.offset = (N - 1) * filterState.limit
    │
    ▼
Triggers Filter Flow (§5.3) with updated offset
```

### 5.5 Job Detail Flow

```
User clicks a <JobRow />
    │
    ▼
resultsState.selectedJob = job   (from local resultsState.jobs array)
    │
    ▼
<JobDetailPanel /> opens and renders selectedJob
```

---

## 6. API Client Module (apiClient.ts)

```typescript
// frontend/src/api/jobspyClient.ts

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchSites(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/api/sites`);
  const data = await res.json();
  return data.sites;
}

export async function fetchJobTypes(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/api/job_types`);
  const data = await res.json();
  return data.job_types;
}

export async function scrapeJobs(params: ScrapeRequest): Promise<ScrapeResponse> {
  const res = await fetch(`${BASE_URL}/api/scrape`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function queryJobs(filters: FilterState): Promise<JobListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== null && v !== "" && v !== undefined) params.set(k, String(v));
  });
  const res = await fetch(`${BASE_URL}/api/jobs?${params.toString()}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJob(id: string): Promise<JobRecord> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Not found");
  return res.json();
}

export async function deleteJob(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}
```

---

## 7. Step-by-Step Execution Plan (执行计划)

### Phase 1 — Backend Foundation

| Step | Action | File(s) |
|------|--------|---------|
| 1.1 | Install new dependencies | `pyproject.toml` |
| 1.2 | Verify `jobspy/database.py` tables create correctly | Run `python -c "from jobspy.database import create_tables; create_tables()"` |
| 1.3 | Test `save_jobs()` with a real scrape | Quick script |
| 1.4 | Run `uvicorn api.main:app --reload` and open `/docs` | Manual |
| 1.5 | Test `POST /api/scrape` via Swagger UI | Manual |

### Phase 2 — Frontend Scaffold

| Step | Action |
|------|--------|
| 2.1 | `npm create vite@latest jobspy-ui -- --template react-ts` |
| 2.2 | Install: `axios` or native fetch, `react-markdown`, `date-fns`, UI library (e.g. shadcn/ui or Tailwind) |
| 2.3 | Create `src/api/jobspyClient.ts` (see §6) |
| 2.4 | Create state types in `src/types/index.ts` (see §3) |

### Phase 3 — Core Components

| Step | Component | Consumes |
|------|-----------|---------|
| 3.1 | `<SiteCheckboxGroup />` | `GET /api/sites` |
| 3.2 | `<JobTypeSelect />` | `GET /api/job_types` |
| 3.3 | `<SearchPanel />` (form) | Assembles `ScrapeRequest` |
| 3.4 | `<ResultsTable />` | `resultsState.jobs` |
| 3.5 | `<JobDetailPanel />` | `resultsState.selectedJob` |
| 3.6 | `<FilterPanel />` | `GET /api/jobs` |
| 3.7 | `<Pagination />` | `filterState.offset/limit` |

### Phase 4 — Integration & Polish

| Step | Action |
|------|--------|
| 4.1 | Wire `<SearchButton />` → `scrapeJobs()` → update `resultsState` |
| 4.2 | Wire `<FilterPanel />` → debounced `queryJobs()` → update `resultsState` |
| 4.3 | Wire row click → `resultsState.selectedJob` → open `<JobDetailPanel />` |
| 4.4 | Wire "Delete" button → `deleteJob()` → remove from local list |
| 4.5 | Add error boundaries and loading skeletons |
| 4.6 | Add salary formatting helper: `"$120,000 – $180,000 / yr"` |
| 4.7 | Add relative date helper: `"3 days ago"` using `date-fns` |

### Phase 5 — Production Hardening

| Step | Action |
|------|--------|
| 5.1 | Switch `DATABASE_URL` to PostgreSQL connection string |
| 5.2 | Add Alembic for database migrations |
| 5.3 | Restrict CORS `allow_origins` to frontend domain |
| 5.4 | Add rate-limiting middleware (slowapi) |
| 5.5 | Add background task queue (Celery + Redis) so scrapes don't block the HTTP response |
| 5.6 | Add `GET /api/sessions` endpoint to show scrape history |

---

## 8. New Dependencies to Add (新增依赖)

Add to `pyproject.toml`:

```toml
[tool.poetry.dependencies]
# Backend API
fastapi       = "^0.115.0"
uvicorn       = {extras = ["standard"], version = "^0.30.0"}
sqlalchemy    = "^2.0.0"

# Optional: PostgreSQL driver
# psycopg2-binary = "^2.9.0"
```

Install:
```bash
poetry add fastapi "uvicorn[standard]" sqlalchemy
```

Start server:
```bash
uvicorn api.main:app --reload --port 8000
```

---

## 9. Field-to-Column Mapping Reference (字段对照表)

| `scrape_jobs()` return column | DB column (`jobs` table) | API response field | UI display label |
|---|---|---|---|
| `id` | `id` (PK) | `id` | — (internal) |
| `site` | `site` | `site` | Source |
| `job_url` | `job_url` | `job_url` | Job Link |
| `job_url_direct` | `job_url_direct` | `job_url_direct` | Apply Link |
| `title` | `title` | `title` | Title |
| `company` | `company` | `company` | Company |
| `location` | `location` | `location` | Location |
| `date_posted` | `date_posted` | `date_posted` | Posted |
| `job_type` | `job_type` | `job_type` | Type |
| `salary_source` | `salary_source` | `salary_source` | Salary Source |
| `interval` | `interval` | `interval` | Pay Period |
| `min_amount` | `min_amount` | `min_amount` | Min Salary |
| `max_amount` | `max_amount` | `max_amount` | Max Salary |
| `currency` | `currency` | `currency` | Currency |
| `is_remote` | `is_remote` | `is_remote` | Remote |
| `job_level` | `job_level` | `job_level` | Level |
| `job_function` | `job_function` | `job_function` | Function |
| `listing_type` | `listing_type` | `listing_type` | Listing Type |
| `emails` | `emails` | `emails` | Contact |
| `description` | `description` | `description` | Description |
| `company_industry` | `company_industry` | `company_industry` | Industry |
| `company_url` | `company_url` | `company_url` | Company Page |
| `company_logo` | `company_logo` | `company_logo` | Logo |
| `company_url_direct` | `company_url_direct` | `company_url_direct` | Company Site |
| `company_addresses` | `company_addresses` | `company_addresses` | Offices |
| `company_num_employees` | `company_num_employees` | `company_num_employees` | Team Size |
| `company_revenue` | `company_revenue` | `company_revenue` | Revenue |
| `company_description` | `company_description` | `company_description` | About Company |
| `skills` | `skills` | `skills` | Skills |
| `experience_range` | `experience_range` | `experience_range` | Experience |
| `company_rating` | `company_rating` | `company_rating` | Rating |
| `company_reviews_count` | `company_reviews_count` | `company_reviews_count` | Reviews |
| `vacancy_count` | `vacancy_count` | `vacancy_count` | Openings |
| `work_from_home_type` | `work_from_home_type` | `work_from_home_type` | WFH Type |
