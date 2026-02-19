"""
main.py - FastAPI application for JobSpy.

Run with:
    uvicorn api.main:app --reload --port 8000

Interactive docs at:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from jobspy import scrape_jobs
from jobspy.model import Site, JobType
from jobspy.database import (
    create_tables,
    save_jobs,
    query_jobs,
    get_job_by_id,
    delete_job,
    create_session_record,
    get_sessions,
)
from api.schemas import (
    ScrapeRequest,
    ScrapeResponse,
    JobListResponse,
    SiteListResponse,
    JobTypeListResponse,
)


# ---------------------------------------------------------------------------
# Application lifespan: create DB tables on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="JobSpy API",
    description=(
        "REST API that wraps the JobSpy scraping library and persists results "
        "to a relational database (SQLite by default, PostgreSQL via DATABASE_URL)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Restrict to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Metadata endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/sites",
    response_model=SiteListResponse,
    summary="List supported job boards",
    tags=["meta"],
)
def get_sites() -> SiteListResponse:
    """Return every job board name that JobSpy supports."""
    return SiteListResponse(sites=[site.value for site in Site])


@app.get(
    "/api/job_types",
    response_model=JobTypeListResponse,
    summary="List supported job types",
    tags=["meta"],
)
def get_job_types() -> JobTypeListResponse:
    """Return every job type value that can be passed as job_type."""
    return JobTypeListResponse(job_types=[jt.value[0] for jt in JobType])


# ---------------------------------------------------------------------------
# Scraping endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/scrape",
    response_model=ScrapeResponse,
    summary="Trigger a job scrape",
    tags=["scrape"],
)
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    """
    Invoke scrape_jobs() with the supplied parameters, persist the results
    to the database, and return the scraped jobs.

    - **site_name**: which job boards to hit (array or single string)
    - **search_term**: keyword / job title
    - **location**: city/state/country string
    - **results_wanted**: upper bound on rows returned
    """
    try:
        df: pd.DataFrame = scrape_jobs(
            site_name=request.site_name,
            search_term=request.search_term,
            google_search_term=request.google_search_term,
            location=request.location,
            distance=request.distance,
            is_remote=request.is_remote,
            job_type=request.job_type,
            easy_apply=request.easy_apply,
            results_wanted=request.results_wanted,
            country_indeed=request.country_indeed,
            description_format=request.description_format,
            linkedin_fetch_description=request.linkedin_fetch_description,
            linkedin_company_ids=request.linkedin_company_ids,
            offset=request.offset,
            hours_old=request.hours_old,
            enforce_annual_salary=request.enforce_annual_salary,
            verbose=request.verbose,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Persist to DB
    saved_count = save_jobs(df)

    # Log the session
    if not df.empty:
        site_names = (
            request.site_name
            if isinstance(request.site_name, list)
            else [request.site_name]
        )
        create_session_record(
            site_names=site_names,
            search_term=request.search_term,
            google_search_term=request.google_search_term,
            location=request.location,
            distance=request.distance,
            is_remote=request.is_remote,
            job_type=request.job_type,
            easy_apply=request.easy_apply,
            results_wanted=request.results_wanted,
            results_returned=len(df),
            country_indeed=request.country_indeed,
            hours_old=request.hours_old,
            enforce_annual_salary=request.enforce_annual_salary,
            description_format=request.description_format,
        )

    # Serialise to plain dicts (handles date/NaN objects)
    records = (
        df.where(pd.notna(df), None)
        .assign(date_posted=lambda d: d["date_posted"].astype(str).where(d["date_posted"].notna(), None))
        .to_dict(orient="records")
    ) if not df.empty else []

    return ScrapeResponse(
        total_found=len(df),
        total_saved=saved_count,
        jobs=records,
    )


# ---------------------------------------------------------------------------
# Query / CRUD endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/jobs",
    response_model=JobListResponse,
    summary="Query stored jobs",
    tags=["jobs"],
)
def get_jobs(
    site: Optional[str] = Query(None, description="Filter by job board (e.g. linkedin)"),
    title: Optional[str] = Query(None, description="Case-insensitive substring match on title"),
    company: Optional[str] = Query(None, description="Case-insensitive substring match on company"),
    location: Optional[str] = Query(None, description="Case-insensitive substring match on location"),
    is_remote: Optional[bool] = Query(None, description="true = remote only"),
    min_salary: Optional[float] = Query(None, description="Minimum annual salary filter"),
    date_from: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD) — only jobs posted on or after"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> JobListResponse:
    """
    Query jobs already stored in the database.

    All string filters are case-insensitive substring matches.
    Results are sorted newest-first.
    """
    df = query_jobs(
        site=site,
        title=title,
        company=company,
        location=location,
        is_remote=is_remote,
        min_salary=min_salary,
        date_from=date_from,
        limit=limit,
        offset=offset,
    )

    records = (
        df.where(pd.notna(df), None).to_dict(orient="records")
        if not df.empty
        else []
    )
    return JobListResponse(total=len(records), jobs=records)


@app.get(
    "/api/jobs/{job_id}",
    summary="Get a single job by ID",
    tags=["jobs"],
)
def get_job(job_id: str) -> dict:
    """Retrieve a single job record by its site-prefixed ID."""
    job = get_job_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@app.delete(
    "/api/jobs/{job_id}",
    summary="Delete a job by ID",
    tags=["jobs"],
)
def remove_job(job_id: str) -> dict:
    """Delete a job record from the database."""
    deleted = delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return {"deleted": True, "id": job_id}


@app.get(
    "/api/sessions",
    summary="List scrape sessions",
    tags=["sessions"],
)
def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """Return past scrape session records, newest first."""
    sessions = get_sessions(limit=limit, offset=offset)
    # Convert datetime objects to strings for JSON serialisation
    for s in sessions:
        for k, v in s.items():
            if hasattr(v, "isoformat"):
                s[k] = v.isoformat()
    return {"total": len(sessions), "sessions": sessions}


# ---------------------------------------------------------------------------
# Serve the frontend/ directory as static files at root (must be last)
# ---------------------------------------------------------------------------
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
