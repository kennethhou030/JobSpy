# JobSpy Demo Prep — Status & Priorities (REVISED)

**Time to demo:** 2 days. **Team available:** 1 (solo). **Rubric total:** 6 points.
**Revised after reading the full codebase.**

## Corrected assessment of the project

This project is ~85% built, not ~50% as your status update implied. What you actually have:

- All 8 platform scrapers exist in code (debugging, not building)
- `jobspy/platform_selector.py` with 60+ location mappings (DONE)
- `jobspy/nlp/skill_extractor.py` — spaCy PhraseMatcher with required/preferred context detection (DONE, algorithm is correct)
- `jobspy/nlp/resume_parser.py` — 3-layer detection, 200+ heading synonyms, date-anchor segmentation (DONE, sophisticated)
- `jobspy/nlp/match_scorer.py` — weighted skill-overlap with alias normalization (DONE, algorithm is correct — NOT broken TF-IDF)
- `jobspy/nlp/cover_letter.py` — Claude API with carefully tuned system prompt (DONE)
- `evaluation/match_eval.py` + `evaluation/cover_letter_eval.py` — BOTH eval scripts are already written (DONE)
- `tasks/test_resume_parser_v2.py` — test suite with 25+ assertions (DONE)
- 5 frontend pages, FastAPI with 15+ endpoints, SQLAlchemy with 4 tables (DONE)
- Railway deployment (DONE)

## What actually needs fixing (revised)

| Issue | Root cause | Fix time |
|---|---|---|
| ~~6/8 scrapers failing~~ **RESOLVED (partial):** LinkedIn + Indeed reliable; Glassdoor/Google/ZipRecruiter hard-blocked by anti-bot (TLS fingerprinting, stale CSRF token, DOM drift) — not code bugs | Error isolation added to `jobspy/__init__.py`; `smoke_test_scrapers.py` created | DONE — ship with 2 |
| Match scores too low | **Skill taxonomy is only ~170 skills**, not 1000+; thin extraction → low scores | 1–2 hours |
| Resume parser fragile | 2-column PDFs, stylized layouts | 1–2 hours |
| `labeled_jobs.csv` is empty | Eval can't run without labels | 45 min |
| No video recorded | Biggest single rubric risk (2 pts) | 3 hours |

## Triage decisions

### Ship
- Everything above, tightened via targeted debugging

### Reframe as "future work" in demo (honestly)
- International board *scraping* (code exists, reliability varies) — present as implemented but demo with US boards
- 5-reviewer human eval (scale down to self + 1–2 friends, 5 letters)
- Ghost-posting detection and longitudinal analysis (code supports it, not demonstrated at scale)

### Do not claim
- "1000+ skill taxonomy" — README overclaims. Either expand the file to match, or change the claim to "curated skill taxonomy (~200 entries)"

## Time budget (48 hours)

| Block | Hours | Focus |
|---|---|---|
| ~~Day 1 AM (2h)~~ **DONE** | LinkedIn + Indeed reliable; 3 others hard-blocked; error isolation + smoke test added. Ship with 2. | `01_fix_scrapers.md` ✓ |
| Day 1 midday (2h) | Expand skills taxonomy + verify scores improve | `03_fix_match_score.md` |
| Day 1 PM (2h) | Debug resume parser against 3–5 real resumes | `02_fix_resume_parser.md` |
| Day 1 evening (2h) | Label 25–30 jobs, run `match_eval.py` + `cover_letter_eval.py` | `04_minimal_eval.md` |
| Day 2 AM (3h) | Record video (nonnegotiable) | `05_video_script.md` |
| Day 2 midday (2h) | Architecture diagram + one-pager | `07_rubric_coverage_plan.md` |
| Day 2 PM (2h) | Demo rehearsal + station activities + backup plan | `06_live_demo_script.md` |
| Day 2 evening (1h) | Final Railway smoke test, charge laptop, sleep | — |

**Hard cut-off:** Day 2 morning = video. If Day 1 work slips, you ship with fewer fixes, not a missing video.

## Rubric leverage (revised confidence)

1. **Video (2 pts)** — not started. Largest exposure.
2. **Testing & QA (1 pt)** — eval scripts exist. Labeling 25 jobs + running them = ~1 hour to fully earn this.
3. **Technical Achievement (1 pt)** — the codebase is genuinely impressive. You can legitimately claim: 200+ section synonyms, context-aware skill classification, weighted scoring with alias normalization. **Higher confidence than I originally said.**
4. **Project Impact (1 pt)** — proposal narrative is strong, Railway deployment closes the real-world applicability gap.
5. **UX (0.5 pt)** — 5 pages exist. Spend ~30 min on visual polish only.
6. **Docs (0.5 pt)** — architecture diagram + one-pager + existing README.

## What NOT to do

- Don't rebuild anything that exists. Every file I listed above is already in your repo.
- Don't spend hours chasing 8/8 scraper coverage. 4–5 reliable US platforms is a demo win; 8 flaky platforms is a demo loss.
- Don't promise the 5-reviewer Likert eval on stage. Pilot framing is honest and still scores the rubric.
- Don't claim "1000+ skills" unless you've expanded the taxonomy file.
