# Phase 1 — Location-Aware Platform Selector
> Prerequisite: Phase 0 must be complete.

## Context
JobSpy already scrapes 8 platforms. Right now the user manually picks which platforms to query. The proposal requires automatic location-aware selection — e.g., when a user searches for jobs in India, Naukri is automatically included; for the Middle East, Bayt is included. This is a small but important feature for the project's research validity.

---

## Your Job in This Phase
1. Create `jobspy/platform_selector.py`
2. Wire it into `api/main.py` so the scrape endpoint uses it
3. Test it works

---

## Step 1 — Read These Files First
- `api/main.py` — focus on the `POST /api/scrape` endpoint and `ScrapeRequest` schema
- `api/schemas.py` — look at the `ScrapeRequest` model (specifically `site_name` and `location` fields)
- `jobspy/model.py` — look at the `Site` enum to understand valid platform names

---

## Step 2 — Create `jobspy/platform_selector.py`

Create this file exactly:

```python
"""
platform_selector.py
Automatically selects appropriate job platforms based on the user's target location.
International platforms (Naukri, Bayt, BDJobs) are only included when the location
matches their relevant region, preventing irrelevant results.
"""

from __future__ import annotations

# Default platforms for any search (globally applicable)
DEFAULT_PLATFORMS = ["linkedin", "indeed", "glassdoor", "google"]

# Mapping from location keywords → additional platforms
REGION_PLATFORM_MAP: dict[str, list[str]] = {
    # India
    "india": ["naukri"],
    "bengaluru": ["naukri"],
    "bangalore": ["naukri"],
    "mumbai": ["naukri"],
    "delhi": ["naukri"],
    "hyderabad": ["naukri"],
    "pune": ["naukri"],
    "chennai": ["naukri"],
    # Middle East
    "middle east": ["bayt"],
    "uae": ["bayt"],
    "dubai": ["bayt"],
    "abu dhabi": ["bayt"],
    "saudi arabia": ["bayt"],
    "riyadh": ["bayt"],
    "qatar": ["bayt"],
    "doha": ["bayt"],
    "kuwait": ["bayt"],
    "bahrain": ["bayt"],
    "jordan": ["bayt"],
    "egypt": ["bayt"],
    "lebanon": ["bayt"],
    # Bangladesh
    "bangladesh": ["bdjobs"],
    "dhaka": ["bdjobs"],
    "chittagong": ["bdjobs"],
    # North America (add ZipRecruiter)
    "united states": ["ziprecruiter"],
    "usa": ["ziprecruiter"],
    "canada": ["ziprecruiter"],
}


def select_platforms(location: str, override: list[str] | None = None) -> list[str]:
    """
    Return the list of platform names to scrape for a given location.

    Args:
        location: The user's target job location string (e.g., "New York", "Mumbai, India")
        override: If provided and non-empty, return override directly (user manually chose platforms)

    Returns:
        List of platform name strings matching jobspy Site enum values
    """
    # If user manually specified platforms, respect that choice
    if override:
        return override

    location_lower = location.lower().strip()
    platforms = set(DEFAULT_PLATFORMS)

    for region_keyword, extra_platforms in REGION_PLATFORM_MAP.items():
        if region_keyword in location_lower:
            platforms.update(extra_platforms)

    return sorted(platforms)


def get_platform_info(location: str) -> dict:
    """
    Returns a dict explaining which platforms were selected and why.
    Useful for frontend display and debugging.
    """
    location_lower = location.lower().strip()
    selected = set(DEFAULT_PLATFORMS)
    reasons: dict[str, str] = {p: "default (global)" for p in DEFAULT_PLATFORMS}

    for region_keyword, extra_platforms in REGION_PLATFORM_MAP.items():
        if region_keyword in location_lower:
            for p in extra_platforms:
                selected.add(p)
                reasons[p] = f"location match: '{region_keyword}'"

    return {
        "platforms": sorted(selected),
        "reasons": reasons,
        "location_input": location,
    }
```

---

## Step 3 — Wire Into `api/main.py`

In `api/main.py`, find the `POST /api/scrape` endpoint. It will look something like:

```python
@app.post("/api/scrape")
async def scrape_jobs_endpoint(request: ScrapeRequest):
    ...
    results = scrape_jobs(
        site_name=request.site_name,  # ← this line
        ...
    )
```

Make these two changes:

**Add the import at the top of `api/main.py`:**
```python
from jobspy.platform_selector import select_platforms
```

**Modify the scrape endpoint to use `select_platforms()`:**

Replace the line that passes `site_name` to `scrape_jobs()` with:
```python
selected_sites = select_platforms(
    location=request.location or "",
    override=request.site_name if request.site_name else None,
)
```
Then pass `site_name=selected_sites` to `scrape_jobs()`.

Do not change any other logic in the endpoint.

---

## Step 4 — Add `GET /api/platforms` Endpoint

Add this new endpoint to `api/main.py` so the frontend can ask which platforms are selected for a given location:

```python
@app.get("/api/platforms")
async def get_platforms_for_location(location: str = ""):
    """Returns which platforms will be auto-selected for a given location."""
    from jobspy.platform_selector import get_platform_info
    return get_platform_info(location)
```

---

## Step 5 — Test It

Run the following Python snippet to verify the selector logic works:

```python
from jobspy.platform_selector import select_platforms, get_platform_info

# Test 1: Generic US location — should NOT include naukri/bayt/bdjobs
result = select_platforms("New York, NY")
assert "naukri" not in result, "naukri should not appear for New York"
assert "linkedin" in result
print("Test 1 passed:", result)

# Test 2: India location — should include naukri
result = select_platforms("Mumbai, India")
assert "naukri" in result, "naukri should appear for Mumbai"
print("Test 2 passed:", result)

# Test 3: Dubai — should include bayt
result = select_platforms("Dubai")
assert "bayt" in result
print("Test 3 passed:", result)

# Test 4: Manual override — should ignore location logic
result = select_platforms("Mumbai", override=["linkedin"])
assert result == ["linkedin"]
print("Test 4 passed:", result)

# Test 5: get_platform_info
info = get_platform_info("Dhaka, Bangladesh")
assert "bdjobs" in info["platforms"]
print("Test 5 passed:", info)

print("\nAll tests passed!")
```

Run it with:
```bash
python -c "exec(open('tasks/test_platform_selector.py').read())"
```
Or just paste it into a quick `python3` interactive session.

---

## Step 6 — Verify the API Still Works

Start the server and confirm the scrape endpoint doesn't error:
```bash
uvicorn api.main:app --port 8000 --reload
```

Hit `GET http://localhost:8000/api/platforms?location=Mumbai` and confirm you get back a JSON response with `naukri` in the platforms list.

---

## Completion Checklist
- [ ] `jobspy/platform_selector.py` created with `select_platforms()` and `get_platform_info()`
- [ ] `api/main.py` imports and calls `select_platforms()` in the scrape endpoint
- [ ] `GET /api/platforms` endpoint added
- [ ] All 5 test cases pass
- [ ] Server starts without errors

## What's Next
When done, tell Kenneth "Phase 1 complete" and he will give you `02_skill_extractor.md`.
