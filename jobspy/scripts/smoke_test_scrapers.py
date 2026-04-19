"""Smoke test each scraper in isolation with a known-good query."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import traceback
from jobspy import scrape_jobs

PLATFORMS = ["linkedin", "indeed", "glassdoor", "google", "zip_recruiter"]
# Skipping international boards (bayt, naukri, bdjobs) for the US demo path

QUERY = {
    "search_term": "software engineer",
    "google_search_term": "software engineer jobs near New York, NY since yesterday",
    "location": "New York, NY",
    "results_wanted": 5,
    "country_indeed": "usa",
}

print(f"{'Platform':<15} {'Status':<10} {'Count':<8} Detail")
print("-" * 80)
for platform in PLATFORMS:
    try:
        df = scrape_jobs(site_name=[platform], verbose=0, **QUERY)
        if df.empty:
            print(f"{platform:<15} {'EMPTY':<10} {0:<8} No jobs returned")
        else:
            print(f"{platform:<15} {'OK':<10} {len(df):<8} Sample: {df.iloc[0]['title'][:50]}")
    except Exception as e:
        err = str(e)[:100].replace("\n", " ")
        print(f"{platform:<15} {'FAIL':<10} {'-':<8} {type(e).__name__}: {err}")
        # Uncomment for full stack trace during debugging:
        # traceback.print_exc()
