"""
Prune confirmed generic English words from data/skills_taxonomy.csv.
Only drops entries whose lowercased form is in the explicit STOPWORDS set.
No pattern-based filtering — legitimate skill names are never touched.
"""
import csv, sys
from pathlib import Path

STOPWORDS = {
    # Confirmed noise from CC's diagnostic sample job
    "analysis", "algorithms", "architectures", "communication", "documentation",
    "engineering", "hardware", "health", "mentoring", "plan", "protocols",
    "reporting", "scripting", "system", "technical", "testing", "training",
    # High-probability additions (generic English, not tech-specific)
    "development", "management", "leadership", "collaboration", "implementation",
    "design", "monitoring", "operations", "troubleshooting", "maintenance",
    "optimization", "integration", "deployment", "configuration", "administration",
    "automation", "support", "research", "planning", "coordination", "evaluation",
    "programming", "coding", "debugging", "reviewing", "writing",
    "consulting", "teaching", "presenting", "networking", "hiring", "interviewing",
    "mathematics", "statistics", "modeling", "forecasting", "auditing",
    "content", "product", "service", "software", "web",
    "application", "applications", "platform", "platforms", "infrastructure",
    "environment", "framework", "frameworks", "library", "libraries",
    "process", "processes", "workflow", "workflows", "procedure", "procedures",
    "strategy", "strategies", "knowledge", "skills", "experience", "expertise",
    "ability", "abilities", "understanding", "familiarity", "proficiency",
}

TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "skills_taxonomy.csv"

rows = []
with open(TAXONOMY_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

starting_count = len(rows)
kept = []
dropped = []

for row in rows:
    skill = row.get("skill", "").strip()
    if skill.lower() in STOPWORDS:
        dropped.append(skill)
    else:
        kept.append(row)

with open(TAXONOMY_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(kept)

print(f"Starting count: {starting_count}")
print(f"Dropped ({len(dropped)}): {sorted(dropped)}")
print(f"Final count:    {len(kept)}")
