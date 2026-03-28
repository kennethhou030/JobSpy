"""
daily_scrape.py
Runs a daily job scrape and logs results.
Designed to be called by a cron job or scheduler.

Usage:
    python scripts/daily_scrape.py --terms "Software Engineer" "Data Scientist" --location "United States"

Cron example (runs every day at 8am):
    0 8 * * * cd /path/to/JobSpy && python scripts/daily_scrape.py >> logs/daily_scrape.log 2>&1
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy import scrape_jobs
from jobspy.platform_selector import select_platforms

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


DEFAULT_SEARCH_TERMS = [
    "Software Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
]

DEFAULT_LOCATION = "United States"


def run_daily_scrape(
    search_terms: list[str] = DEFAULT_SEARCH_TERMS,
    location: str = DEFAULT_LOCATION,
    results_per_term: int = 50,
):
    log.info(f"Daily scrape started — {datetime.now().isoformat()}")
    total_saved = 0

    for term in search_terms:
        log.info(f"Scraping: '{term}' in '{location}'")
        try:
            platforms = select_platforms(location)
            log.info(f"  Platforms: {platforms}")

            df = scrape_jobs(
                site_name=platforms,
                search_term=term,
                location=location,
                results_wanted=results_per_term,
                hours_old=26,      # slightly over 24h to avoid gaps
                description_format="markdown",
                verbose=0,
            )

            log.info(f"  Scraped {len(df)} jobs for '{term}'")
            total_saved += len(df)

        except Exception as e:
            log.error(f"  FAILED to scrape '{term}': {e}")

    log.info(f"Daily scrape complete. Total jobs saved/updated: {total_saved}")
    return total_saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily job scraper for longitudinal dataset collection")
    parser.add_argument("--terms", nargs="+", default=DEFAULT_SEARCH_TERMS,
                        help="Search terms to scrape (default: Software Engineer, Data Scientist, ML Engineer)")
    parser.add_argument("--location", default=DEFAULT_LOCATION,
                        help="Location to search in (default: United States)")
    parser.add_argument("--results", type=int, default=50,
                        help="Results per search term (default: 50)")
    args = parser.parse_args()
    run_daily_scrape(args.terms, args.location, args.results)
