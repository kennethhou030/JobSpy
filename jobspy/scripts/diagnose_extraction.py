"""
Diagnostic script for three skill-extraction hypotheses.
Read-only — no DB writes, no taxonomy changes.
"""
import sys, re, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import engine
from jobspy.nlp.skill_extractor import (
    REQUIRED_SIGNALS, PREFERRED_SIGNALS, _load_nlp_and_matcher
)
from sqlalchemy import text

# ── helpers ──────────────────────────────────────────────────────────────────

def load_taxonomy() -> list[str]:
    path = Path(__file__).parent.parent / "data" / "skills_taxonomy.csv"
    skills = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = row.get("skill", "").strip()
            if s:
                skills.append(s)
    return skills

def section_signal_source(clean_text: str, skill_start: int, window: int = 600) -> str:
    """Returns 'required_signal', 'preferred_signal', or 'unknown_default'."""
    context = clean_text[max(0, skill_start - window): skill_start].lower()
    last_req = max((context.rfind(sig) for sig in REQUIRED_SIGNALS), default=-1)
    last_pref = max((context.rfind(sig) for sig in PREFERRED_SIGNALS), default=-1)
    if last_req == -1 and last_pref == -1:
        return "unknown_default"
    if last_req >= last_pref:
        return "required_signal"
    return "preferred_signal"

def clean(description: str) -> str:
    t = re.sub(r"[#*`>\[\]()_~]", " ", description)
    return re.sub(r"\s+", " ", t).strip()

# ── fetch one CS-relevant job with a description ──────────────────────────────

with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT title, description, required_skills, preferred_skills "
        "FROM jobs WHERE description IS NOT NULL AND length(description) > 200 "
        "AND (title LIKE '%Engineer%' OR title LIKE '%Software%' OR title LIKE '%ML%' "
        "OR title LIKE '%Data%' OR title LIKE '%AI%' OR title LIKE '%Intern%') "
        "LIMIT 1"
    )).fetchone()

if row is None:
    sys.exit("No suitable job found in DB.")

title, desc, req_stored, pref_stored = row
import json
req_stored  = json.loads(req_stored)  if isinstance(req_stored,  str) else (req_stored  or [])
pref_stored = json.loads(pref_stored) if isinstance(pref_stored, str) else (pref_stored or [])

print(f"\n{'='*70}")
print(f"JOB: {title}")
print(f"Description length: {len(desc)} chars")
print(f"Stored required_skills ({len(req_stored)}): {req_stored}")
print(f"Stored preferred_skills ({len(pref_stored)}): {pref_stored}")

# ── HYPOTHESIS 1 — unknown→required default ──────────────────────────────────

print(f"\n{'='*70}")
print("HYPOTHESIS 1: unknown→required default inflation")
print("="*70)

nlp, matcher, _ = _load_nlp_and_matcher()
clean_desc = clean(desc)
doc = nlp(clean_desc)
matches = matcher(doc)

seen: set[str] = set()
h1_required_signal = []
h1_unknown_default  = []
h1_preferred_signal = []

for match_id, start, end in matches:
    span = doc[start:end]
    skill_lower = span.text.lower()
    if skill_lower in seen:
        continue
    seen.add(skill_lower)
    source = section_signal_source(clean_desc, span.start_char)
    if source == "required_signal":
        h1_required_signal.append(span.text)
    elif source == "unknown_default":
        h1_unknown_default.append(span.text)
    else:
        h1_preferred_signal.append(span.text)

total = len(h1_required_signal) + len(h1_unknown_default) + len(h1_preferred_signal)
print(f"Total matches: {total}")
print(f"  True required signal:  {len(h1_required_signal):3d}  ({100*len(h1_required_signal)/max(total,1):.0f}%)  {h1_required_signal[:15]}")
print(f"  Unknown→required default: {len(h1_unknown_default):3d}  ({100*len(h1_unknown_default)/max(total,1):.0f}%)  {h1_unknown_default[:15]}")
print(f"  Preferred signal:      {len(h1_preferred_signal):3d}  ({100*len(h1_preferred_signal)/max(total,1):.0f}%)  {h1_preferred_signal[:15]}")

# ── HYPOTHESIS 2 — generic single-word taxonomy entries ──────────────────────

print(f"\n{'='*70}")
print("HYPOTHESIS 2: generic single-word taxonomy entries")
print("="*70)

taxonomy = load_taxonomy()
print(f"Taxonomy size: {len(taxonomy)} entries")

generic_pattern = re.compile(r'^[A-Za-z][a-z]{3,}$')  # single word, only letters, >3 chars, no caps beyond first
generic_words = [s for s in taxonomy if generic_pattern.match(s)]
print(f"Generic single-word entries (no digits/punctuation/multi-caps, len>3): {len(generic_words)}")
print(f"  {sorted(generic_words)}")

# How many of the job's extracted skills (all buckets) came from generic words?
generic_lower = {g.lower() for g in generic_words}
all_extracted = h1_required_signal + h1_unknown_default + h1_preferred_signal
from_generic = [s for s in all_extracted if s.lower() in generic_lower]
print(f"\nOf {len(all_extracted)} extracted skills from this job, {len(from_generic)} are generic-word entries:")
print(f"  {from_generic}")

# ── HYPOTHESIS 3 — substring overlap ─────────────────────────────────────────

print(f"\n{'='*70}")
print("HYPOTHESIS 3: taxonomy substring overlaps (shorter is substring of longer)")
print("="*70)

tax_lower = [(s, s.lower()) for s in taxonomy]
pairs = []
for i, (s1, l1) in enumerate(tax_lower):
    for j, (s2, l2) in enumerate(tax_lower):
        if i == j:
            continue
        if l1 in l2 and l1 != l2:          # s1 is substring of s2
            pairs.append((s1, s2))

# Deduplicate: keep canonical (shorter, longer) pairs by lower
seen_pairs: set[tuple[str,str]] = set()
unique_pairs = []
for s, l in pairs:
    key = (s.lower(), l.lower())
    if key not in seen_pairs:
        seen_pairs.add(key)
        unique_pairs.append((s, l))

print(f"Total substring-overlap pairs: {len(unique_pairs)}")
print("Top 20:")
for shorter, longer in sorted(unique_pairs, key=lambda p: p[0].lower())[:20]:
    print(f"  '{shorter}'  ⊂  '{longer}'")
