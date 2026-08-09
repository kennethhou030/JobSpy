"""One-off script: merge existing skills_taxonomy.csv with pyresparser skills.csv."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
TAXONOMY = ROOT / "data" / "skills_taxonomy.csv"
PYRESPARSER = Path("/tmp/pyresparser_skills.csv")

# ---------------------------------------------------------------------------
# Alias table mirrored from match_scorer.py
# Only semantic filter: skip alias keys that are not the canonical value.
# e.g. skip "nodejs" (aliases to "node.js") — keep "node.js" instead.
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    "node":                  "node.js",
    "nodejs":                "node.js",
    "node js":               "node.js",
    "node.js":               "node.js",
    "ts":                    "typescript",
    "typescript":            "typescript",
    "py":                    "python",
    "python3":               "python",
    "python 3":              "python",
    "java se":               "java",
    "java ee":               "java",
    "c++":                   "c++",
    "cpp":                   "c++",
    "c#":                    "c#",
    "csharp":                "c#",
    "c sharp":               "c#",
    "amazon web services":   "aws",
    "aws":                   "aws",
    "google cloud":          "gcp",
    "google cloud platform": "gcp",
    "gcp":                   "gcp",
    "azure":                 "azure",
    "microsoft azure":       "azure",
    "postgresql":            "postgres",
    "postgres":              "postgres",
    "mysql":                 "mysql",
    "mssql":                 "sql server",
    "microsoft sql server":  "sql server",
    "sql server":            "sql server",
    "mongo":                 "mongodb",
    "mongodb":               "mongodb",
    "scikit learn":          "scikit-learn",
    "scikit-learn":          "scikit-learn",
    "sklearn":               "scikit-learn",
    "tensorflow":            "tensorflow",
    "tf":                    "tensorflow",
    "pytorch":               "pytorch",
    "torch":                 "pytorch",
    "pandas":                "pandas",
    "numpy":                 "numpy",
    "kubernetes":            "kubernetes",
    "k8s":                   "kubernetes",
    "docker":                "docker",
    "terraform":             "terraform",
    "ci/cd":                 "ci/cd",
    "cicd":                  "ci/cd",
    "github actions":        "github actions",
    "gitlab ci":             "gitlab ci",
    "reactjs":               "react",
    "react.js":              "react",
    "react":                 "react",
    "vuejs":                 "vue",
    "vue.js":                "vue",
    "vue":                   "vue",
    "angular":               "angular",
    "angularjs":             "angular",
    "rest api":              "rest",
    "restful":               "rest",
    "rest":                  "rest",
    "graphql":               "graphql",
    "pytest":                "pytest",
    "jest":                  "jest",
    "junit":                 "junit",
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

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\n\r\t]")


def is_malformed(skill: str) -> bool:
    """Drop only entries that would corrupt the CSV format."""
    if not skill:
        return True
    if _CONTROL_CHAR_RE.search(skill):
        return True
    return False


def should_skip_alias(skill: str) -> bool:
    """Skip if this skill is an alias key but not the canonical target."""
    lower = skill.strip().lower()
    return lower in _ALIASES and _ALIASES[lower] != lower


# ---------------------------------------------------------------------------
# Load existing taxonomy
# ---------------------------------------------------------------------------
existing_lines = TAXONOMY.read_text().strip().splitlines()
header = existing_lines[0]
existing_skills = [l.strip() for l in existing_lines[1:] if l.strip()]
print(f"Existing taxonomy: {len(existing_skills)} entries")

existing_lower_map: dict[str, str] = {}
for s in existing_skills:
    lower = s.lower()
    if lower not in existing_lower_map:
        existing_lower_map[lower] = s

# ---------------------------------------------------------------------------
# Load original git-recovered taxonomy (one skill per line, has header)
# ---------------------------------------------------------------------------
ORIGINAL = Path("/tmp/original_taxonomy.csv")
original_added = 0
if ORIGINAL.exists():
    orig_lines = ORIGINAL.read_text().strip().splitlines()
    orig_skills = [l.strip() for l in orig_lines[1:] if l.strip()]
    print(f"Original (git) taxonomy: {len(orig_skills)} entries")
    for s in orig_skills:
        lower = s.lower()
        if is_malformed(s) or should_skip_alias(s):
            continue
        if lower not in existing_lower_map:
            existing_lower_map[lower] = s
            original_added += 1
    print(f"Original entries restored (net new vs current): {original_added}")

# ---------------------------------------------------------------------------
# Load pyresparser skills (single comma-separated line, no header)
# ---------------------------------------------------------------------------
pyresparser_raw = PYRESPARSER.read_text().strip()
pyresparser_parts = [p.strip() for p in pyresparser_raw.split(",")]
pyresparser_parts = [p for p in pyresparser_parts if p and p.lower() != "technical skills"]
print(f"pyresparser raw entries (after removing category header): {len(pyresparser_parts)}")

# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
merged_lower: dict[str, str] = dict(existing_lower_map)
added = skipped_alias = skipped_malformed = 0

for raw in pyresparser_parts:
    skill = raw.strip()
    lower = skill.lower()

    if is_malformed(skill):
        skipped_malformed += 1
        continue
    if should_skip_alias(skill):
        skipped_alias += 1
        continue
    if lower in merged_lower:
        continue

    merged_lower[lower] = skill
    added += 1

# ---------------------------------------------------------------------------
# Sort and write
# ---------------------------------------------------------------------------
final_skills = sorted(merged_lower.values(), key=lambda s: s.lower())

TAXONOMY.write_text(header + "\n" + "\n".join(final_skills) + "\n")

print(f"pyresparser skipped (malformed):       {skipped_malformed}")
print(f"pyresparser skipped (alias non-canon): {skipped_alias}")
print(f"pyresparser added (net new):           {added}")
print(f"Final merged unique count:             {len(final_skills)}")
print(f"\nWrote {TAXONOMY}")
