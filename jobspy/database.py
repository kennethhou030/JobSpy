"""
database.py - Persistence layer for JobSpy.

Supports SQLite (default, zero-config) and PostgreSQL (production).
Set the DATABASE_URL environment variable to switch:

    # SQLite (default)
    DATABASE_URL=sqlite:///jobspy.db

    # PostgreSQL
    DATABASE_URL=postgresql://user:password@localhost:5432/jobspy

Usage:
    from jobspy.database import create_tables, save_jobs, query_jobs

    create_tables()                          # Run once on startup
    n = save_jobs(df)                        # Upsert a scrape_jobs() DataFrame
    results_df = query_jobs(title="Python")  # Query stored jobs
"""
from __future__ import annotations

import os
from datetime import datetime, date
from typing import Optional

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Engine / session setup
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///jobspy.db")

_connect_args: dict = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)

# Enable WAL mode for SQLite to allow concurrent reads
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class ScrapeSession(Base):
    """Records metadata for every call to scrape_jobs()."""
    __tablename__ = "scrape_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    site_names = Column(String(255))          # e.g. "linkedin,indeed"
    search_term = Column(String(255))
    google_search_term = Column(String(255))
    location = Column(String(255))
    distance = Column(Integer)
    is_remote = Column(Boolean, default=False)
    job_type = Column(String(50))
    easy_apply = Column(Boolean)
    results_wanted = Column(Integer)
    results_returned = Column(Integer)        # actual count after scraping
    country_indeed = Column(String(50))
    hours_old = Column(Integer)
    enforce_annual_salary = Column(Boolean, default=False)
    description_format = Column(String(20))


class Job(Base):
    """One row per unique job posting. Primary key is the site-prefixed job id."""
    __tablename__ = "jobs"

    # --- Identity ---
    id = Column(String(255), primary_key=True)
    site = Column(String(50), nullable=False, index=True)

    # --- URLs ---
    job_url = Column(Text)
    job_url_direct = Column(Text)

    # --- Core details ---
    title = Column(String(512), index=True)
    company = Column(String(255), index=True)
    location = Column(String(255), index=True)
    date_posted = Column(Date, index=True)
    job_type = Column(String(100))            # comma-separated e.g. "fulltime"
    listing_type = Column(String(100))

    # --- Salary ---
    salary_source = Column(String(50))        # "direct_data" | "description"
    interval = Column(String(20))             # yearly | monthly | weekly | daily | hourly
    min_amount = Column(Float)
    max_amount = Column(Float)
    currency = Column(String(10))

    # --- Flags ---
    is_remote = Column(Boolean, index=True)

    # --- Seniority / function ---
    job_level = Column(String(100))
    job_function = Column(String(100))

    # --- Contact ---
    emails = Column(Text)                     # comma-separated

    # --- Description ---
    description = Column(Text)

    # --- Company enrichment ---
    company_industry = Column(String(255))
    company_url = Column(Text)
    company_logo = Column(Text)
    company_url_direct = Column(Text)
    company_addresses = Column(Text)
    company_num_employees = Column(String(100))
    company_revenue = Column(String(100))
    company_description = Column(Text)

    # --- Naukri-specific ---
    skills = Column(Text)                     # comma-separated
    experience_range = Column(String(100))
    company_rating = Column(Float)
    company_reviews_count = Column(Integer)
    vacancy_count = Column(Integer)
    work_from_home_type = Column(String(50))

    # --- Audit timestamps ---
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_tables() -> None:
    """Create all tables if they do not exist. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)


def save_jobs(df: pd.DataFrame, session_id: Optional[int] = None) -> int:
    """
    Upsert a DataFrame returned by scrape_jobs() into the database.

    Behaviour:
    - Rows without an 'id' value are skipped.
    - Existing rows (same primary key) are updated except for first_seen_at.
    - New rows are inserted.

    Returns the number of rows successfully upserted.
    """
    if df.empty:
        return 0

    # Replace NaN/NaT with None for SQL compatibility
    records = df.where(pd.notna(df), None).to_dict(orient="records")

    _JOB_COLUMNS = {c.key for c in Job.__table__.columns}

    upserted = 0
    now = datetime.utcnow()

    with SessionLocal() as db:
        for record in records:
            job_id = record.get("id")
            if not job_id:
                continue

            # Build a dict of only columns that exist in the Job table
            job_data: dict = {
                k: v for k, v in record.items() if k in _JOB_COLUMNS
            }
            job_data["last_seen_at"] = now

            existing = db.get(Job, job_id)
            if existing is None:
                job_data["first_seen_at"] = now
                db.add(Job(**job_data))
            else:
                job_data.pop("first_seen_at", None)
                for key, val in job_data.items():
                    setattr(existing, key, val)

            upserted += 1

        db.commit()

    return upserted


def create_session_record(
    site_names: list[str],
    search_term: Optional[str],
    google_search_term: Optional[str],
    location: Optional[str],
    distance: Optional[int],
    is_remote: bool,
    job_type: Optional[str],
    easy_apply: Optional[bool],
    results_wanted: int,
    results_returned: int,
    country_indeed: str,
    hours_old: Optional[int],
    enforce_annual_salary: bool,
    description_format: str,
) -> int:
    """Insert a ScrapeSession record and return its auto-generated id."""
    with SessionLocal() as db:
        session = ScrapeSession(
            site_names=",".join(site_names) if isinstance(site_names, list) else site_names,
            search_term=search_term,
            google_search_term=google_search_term,
            location=location,
            distance=distance,
            is_remote=is_remote,
            job_type=job_type,
            easy_apply=easy_apply,
            results_wanted=results_wanted,
            results_returned=results_returned,
            country_indeed=country_indeed,
            hours_old=hours_old,
            enforce_annual_salary=enforce_annual_salary,
            description_format=description_format,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id


def query_jobs(
    site: Optional[str] = None,
    title: Optional[str] = None,
    company: Optional[str] = None,
    location: Optional[str] = None,
    is_remote: Optional[bool] = None,
    min_salary: Optional[float] = None,
    date_from: Optional[str] = None,      # "YYYY-MM-DD"
    limit: int = 100,
    offset: int = 0,
) -> pd.DataFrame:
    """
    Query the jobs table with optional filters.

    All string filters use SQL ILIKE (case-insensitive substring match).
    Returns an empty DataFrame when no rows match.
    """
    with SessionLocal() as db:
        q = db.query(Job)

        if site:
            q = q.filter(Job.site == site.lower())
        if title:
            q = q.filter(Job.title.ilike(f"%{title}%"))
        if company:
            q = q.filter(Job.company.ilike(f"%{company}%"))
        if location:
            q = q.filter(Job.location.ilike(f"%{location}%"))
        if is_remote is not None:
            q = q.filter(Job.is_remote == is_remote)
        if min_salary is not None:
            q = q.filter(Job.min_amount >= min_salary)
        if date_from:
            q = q.filter(Job.date_posted >= date_from)

        q = q.order_by(Job.date_posted.desc().nulls_last(), Job.first_seen_at.desc())
        q = q.offset(offset).limit(limit)

        rows = q.all()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [{k: v for k, v in row.__dict__.items() if not k.startswith("_")} for row in rows]
    )


def get_job_by_id(job_id: str) -> Optional[dict]:
    """Return a single job record as a dict, or None if not found."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return None
        return {k: v for k, v in job.__dict__.items() if not k.startswith("_")}


def delete_job(job_id: str) -> bool:
    """Delete a job by ID. Returns True if deleted, False if not found."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return False
        db.delete(job)
        db.commit()
        return True


def get_sessions(limit: int = 50, offset: int = 0) -> list[dict]:
    """Return scrape session records newest-first."""
    with SessionLocal() as db:
        rows = (
            db.query(ScrapeSession)
            .order_by(ScrapeSession.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
            for row in rows
        ]
