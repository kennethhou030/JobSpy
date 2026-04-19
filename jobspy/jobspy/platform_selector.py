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
