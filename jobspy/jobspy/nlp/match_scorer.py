"""
match_scorer.py
Computes match scores between a user's resume and job postings using
weighted skill overlap (required 70% + preferred 30%).

Match Score Formula:
    required_ratio  = matched_required  / total_required   (0 if none)
    preferred_ratio = matched_preferred / total_preferred  (0 if none)
    score = required_ratio * 0.7 + preferred_ratio * 0.3
    score is scaled to 0–100.

Skill Gap:
    missing_required = job.required_skills - resume.skills
    missing_preferred = job.preferred_skills - resume.skills
    matched = job.required_skills ∩ resume.skills
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Skill alias table — maps alternate spellings to a canonical form.
# Both sides are stored lowercase; comparison is always lowercase.
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    # JavaScript / Node
    "node":                  "node.js",
    "nodejs":                "node.js",
    "node js":               "node.js",
    "node.js":               "node.js",
    # TypeScript
    "ts":                    "typescript",
    "typescript":            "typescript",
    # Python
    "py":                    "python",
    "python3":               "python",
    "python 3":              "python",
    # Java
    "java se":               "java",
    "java ee":               "java",
    # C variants
    "c++":                   "c++",
    "cpp":                   "c++",
    "c#":                    "c#",
    "csharp":                "c#",
    "c sharp":               "c#",
    # Cloud
    "amazon web services":   "aws",
    "aws":                   "aws",
    "google cloud":          "gcp",
    "google cloud platform": "gcp",
    "gcp":                   "gcp",
    "azure":                 "azure",
    "microsoft azure":       "azure",
    # Databases
    "postgresql":            "postgres",
    "postgres":              "postgres",
    "mysql":                 "mysql",
    "mssql":                 "sql server",
    "microsoft sql server":  "sql server",
    "sql server":            "sql server",
    "mongo":                 "mongodb",
    "mongodb":               "mongodb",
    # ML / Data
    "scikit learn":          "scikit-learn",
    "scikit-learn":          "scikit-learn",
    "sklearn":               "scikit-learn",
    "tensorflow":            "tensorflow",
    "tf":                    "tensorflow",
    "pytorch":               "pytorch",
    "torch":                 "pytorch",
    "pandas":                "pandas",
    "numpy":                 "numpy",
    # DevOps / Infra
    "kubernetes":            "kubernetes",
    "k8s":                   "kubernetes",
    "docker":                "docker",
    "terraform":             "terraform",
    "tf":                    "terraform",   # ambiguous — terraform wins over tensorflow
    "ci/cd":                 "ci/cd",
    "cicd":                  "ci/cd",
    "github actions":        "github actions",
    "gitlab ci":             "gitlab ci",
    # React / Frontend
    "reactjs":               "react",
    "react.js":              "react",
    "react":                 "react",
    "vuejs":                 "vue",
    "vue.js":                "vue",
    "vue":                   "vue",
    "angular":               "angular",
    "angularjs":             "angular",
    # REST / APIs
    "rest api":              "rest",
    "restful":               "rest",
    "rest":                  "rest",
    "graphql":               "graphql",
    # Testing
    "pytest":                "pytest",
    "jest":                  "jest",
    "junit":                 "junit",
    # Misc
    "git":                   "git",
    "github":                "github",
    "gitlab":                "gitlab",
    "linux":                 "linux",
    "bash":                  "bash",
    "shell":                 "bash",
    "shell scripting":       "bash",
    "agile":                 "agile",
    "scrum":                 "scrum",
    "jira":                  "jira",
    "fastapi":               "fastapi",
    "flask":                 "flask",
    "django":                "django",
    "spring":                "spring",
    "spring boot":           "spring boot",
}


def _normalize_skill(skill: str) -> str:
    """Normalize a skill name to its canonical alias (lowercase)."""
    lower = skill.strip().lower()
    return _ALIASES.get(lower, lower)


def _skill_set(skills: list[str]) -> set[str]:
    """Return a set of normalized lowercase skill names."""
    return {_normalize_skill(s) for s in skills if s.strip()}


def compute_match_score(
    resume_skills: list[str],
    job_required_skills: list[str],
    job_preferred_skills: list[str],
    required_weight: float = 0.7,
    preferred_weight: float = 0.3,
) -> float:
    """
    Compute a match score (0.0 to 100.0) using weighted skill overlap.

    required_ratio  = matched_required  / total_required
    preferred_ratio = matched_preferred / total_preferred
    score = required_ratio * 0.7 + preferred_ratio * 0.3  (weights adjust if one side empty)
    """
    if not resume_skills:
        return 0.0
    if not job_required_skills and not job_preferred_skills:
        return 0.0

    resume_norm = _skill_set(resume_skills)
    req_norm    = _skill_set(job_required_skills)
    pref_norm   = _skill_set(job_preferred_skills)

    req_ratio  = len(resume_norm & req_norm)  / len(req_norm)  if req_norm  else None
    pref_ratio = len(resume_norm & pref_norm) / len(pref_norm) if pref_norm else None

    if req_ratio is None and pref_ratio is None:
        return 0.0
    if req_ratio is None:
        weighted = pref_ratio
    elif pref_ratio is None:
        weighted = req_ratio
    else:
        weighted = req_ratio * required_weight + pref_ratio * preferred_weight

    return round(weighted * 100, 1)


def compute_skill_gap(
    resume_skills: list[str],
    job_required_skills: list[str],
    job_preferred_skills: list[str],
) -> dict:
    """
    Compute which skills the candidate is missing vs. which they have.
    Alias-normalizes all comparisons so "NodeJS" matches "node.js".

    Returns:
        {
            "matched": [...],           # required skills the candidate HAS
            "missing_required": [...],  # required skills the candidate LACKS
            "missing_preferred": [...], # preferred skills the candidate LACKS
        }
    """
    resume_norm = _skill_set(resume_skills)

    matched: list[str] = []
    missing_required: list[str] = []
    missing_preferred: list[str] = []

    for skill in job_required_skills:
        if _normalize_skill(skill) in resume_norm:
            matched.append(skill)
        else:
            missing_required.append(skill)

    for skill in job_preferred_skills:
        if _normalize_skill(skill) not in resume_norm:
            missing_preferred.append(skill)

    return {
        "matched": sorted(matched),
        "missing_required": sorted(missing_required),
        "missing_preferred": sorted(missing_preferred),
    }


def score_job_against_resume(job: dict, resume_profile: dict) -> dict:
    """
    Convenience function: given a job dict and a resume profile dict,
    compute both match score and skill gap in one call.
    """
    resume_skills = resume_profile.get("parsed_skills") or []
    required      = job.get("required_skills") or []
    preferred     = job.get("preferred_skills") or []

    match_score = compute_match_score(resume_skills, required, preferred)
    skill_gap   = compute_skill_gap(resume_skills, required, preferred)

    return {
        "match_score": match_score,
        "skill_gap": skill_gap,
    }
