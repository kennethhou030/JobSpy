# 06 — Live Demo Script (Station Rotation)

**Format:** 5 min pitch + 5 min interactive, 6–7 rotations. Build for endurance.

## Pre-demo morning-of checklist

- [ ] Laptop fully charged; charger in bag
- [ ] Railway deployment tested end-to-end this morning
- [ ] Local `uvicorn api.main:app --reload --port 8000` tested as backup
- [ ] Default resume already uploaded on both Railway and localhost (so "search + match" demo doesn't require upload)
- [ ] A sample resume PDF on desktop for the "upload your own resume" interactive segment
- [ ] 3 pre-generated cover letters saved as local Markdown in case Claude API misbehaves
- [ ] Full-path screen recording (the video you made yesterday) playable offline
- [ ] One-pager handout printed, QR code to repo + Railway URL
- [ ] `tasks/test_resume_parser_v2.py` runnable locally (good "watch this pass 25 tests" moment)
- [ ] Notifications off, browser cleaned, font zoom 110%+

## The 5-minute pitch (memorize — don't read)

### Hook (15s)
> "Hands up — who's applied to more than 20 jobs this year? *[pause]* Now keep your hand up if you wrote 20 custom cover letters. *[most drop]* That's the gap JobSpy closes."

### Problem (30s)
> "Job seekers juggle five to eight platforms, copy-paste their resume into ChatGPT for every application, and pay $29 a month for tools like Teal if they want anything better. Students and early-career applicants — especially internationals — need the tooling most and can afford it least."

### Solution overview (45s)
> "JobSpy: free, open, multi-platform. You upload your resume once. Every job card shows a match score and, critically, the skill gap — the missing required skills. One click generates a cover letter grounded in your actual resume and the specific job, not generic prose."

### Live walkthrough (2:15)
Move through the same flow as the video, faster:

1. **Search** "Data Scientist, San Francisco" → show LinkedIn + Indeed + others returning side by side (30s)
2. **Click a job** → show match score + "Missing skills: Kubernetes, Terraform" under the card (30s)
3. **Mention the tech** quickly: "Match score is a weighted skill overlap — 70% required, 30% preferred, with alias normalization so NodeJS and node.js count as the same skill." (15s)
4. **Generate cover letter** → read aloud one sentence that names a skill from your resume and one that names the role. Highlight: "notice this sentence references a specific project from my resume — that's the grounding." (60s)

### Technical highlight (45s, ROTATE between groups)

Pick a different one each rotation to keep yourself interested:

- **Resume parsing depth:** "3-layer detection, 200+ heading synonyms. 'Career Highlights,' 'My Toolkit,' 'Core Competencies' — all resolve correctly. We also fall back to structural ALL-CAPS detection for the weird ones."
- **Context-aware skill classification:** "For every skill in a JD, we look back 600 characters for the nearest signal word — 'required', 'must have', 'preferred', 'nice to have'. Skills flagged as preferred weight less in the match score."
- **Graceful degradation:** "Eight scrapers run concurrently. If Google Jobs CAPTCHAs or LinkedIn rate-limits, the other platforms still return. One flaky source never cascades into a failed search."

### Closing (20s)
> "Free. Open-source. Deployed on Railway. Here's the QR code — try it during the interactive segment. Numbers from our pilot eval: [F1 score] for job relevance, [groundedness score]/5 on cover letter human rating."

## 5-minute interactive — 3 activities

Have these instructions on a second screen or printed card so you don't have to narrate setup.

### Activity 1 — "Search a role you'd apply to" (90s)
- Visitor types a real query
- Before clicking: *"What match score would you predict for these?"*
- Reveal the scores and skill gaps. People love predicting.

### Activity 2 — "Generate a cover letter for any job on screen" (120s)
- Visitor picks a listed job; click generate
- While it's generating: *"It's grounded in the resume profile stored in the database — no copy-paste."*
- When done: read one sentence together, point to where it came from the resume

### Activity 3 — "Run the resume parser test suite" (60s, optional but impressive)
- Open terminal, run `python tasks/test_resume_parser_v2.py`
- Watch 25+ tests pass in real time
- *"200+ section synonyms, date-anchor segmentation, structural fallback. All tested."*
- This is a strong "technical depth" moment that differentiates from teams who just ship features

**Total:** ~4:30, leaves buffer for Q&A.

## Anticipated Q&A (one-sentence answers)

- **"How is this different from ChatGPT?"** — "ChatGPT doesn't remember your resume between sessions and can't see job boards. JobSpy stores your resume once, structurally extracts skills from both sides, and explicitly tells the model which skills you have and don't have."

- **"Why didn't you get all 8 scrapers working?"** — "All 8 are implemented. We prioritized reliability on 4–5 US boards for this demo. The international boards — Bayt, Naukri, BDJobs — need platform-specific reliability hardening that's in future work."

- **"What's your evaluation methodology?"** — "Pilot eval: 25 manually-labeled jobs for match classification, and 5 cover letters rated by 3 reviewers across 4 Likert-scale criteria. We cite F1 of [X] and groundedness of [Y]/5. A full 5-rater study is future work given the two-week project window."

- **"Can employers use this to screen?"** — "Not our target — we're building for applicants. The skill extraction could be repurposed, yes, but recruiter-side tooling would need different incentive design."

- **"How do you handle skills that aren't in your taxonomy?"** — "They get missed. Our taxonomy has ~500 entries covering common tech skills. Expanding it is straightforward — it's a CSV — and automatically populating it from ESCO or O*NET is a future-work item."

- **"Is there a privacy story?"** — "Resumes are stored keyed to a session on Railway; single-user MVP. A production version would add proper auth, per-user isolation, and explicit data retention controls. Important to flag but out of scope for this project."

- **"What happens if Claude is down?"** — "The generation endpoint returns a 500 with a retry button. Matching and search still work without Claude. The system degrades gracefully rather than failing globally."

## Backup ladder (execute in order if things break)

1. **Railway slow/down:** switch to `localhost:8000` (both pre-tested this morning).
2. **Localhost misbehaves:** play the recorded walkthrough you made for the video; narrate live.
3. **Claude API is down:** open the 3 pre-generated sample cover letters from Markdown files; show those instead.
4. **Total laptop crash:** hand out the one-pager, walk through screenshots on your phone. Own it, make a joke, move on.

## Energy management

6–7 rotations in a row is physically tiring. Between groups:
- Sip water
- Three deep breaths
- Reset the UI: cleared search bar, no generated letter open, no error toasts
- Vary which technical highlight you open with — otherwise you'll deliver the 4th one on autopilot and it'll show
