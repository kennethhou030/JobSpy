# 01 — Debug Scrapers (for Claude Code)

**Owner:** Claude Code, running in `/Users/kennethhou/Desktop/JobSpy/JobSpy/`.
**Goal:** Get **4–5 US boards** working reliably. All 8 scrapers already exist in code.
**Time box:** 2–3 hours. At 3.5h, stop and ship what works.

## Context for CC

The `scrape_jobs()` function in `jobspy/__init__.py` orchestrates 8 platform scrapers via `ThreadPoolExecutor`. All 8 scrapers are implemented at `jobspy/{linkedin,indeed,glassdoor,google,ziprecruiter,bayt,naukri,bdjobs}/__init__.py`. Skill extraction already runs inside the scrape flow (line ~192 of `jobspy/__init__.py`: `extract_skills(job_data["description"])` is called per job). User reports only LinkedIn + Indeed actually return results.

**Hypothesis:** most failures are environmental, not code bugs — rate limits, site DOM drift, missing parameters, or transient network issues. Verify before patching.

## Tasks

### Step 1 — Build a smoke test script (30 min)

Create `scripts/smoke_test_scrapers.py` that runs each platform in isolation and prints clear per-platform status. The script should NOT use the ThreadPoolExecutor — run sequentially so errors are readable.

```python
"""Smoke test each scraper in isolation with a known-good query."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import traceback
from jobspy import scrape_jobs

PLATFORMS = ["linkedin", "indeed", "glassdoor", "google", "ziprecruiter"]
# Skipping international boards (bayt, naukri, bdjobs) for the US demo path

QUERY = {
    "search_term": "software engineer",
    "google_search_term": "software engineer jobs near New York, NY",
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
```

Run it, collect a table of results per platform.

### Step 2 — Triage per-platform failures (90 min)

Based on the smoke test output, apply the right fix for each:

**LinkedIn**
- If it returns 0 results: try `linkedin_fetch_description=True` once to slow requests
- If it throws 429: add delay between pages in `jobspy/linkedin/__init__.py`, or back off `results_wanted` to 10
- If it throws 403: TLS session is being fingerprinted. Check `create_session()` in `jobspy/util.py` is using `tls-client`

**Indeed**
- Usually reliable via their GraphQL API. If failing, check for country_indeed param propagation
- Common error: "Could not get country code" — fix by explicitly passing `country_indeed="usa"`

**Glassdoor**
- Needs `country_indeed` to map to the right subdomain (check `jobspy/model.py` `Country` enum)
- Test with `country_indeed="usa"` explicitly
- If still failing: many Glassdoor queries need a GraphQL session token — check `jobspy/glassdoor/__init__.py` for token refresh logic

**Google Jobs**
- REQUIRES `google_search_term` parameter (distinct from `search_term`). Confirm the smoke test passes it.
- Format: `"<role> jobs near <location>"` — this is how Google parses it
- If still failing: Google Jobs sometimes gates via CAPTCHA; documented limitation

**ZipRecruiter**
- US/Canada only. Don't test with non-NA locations.
- Rate-limits aggressively. If failing: reduce `results_wanted` to 10, space calls out
- Session may need a fresh cookie — check `jobspy/ziprecruiter/__init__.py`

### Step 3 — Harden error isolation (30 min)

Open `jobspy/__init__.py`. The `ThreadPoolExecutor` block currently calls `future.result()` inside the `for future in as_completed()` loop — an exception on one site crashes the whole scrape. Wrap in try/except:

```python
for future in as_completed(future_to_site):
    site = future_to_site[future]
    try:
        site_value, scraped_data = future.result()
        site_to_jobs_dict[site_value] = scraped_data
    except Exception as exc:
        create_logger(site.value).error(f"scrape failed: {exc}")
        site_to_jobs_dict[site.value] = JobResponse(jobs=[])
```

This way, a Google Jobs failure does not kill LinkedIn+Indeed results.

### Step 4 — Add a per-platform status field to API response (optional, 30 min)

In `api/main.py` `/api/scrape`, track which platforms returned >0 jobs and include it in the response so the frontend can show "Glassdoor temporarily unavailable" instead of silent failure.

## Definition of done

- [ ] `scripts/smoke_test_scrapers.py` exists and runs cleanly
- [ ] Smoke test shows **at least 4 US platforms** returning jobs (target: linkedin, indeed, glassdoor, ziprecruiter, google)
- [ ] Per-site exception isolation added to `jobspy/__init__.py`
- [ ] (Optional) per-platform status in API response

## Fallback if stuck after 3.5 hours

Accept what works. In the demo, frame it honestly:
> "Our codebase implements all 8 platform scrapers. In practice we prioritized reliability — 4 US boards return results consistently; Bayt, Naukri, and BDJobs are implemented for international markets and will be reliability-hardened as future work. This is how it already is in production at platforms like LinkedIn itself — not every source is live every day."

That framing is defensible AND honest.
