"""
main.py - FastAPI application for JobSpy.

Run with:
    uvicorn api.main:app --reload --port 8000

Interactive docs at:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)
"""
from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from jobspy import scrape_jobs
from jobspy.model import Site, JobType
from jobspy.platform_selector import select_platforms, get_platform_info
from jobspy.nlp.match_scorer import score_job_against_resume
from jobspy.database import (
    create_tables,
    save_jobs,
    query_jobs,
    count_jobs,
    get_job_by_id,
    delete_job,
    create_session_record,
    get_sessions,
    save_resume_profile,
    get_resume_profile,
    ResumeProfile,
    SessionLocal,
    save_cover_letter,
    get_cover_letter,
    list_cover_letters,
)
from jobspy.nlp.resume_parser import parse_resume
from jobspy.nlp.cover_letter import generate_cover_letter
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

@app.get(
    "/api/platforms",
    summary="Get auto-selected platforms for a location",
    tags=["meta"],
)
async def get_platforms_for_location(location: str = "") -> dict:
    """Returns which platforms will be auto-selected for a given location."""
    return get_platform_info(location)


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
    selected_sites = select_platforms(
        location=request.location or "",
        override=request.site_name if request.site_name else None,
    )

    try:
        df: pd.DataFrame = scrape_jobs(
            site_name=selected_sites,
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
    sort_by: Optional[str] = Query(None, description="Sort field: 'match_score' to sort by resume match"),
) -> JobListResponse:
    """
    Query jobs already stored in the database.

    All string filters are case-insensitive substring matches.
    Results are sorted newest-first. Pass sort_by=match_score to sort by resume match.
    """
    resume = get_resume_profile(user_id="default")
    resume_dict = {"parsed_skills": resume.parsed_skills or []} if resume else None

    filter_kwargs = dict(
        site=site,
        title=title,
        company=company,
        location=location,
        is_remote=is_remote,
        min_salary=min_salary,
        date_from=date_from,
    )

    if sort_by == "match_score" and resume_dict:
        # Fetch ALL matching jobs, score them all, then paginate in Python
        # so that page 2+ returns the correct globally-sorted results.
        df = query_jobs(**filter_kwargs, limit=None)
        all_records = (
            df.where(pd.notna(df), None).to_dict(orient="records")
            if not df.empty
            else []
        )
        for job_data in all_records:
            result = score_job_against_resume(
                {
                    "required_skills": job_data.get("required_skills") or [],
                    "preferred_skills": job_data.get("preferred_skills") or [],
                },
                resume_dict,
            )
            job_data["match_score"] = result["match_score"]
            job_data["skill_gap"] = result["skill_gap"]
        all_records.sort(key=lambda j: j.get("match_score") or 0, reverse=True)
        total = len(all_records)
        records = all_records[offset: offset + limit]
    else:
        # Normal path: DB-level pagination, then enrich the page with scores.
        total = count_jobs(**filter_kwargs)
        df = query_jobs(**filter_kwargs, limit=limit, offset=offset)
        records = (
            df.where(pd.notna(df), None).to_dict(orient="records")
            if not df.empty
            else []
        )
        for job_data in records:
            if resume_dict:
                result = score_job_against_resume(
                    {
                        "required_skills": job_data.get("required_skills") or [],
                        "preferred_skills": job_data.get("preferred_skills") or [],
                    },
                    resume_dict,
                )
                job_data["match_score"] = result["match_score"]
                job_data["skill_gap"] = result["skill_gap"]
            else:
                job_data["match_score"] = None
                job_data["skill_gap"] = None

    return JobListResponse(total=total, jobs=records)


@app.get(
    "/api/jobs/{job_id}/match",
    summary="Get match score and skill gap for a job vs. stored resume",
    tags=["jobs"],
)
def get_job_match(job_id: str) -> dict:
    """
    Compute match score and skill gap for a specific job against the stored resume.
    Returns 404 if no resume is uploaded or job not found.
    """
    resume = get_resume_profile(user_id="default")
    if not resume:
        raise HTTPException(
            status_code=404,
            detail="No resume uploaded. Please upload your resume on the Profile page first.",
        )

    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    result = score_job_against_resume(
        {
            "required_skills": job.get("required_skills") or [],
            "preferred_skills": job.get("preferred_skills") or [],
        },
        {"parsed_skills": resume.parsed_skills or []},
    )
    return {
        "job_id": job_id,
        "job_title": job.get("title"),
        "company": job.get("company"),
        **result,
    }


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
# Resume endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/resume/upload",
    summary="Upload and parse a resume (PDF or DOCX)",
    tags=["resume"],
)
async def upload_resume(file: UploadFile = File(...)) -> dict:
    """
    Upload a resume (PDF or DOCX). Parses it and stores the profile persistently.
    For the MVP, uses user_id='default' (single-user mode).
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    save_dir = Path("data/resumes")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"default_resume{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        parsed = parse_resume(str(save_path))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse resume: {str(e)}")

    profile_data = {
        "file_path": str(save_path),
        "original_filename": filename,
        **parsed,
    }
    profile = save_resume_profile(profile_data, user_id="default")

    return {
        "message":           "Resume uploaded and parsed successfully.",
        "name":              profile.name,
        "email":             profile.email,
        "phone":             profile.phone,
        "skills_count":      len(profile.parsed_skills or []),
        "experience_years":  profile.experience_years,
        "education_count":   len(profile.education or []),
        "work_entries":      len(getattr(profile, "work_experience", None) or []),
        "projects_count":    len(getattr(profile, "projects", None) or []),
        "volunteer_count":   len(getattr(profile, "volunteer", None) or []),
        "certifications":    getattr(profile, "certifications", None) or [],
        "languages":         getattr(profile, "languages", None) or [],
        "linkedin_url":      getattr(profile, "linkedin_url", None),
        "github_url":        getattr(profile, "github_url", None),
        "sections_detected": list((getattr(profile, "raw_sections", None) or {}).keys()),
    }


@app.get(
    "/api/resume",
    summary="Get the stored resume profile",
    tags=["resume"],
)
async def get_resume() -> dict:
    """Retrieve the currently stored resume profile."""
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
        # Skills
        "parsed_skills":     profile.parsed_skills or [],
        # Structured sections
        "work_experience":   getattr(profile, "work_experience", None) or [],
        "projects":          getattr(profile, "projects", None) or [],
        "volunteer":         getattr(profile, "volunteer", None) or [],
        "education":         profile.education or [],
        "certifications":    getattr(profile, "certifications", None) or [],
        "languages":         getattr(profile, "languages", None) or [],
        # Meta
        "original_filename": profile.original_filename,
        "uploaded_at":       profile.uploaded_at.isoformat() if profile.uploaded_at else None,
        "sections_detected": list((getattr(profile, "raw_sections", None) or {}).keys()),
    }


@app.delete(
    "/api/resume",
    summary="Delete the stored resume profile",
    tags=["resume"],
)
async def delete_resume() -> dict:
    """Delete the stored resume profile and the uploaded file."""
    with SessionLocal() as session:
        profile = session.query(ResumeProfile).filter_by(user_id="default").first()
        if not profile:
            raise HTTPException(status_code=404, detail="No resume found.")
        if profile.file_path and Path(profile.file_path).exists():
            Path(profile.file_path).unlink()
        session.delete(profile)
        session.commit()
    return {"message": "Resume deleted."}


# ---------------------------------------------------------------------------
# Cover letter endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/cover-letter/{job_id}",
    summary="Generate a cover letter for a job",
    tags=["cover-letter"],
)
async def create_cover_letter(job_id: str) -> dict:
    """
    Generate a tailored cover letter for the given job using the stored resume.
    Requires a resume to be uploaded first. Saves the letter for later retrieval.
    """
    resume = get_resume_profile(user_id="default")
    if not resume:
        raise HTTPException(
            status_code=404,
            detail="No resume uploaded. Please upload your resume on the Profile page first.",
        )

    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    resume_dict = {
        "name": resume.name,
        "summary": resume.summary,
        "parsed_skills": resume.parsed_skills or [],
        "experience_years": resume.experience_years,
    }
    job_dict = {
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "description": job.get("description"),
        "required_skills": job.get("required_skills") or [],
        "preferred_skills": job.get("preferred_skills") or [],
    }

    try:
        cover_letter_text = generate_cover_letter(resume_dict, job_dict)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {str(e)}")

    from jobspy.nlp.match_scorer import compute_match_score
    match_score = compute_match_score(
        resume_dict["parsed_skills"],
        job_dict["required_skills"],
        job_dict["preferred_skills"],
    )

    cl = save_cover_letter(
        job_id=job_id,
        cover_letter_text=cover_letter_text,
        job_title=job.get("title"),
        company_name=job.get("company"),
        match_score=match_score,
    )

    return {
        "job_id": job_id,
        "job_title": job.get("title"),
        "company": job.get("company"),
        "match_score": match_score,
        "cover_letter_text": cover_letter_text,
        "generated_at": cl.generated_at.isoformat(),
    }


@app.get(
    "/api/cover-letter/{job_id}",
    summary="Retrieve a saved cover letter",
    tags=["cover-letter"],
)
async def get_cover_letter_endpoint(job_id: str) -> dict:
    """Retrieve a previously generated cover letter for a job."""
    cl = get_cover_letter(job_id=job_id, user_id="default")
    if not cl:
        raise HTTPException(
            status_code=404,
            detail=f"No cover letter found for job '{job_id}'. Generate one first.",
        )
    return {
        "job_id": cl.job_id,
        "job_title": cl.job_title,
        "company": cl.company_name,
        "match_score": cl.match_score,
        "cover_letter_text": cl.cover_letter_text,
        "generated_at": cl.generated_at.isoformat(),
    }


@app.get(
    "/api/cover-letters",
    summary="List all generated cover letters",
    tags=["cover-letter"],
)
async def list_cover_letters_endpoint() -> dict:
    """List all generated cover letters for the current user."""
    letters = list_cover_letters(user_id="default")
    return {
        "total": len(letters),
        "cover_letters": [
            {
                "job_id": cl.job_id,
                "job_title": cl.job_title,
                "company_name": cl.company_name,
                "match_score": cl.match_score,
                "generated_at": cl.generated_at.isoformat(),
                "cover_letter_text": cl.cover_letter_text,
            }
            for cl in letters
        ],
    }


# ---------------------------------------------------------------------------
# Serve the frontend/ directory as static files at root (must be last)
# ---------------------------------------------------------------------------
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
