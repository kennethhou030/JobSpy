"""
schemas.py - Pydantic request/response models for the JobSpy REST API.

These schemas are the contract between the frontend and the backend.
Variable names here map 1-to-1 with scrape_jobs() parameters.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    """
    Maps directly to scrape_jobs() keyword arguments.
    All optional fields mirror the function's defaults.
    """
    site_name: list[str] | str = Field(
        default=["linkedin", "indeed"],
        description=(
            "One or more job boards to scrape. "
            "Valid values: linkedin, indeed, zip_recruiter, glassdoor, "
            "google, bayt, naukri, bdjobs"
        ),
        examples=[["linkedin", "indeed"]],
    )
    search_term: Optional[str] = Field(
        None,
        description="Job title / keyword to search for",
        examples=["Python Developer"],
    )
    google_search_term: Optional[str] = Field(
        None,
        description="Override search term specifically for Google Jobs",
    )
    location: Optional[str] = Field(
        None,
        description="City, state, or country string",
        examples=["San Francisco, CA"],
    )
    distance: Optional[int] = Field(
        50,
        ge=0,
        description="Search radius in miles",
    )
    is_remote: bool = Field(False, description="Filter for remote-only jobs")
    job_type: Optional[str] = Field(
        None,
        description="fulltime | parttime | contract | temporary | internship | per_diem | nights | other | summer | volunteer",
    )
    easy_apply: Optional[bool] = Field(
        None,
        description="Filter for Easy Apply jobs (LinkedIn / Indeed only)",
    )
    results_wanted: int = Field(
        15,
        ge=1,
        le=500,
        description="Maximum number of results to return",
    )
    country_indeed: str = Field(
        "usa",
        description="Country for Indeed / Glassdoor domain selection",
        examples=["usa", "uk", "canada", "australia"],
    )
    description_format: str = Field(
        "markdown",
        description="Output format for job descriptions: markdown | html | plain",
    )
    linkedin_fetch_description: bool = Field(
        False,
        description="Fetch full descriptions from LinkedIn job detail pages (slower)",
    )
    linkedin_company_ids: Optional[list[int]] = Field(
        None,
        description="Restrict LinkedIn results to these company numeric IDs",
    )
    offset: int = Field(0, ge=0, description="Pagination offset")
    hours_old: Optional[int] = Field(
        None,
        description="Only include jobs posted within this many hours",
    )
    enforce_annual_salary: bool = Field(
        False,
        description="Normalise all salary figures to annual equivalents",
    )
    verbose: int = Field(
        0,
        ge=0,
        le=2,
        description="Logging verbosity: 0=ERROR, 1=WARNING, 2=INFO",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "site_name": ["linkedin", "indeed"],
                "search_term": "Software Engineer",
                "location": "Austin, TX",
                "is_remote": False,
                "job_type": "fulltime",
                "results_wanted": 25,
                "country_indeed": "usa",
                "hours_old": 72,
                "enforce_annual_salary": True,
            }
        }
    }


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class JobRecord(BaseModel):
    """Single job record as returned by the API."""
    id: Optional[str] = None
    site: Optional[str] = None
    job_url: Optional[str] = None
    job_url_direct: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    date_posted: Optional[str] = None
    job_type: Optional[str] = None
    salary_source: Optional[str] = None
    interval: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = None
    is_remote: Optional[bool] = None
    job_level: Optional[str] = None
    job_function: Optional[str] = None
    listing_type: Optional[str] = None
    emails: Optional[str] = None
    description: Optional[str] = None
    company_industry: Optional[str] = None
    company_url: Optional[str] = None
    company_logo: Optional[str] = None
    company_url_direct: Optional[str] = None
    company_addresses: Optional[str] = None
    company_num_employees: Optional[str] = None
    company_revenue: Optional[str] = None
    company_description: Optional[str] = None
    skills: Optional[str] = None
    experience_range: Optional[str] = None
    company_rating: Optional[float] = None
    company_reviews_count: Optional[int] = None
    vacancy_count: Optional[int] = None
    work_from_home_type: Optional[str] = None

    model_config = {"from_attributes": True}


class ScrapeResponse(BaseModel):
    """Response from POST /api/scrape."""
    total_found: int = Field(description="Number of jobs returned by scrapers")
    total_saved: int = Field(description="Number of jobs upserted into the database")
    jobs: list[dict[str, Any]] = Field(description="Array of job records")


class JobListResponse(BaseModel):
    """Response from GET /api/jobs."""
    total: int = Field(description="Number of records in this page")
    jobs: list[dict[str, Any]]


class SiteListResponse(BaseModel):
    sites: list[str]


class JobTypeListResponse(BaseModel):
    job_types: list[str]
