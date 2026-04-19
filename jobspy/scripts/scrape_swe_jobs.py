"""
Fresh scrape: software engineer jobs for demo dataset.
Tries US-wide first; falls back to NY + SF if either site returns nothing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from jobspy import scrape_jobs
from jobspy.database import save_jobs, engine
from sqlalchemy import text

COMMON_PARAMS = dict(
    site_name=["linkedin", "indeed"],
    search_term="software engineer",
    results_wanted=25,
    country_indeed="usa",
    hours_old=168,
    is_remote=False,
    description_format="markdown",
    verbose=1,
)

print("Attempting US-wide scrape...")
df = scrape_jobs(location="United States", **COMMON_PARAMS)
print(f"  US-wide returned: {len(df)} rows")

if len(df) < 10:
    print("Too few results — falling back to NY + SF scrapes...")
    df_ny = scrape_jobs(location="New York, NY", **COMMON_PARAMS)
    df_sf = scrape_jobs(location="San Francisco, CA", **COMMON_PARAMS)
    print(f"  NY: {len(df_ny)} rows, SF: {len(df_sf)} rows")
    df = pd.concat([df_ny, df_sf], ignore_index=True).drop_duplicates(subset=["id"])
    print(f"  Merged (deduped): {len(df)} rows")

if df.empty:
    print("ERROR: No jobs returned from any scrape.")
    sys.exit(1)

saved = save_jobs(df)
print(f"\nSaved {saved} new/updated jobs to DB.")

with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar()
print(f"Total jobs in DB: {total}")
