# 05 — Video Script (5–10 min, 2 rubric pts — NON-NEGOTIABLE)

**Owner:** You, Day 2 morning.
**Goal:** Cover all 4 rubric bullets — (1) overview, (2) features, (3) technical highlights, (4) use cases — in ~7 minutes.
**Time box:** 3 hours including recording and light editing.
**Tools:** QuickTime (Mac) or OBS Studio.

## Why this script is stronger than my first draft

After reading your actual code, the technical-highlights section can go deeper with claims you can genuinely back up:
- 200+ heading synonyms in `SECTION_SYNONYMS`
- 3-layer resume detection system (synonym + date-anchor + structural fallback)
- Context-aware skill classification with 600-char lookback for required/preferred signals
- 100+ alias normalizations for skill matching
- 60+ region keyword mappings for location-aware platform routing
- A carefully-tuned Claude system prompt (no em-dashes, no bullets, grounded in matched/missing skills)

## Structure (target 7 minutes)

### [0:00–0:45] Problem & Solution
*Open with face-cam or slide, narrate over it.*

> "Job seekers juggle five to eight platforms every time they search, and the tools that make cover letters tolerable — Teal, Simplify — are paywalled at $29 a month. General-purpose LLMs like ChatGPT work if you're willing to paste your resume into every conversation, but most serious applicants apply to dozens of roles. That workflow doesn't scale.
>
> JobSpy is a free, open, NLP-assisted job discovery and application system. It aggregates postings from multiple boards, computes a skill-level match score with a visible skill gap, and generates resume-grounded cover letters — your resume is stored once, never copy-pasted again."

### [0:45–1:15] Architecture Overview
*Screen: architecture diagram (see `07_rubric_coverage_plan.md`).*

> "Two modules. The Job Discovery Module runs eight platform scrapers concurrently through a FastAPI backend, normalizes results into a 34-column unified schema, and persists to SQL. The Cover Letter Module parses resumes once using a 3-layer spaCy pipeline, stores the structured profile, and passes both sides into Claude for grounded generation. A 5-page vanilla-JS frontend ties them together — no build step."

### [1:15–4:00] Feature Walkthrough (live screen recording)

Record your screen doing the happy path. Narrate over it (write the voiceover first, then re-record audio over the silent screen capture — much easier than talking live).

**Feature 1 — Resume upload (35s)**
- Drag a PDF onto the profile page
- Narrate: *"Resume parsing uses a 3-layer detection system. Layer 1 matches headings against 200+ synonyms — so 'Career Highlights,' 'My Toolkit,' 'Core Competencies' all resolve correctly. Layer 2 uses date ranges as anchors to split out individual work entries. Layer 3 falls back to ALL-CAPS and Title-Case detection for anything the first two layers miss."*
- Show the parsed skills, experience years, education appearing

**Feature 2 — Multi-platform search (50s)**
- Enter a real query: "Software Engineer, New York, NY"
- Narrate: *"Under the hood, a location-aware platform selector with sixty region keyword mappings automatically includes Naukri for India, Bayt for the Middle East, BDJobs for Bangladesh. For a US query like this one, we hit LinkedIn, Indeed, Glassdoor, Google Jobs, and ZipRecruiter — all in parallel."*
- Show results streaming in, labeled by source

**Feature 3 — Match score + skill gap (55s)**
- Click on a job card
- Point at the match score
- Narrate: *"The score is a weighted skill overlap. Required matches count 70 percent, preferred count 30. We normalize aliases — NodeJS, node.js, Node js all collapse to the same canonical skill, so spelling variation doesn't tank your score. Under every job we render the skill gap: exactly which required skills are missing from the candidate's resume. That's what makes the number actionable."*
- Hover on the "Missing skills" line

**Feature 4 — Cover letter generation (50s)**
- Click "Generate cover letter"
- Wait for it to appear (if slow, say: *"This is a live Claude API call"*)
- Read 2 sentences aloud that reference specific resume skills
- Narrate: *"The prompt is constructed from the extracted resume entities and the job's required and preferred skill lists — not the raw text of either. That structured grounding is why JobSpy produces different output than pasting into ChatGPT: we explicitly tell the model which skills the candidate has and which are missing, and we forbid inventing credentials that aren't in the profile."*

### [4:00–5:30] Technical Highlights

Pick 3 and give each ~30 seconds.

**1. Context-aware skill classification**
> "Our skill extractor doesn't just match skills — it classifies each one as required or preferred based on surrounding context. For every mention, we look back 600 characters for the most recent signal word like 'must have' or 'nice to have'. If a skill appears under 'preferred' in the JD, it's weighted lower in the match score. That's how we avoid the classic mistake of treating nice-to-have skills the same as must-haves."

**2. Grounded prompt engineering**
> "The cover letter prompt is deliberately structured. We pass in candidate name, years of experience, parsed skills, the specific role and company, the required skills, the preferred skills, the matched and missing skill lists separately — and then explicitly instruct Claude not to claim any skill listed under 'missing required.' We also constrain the format: no bullet points, no em-dashes, no hollow openers like 'I am excited to apply.' The output reads like a real person wrote it."

**3. Concurrent scraping with error isolation**
> "All eight platform scrapers run in parallel via ThreadPoolExecutor. If LinkedIn rate-limits or Google Jobs gates on CAPTCHA, the other platforms' results still come back — we catch per-future exceptions so one flaky source doesn't cascade into a failed search. It's a small thing, but it's the difference between a production tool and a demo."

### [5:30–6:30] Use Case Examples

Two concrete scenarios:

> "Scenario one: a graduating computer science student applying to 15 new-grad roles over two weeks. They upload their resume once. For each role, they see the match score and skill gap immediately — some roles they thought were a fit turn out to require Kubernetes or Terraform they don't have. That's useful information before writing a cover letter. For the ones that do fit, the letter is generated in under ten seconds with specific references to projects from their actual resume.
>
> Scenario two: an international student who can't justify $29 a month for Teal. JobSpy is free and open-source, the code implements Naukri for India and Bayt for the Middle East — giving access to tools this group is systematically priced out of."

### [6:30–7:00] Impact & Future Work

> "JobSpy closes a real equity gap. The students and early-career applicants who most need tooling for job search are the ones least able to pay for it. Future work includes hardening the international scrapers for production reliability, a longitudinal dataset for research into ghost-posting patterns, and a full 5-reviewer evaluation study. But what's shipped today is a complete, deployed, end-to-end system you can use right now."

*(End card or closing line. Maybe: "Repo link and demo URL in the description.")*

## Recording tips

- **Write voiceover first**, then screen-record silently, then dub audio. Tiny edits are easy this way.
- **Don't do one take.** Record in 3–4 segments and stitch. QuickTime "File → New Screen Recording" lets you select an area.
- **Audio matters more than video.** Quiet room. Earbuds with built-in mic if you don't have a USB mic. No fan, no dishwasher running.
- **Cursor visibility:** enable cursor highlighting on macOS (System Settings → Accessibility → Pointer) for screen segments.
- **Browser prep:** incognito window, no extensions showing, no bookmarks bar, font zoomed to 110%, notifications off (Do Not Disturb on).
- **If something breaks on camera:** keep going, cut it in editing. Don't re-take from scratch.

## Definition of done

- [ ] Duration: 5:00–10:00
- [ ] All 4 rubric bullets covered explicitly (overview, features, tech, use cases)
- [ ] Audio is clean
- [ ] File exported as MP4 at 1080p minimum
- [ ] Uploaded to Canvas

## Hard rule

If Day 2 morning rolls around and you're tempted to squeeze in one more scraper fix — don't. Record the video. A B+ video beats an A- codebase with no submission.
