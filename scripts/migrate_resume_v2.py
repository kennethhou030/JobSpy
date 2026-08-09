"""
migrate_resume_v2.py
Adds new columns to resume_profiles table without dropping any data.
Safe to run multiple times — skips columns that already exist.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path("jobspy.db")
if not DB_PATH.exists():
    for candidate in [Path("jobs.db"), Path("../jobspy.db"), Path("../jobs.db"), Path("data/jobs.db")]:
        if candidate.exists():
            DB_PATH = candidate
            break

if not DB_PATH.exists():
    print("ERROR: jobs.db not found. Check the path.")
    sys.exit(1)

NEW_COLUMNS = [
    ("work_experience",  "TEXT"),
    ("projects",         "TEXT"),
    ("volunteer",        "TEXT"),
    ("certifications",   "TEXT"),
    ("languages",        "TEXT"),
    ("linkedin_url",     "TEXT"),
    ("github_url",       "TEXT"),
    ("raw_sections",     "TEXT"),
]

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(resume_profiles)")
existing = {row[1] for row in cursor.fetchall()}

if not existing:
    print("WARNING: resume_profiles table not found — it will be created when the app starts.")
    conn.close()
    sys.exit(0)

added = []
skipped = []
for col_name, col_type in NEW_COLUMNS:
    if col_name in existing:
        skipped.append(col_name)
    else:
        cursor.execute(f"ALTER TABLE resume_profiles ADD COLUMN {col_name} {col_type}")
        added.append(col_name)

conn.commit()
conn.close()

print(f"Migration complete.")
print(f"  Added:   {added if added else 'none (all already exist)'}")
print(f"  Skipped: {skipped}")
print(f"  DB:      {DB_PATH.resolve()}")
print("\nNo data was lost. Existing resume profiles will have NULL for new columns until re-uploaded.")
