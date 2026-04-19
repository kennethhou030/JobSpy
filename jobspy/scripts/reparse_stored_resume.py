"""Re-parse the stored resume against the current taxonomy and overwrite the DB profile."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import get_resume_profile, save_resume_profile
from jobspy.nlp.resume_parser import parse_resume

profile = get_resume_profile("default")
if profile is None:
    print("ERROR: No resume profile found for user 'default'. Upload a resume first.")
    sys.exit(1)

old_skills = profile.parsed_skills or []
print(f"Old skill count: {len(old_skills)}")
print(f"Old skills: {old_skills}")

file_path = profile.file_path
if not file_path:
    print("ERROR: Profile has no file_path stored — cannot re-parse.")
    sys.exit(1)

# Resolve relative paths from the project root
p = Path(file_path)
if not p.is_absolute():
    p = Path(__file__).parent.parent / p

if not p.exists():
    print(f"ERROR: Resume file not found at {p}")
    sys.exit(1)

print(f"\nRe-parsing: {p}")
parsed = parse_resume(str(p))

new_skills = parsed.get("parsed_skills") or []
print(f"\nNew skill count: {len(new_skills)}")
print(f"New skills: {new_skills}")

added = sorted(set(new_skills) - set(old_skills))
dropped = sorted(set(old_skills) - set(new_skills))
print(f"\nAdded ({len(added)}):   {added}")
print(f"Dropped ({len(dropped)}): {dropped}")

if len(new_skills) < len(old_skills) * 0.7:
    print("\nWARNING: New skill count is dramatically lower than old. Aborting save.")
    sys.exit(1)

parsed["file_path"] = profile.file_path
parsed["original_filename"] = profile.original_filename
save_resume_profile(parsed, user_id="default")
print(f"\nProfile saved. {len(old_skills)} → {len(new_skills)} skills.")
