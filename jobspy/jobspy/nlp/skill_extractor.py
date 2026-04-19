"""
skill_extractor.py
Extracts required and preferred skills from job description text using
spaCy PhraseMatcher against a curated skills taxonomy CSV.
"""

from __future__ import annotations
import csv
import re
from pathlib import Path
from functools import lru_cache

import spacy
from spacy.matcher import PhraseMatcher

# Path to the skills taxonomy (populated in Phase 0)
TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "skills_taxonomy.csv"

# Context windows: keywords that indicate a skill is "required" vs "preferred"
REQUIRED_SIGNALS = [
    "required", "must have", "must-have", "you must", "you will need",
    "mandatory", "essential", "minimum requirement", "you need", "requires",
    "expected to have", "need to have",
]
PREFERRED_SIGNALS = [
    "preferred", "nice to have", "nice-to-have", "bonus", "plus", "ideally",
    "desired", "advantageous", "would be great", "good to have", "optional",
    "a plus", "welcomed",
]


@lru_cache(maxsize=1)
def _load_nlp_and_matcher() -> tuple:
    """
    Load spaCy model and build PhraseMatcher from the skills taxonomy.
    Cached so we only do this once per process.
    """
    nlp = spacy.load("en_core_web_md")

    skills = _load_skills_taxonomy()
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    patterns = [nlp.make_doc(skill.lower()) for skill in skills]
    matcher.add("SKILL", patterns)

    return nlp, matcher, skills


def _load_skills_taxonomy() -> list[str]:
    """Load skills list from the CSV taxonomy file."""
    if not TAXONOMY_PATH.exists():
        raise FileNotFoundError(
            f"Skills taxonomy not found at {TAXONOMY_PATH}. "
            "Please run Phase 0 setup first."
        )
    skills = []
    with open(TAXONOMY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skill = row.get("skill", "").strip()
            if skill:
                skills.append(skill)
    return skills


def _get_section_signal(text: str, skill_start: int, window: int = 600) -> str:
    """
    Look backwards up to `window` chars from the skill mention for the most
    recent required/preferred section signal.

    Returns 'required', 'preferred', or 'unknown'.
    'unknown' means no signal was found — callers treat it as 'preferred' so that
    context-free matches don't inflate the required bucket.
    """
    context_before = text[max(0, skill_start - window): skill_start].lower()

    last_required_pos = max(
        (context_before.rfind(sig) for sig in REQUIRED_SIGNALS), default=-1
    )
    last_preferred_pos = max(
        (context_before.rfind(sig) for sig in PREFERRED_SIGNALS), default=-1
    )

    if last_required_pos == -1 and last_preferred_pos == -1:
        return "unknown"   # no signal found — do not assume required vs preferred

    if last_required_pos >= last_preferred_pos:
        return "required"
    return "preferred"


def extract_skills(description: str) -> dict[str, list[str]]:
    """
    Extract required and preferred skills from a job description string.

    Args:
        description: Raw job description text (markdown or plain text)

    Returns:
        {
            "required": ["Python", "SQL", ...],
            "preferred": ["Kubernetes", "Terraform", ...]
        }
    """
    if not description or not description.strip():
        return {"required": [], "preferred": []}

    # Strip markdown formatting for cleaner NLP
    clean_text = re.sub(r"[#*`>\[\]()_~]", " ", description)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    nlp, matcher, _ = _load_nlp_and_matcher()
    doc = nlp(clean_text)
    matches = matcher(doc)

    required: list[str] = []
    preferred: list[str] = []
    seen: set[str] = set()

    for match_id, start, end in matches:
        span = doc[start:end]
        skill_text = span.text  # original casing
        skill_lower = skill_text.lower()

        if skill_lower in seen:
            continue
        seen.add(skill_lower)

        char_start = span.start_char
        signal = _get_section_signal(clean_text, char_start)

        if signal == "required":
            required.append(skill_text)
        else:   # "preferred" or "unknown" — default to preferred
            # Unknown means no signal word found nearby; treat as preferred rather
            # than required so context-free matches don't inflate the required bucket.
            preferred.append(skill_text)

    return {
        "required": sorted(set(required)),
        "preferred": sorted(set(preferred)),
    }


def extract_skills_bulk(jobs: list[dict]) -> list[dict]:
    """
    Run skill extraction on a list of job dicts.
    Each dict must have a 'description' key.
    Returns the same list with 'required_skills' and 'preferred_skills' added.
    """
    for job in jobs:
        description = job.get("description") or ""
        skills = extract_skills(description)
        job["required_skills"] = skills["required"]
        job["preferred_skills"] = skills["preferred"]
    return jobs
