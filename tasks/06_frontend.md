# Phase 6 — Frontend Integration
> Prerequisite: Phases 0 through 5 must be complete. All backend features must be working.

## Context
All backend features (skill extraction, resume storage, match scoring, skill gap, cover letter generation) are built. This phase wires them into the user-facing frontend. The existing UI already has a 3-column dashboard, job detail panel, and scraper page. We need to extend — not rewrite — those pages and add a nav bar shared across all pages.

---

## Your Job in This Phase
1. Read `frontend/index.html` thoroughly — understand the full DOM structure before touching anything
2. Add a shared navigation bar to all HTML pages
3. Add Match Score column to the jobs table
4. Add Skill Gap + Cover Letter panel in the job detail right pane
5. Add a "Resume Status" banner on the dashboard
6. Create `frontend/applications.html` — a cover letters tracker page

---

## Step 1 — Read These Files Fully First
Read every line before making any changes:
- `frontend/index.html` — main dashboard (jobs table + detail panel)
- `frontend/scraper.html` — scraper control page
- `frontend/history.html` — scrape session log
- `frontend/js/api.js` — shared API client with `window.API` and `window.fmt`
- `frontend/profile.html` — resume upload page (created in Phase 3)

Understand:
- How jobs are fetched and rendered (look for `window.API.queryJobs()` calls)
- How the right panel (job detail) is populated (look for click handlers)
- The Tailwind classes in use (so new elements match the style)
- The color scheme (primary button colors, badge colors, font sizes)

---

## Step 2 — Add a Shared Navigation Bar

All 5 pages need the same nav bar. Add this HTML snippet as the **very first element inside `<body>`** on all pages: `index.html`, `scraper.html`, `history.html`, `profile.html`, and the new `applications.html`.

```html
<!-- Shared Navigation Bar -->
<nav class="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
  <span class="font-bold text-lg text-indigo-600 mr-4">JobSpy</span>
  <a href="/index.html" class="text-sm font-medium text-gray-600 hover:text-indigo-600 transition-colors">Dashboard</a>
  <a href="/scraper.html" class="text-sm font-medium text-gray-600 hover:text-indigo-600 transition-colors">Scraper</a>
  <a href="/profile.html" class="text-sm font-medium text-gray-600 hover:text-indigo-600 transition-colors">Profile</a>
  <a href="/applications.html" class="text-sm font-medium text-gray-600 hover:text-indigo-600 transition-colors">Cover Letters</a>
  <a href="/history.html" class="text-sm font-medium text-gray-600 hover:text-indigo-600 transition-colors">History</a>
  <!-- Resume status indicator -->
  <div id="resume-status-nav" class="ml-auto text-xs text-gray-400">Checking resume...</div>
</nav>
```

Add this script snippet at the bottom of each page (before `</body>`) to update the resume status indicator in the nav:

```html
<script>
  // Update nav resume status badge on every page
  (async () => {
    try {
      const resume = await window.API.getResume();
      const el = document.getElementById('resume-status-nav');
      if (el) {
        if (resume) {
          el.innerHTML = `<span class="text-green-600">✓ Resume: ${resume.name || 'Uploaded'}</span>`;
        } else {
          el.innerHTML = `<a href="/profile.html" class="text-amber-500 hover:underline">⚠ Upload Resume</a>`;
        }
      }
    } catch {}
  })();
</script>
```

---

## Step 3 — Add Match Score Column to Jobs Table (`frontend/index.html`)

Find the jobs table in `index.html`. It likely has column headers like: Site | Title | Company | Location | Posted | Type | Remote | Salary | Link.

**Add "Match" as a new column header** (insert it after Salary, before Link):
```html
<th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Match</th>
```

**In the row rendering JavaScript**, find where each job's columns are built (likely a template string or `innerHTML` assignment). Add this for the Match cell:

```javascript
// Match score cell — insert alongside other td cells
const matchScore = job.match_score;
const matchCell = matchScore !== null && matchScore !== undefined
  ? `<td class="px-3 py-2 text-sm">
      <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold
        ${matchScore >= 75 ? 'bg-green-100 text-green-800'
          : matchScore >= 50 ? 'bg-yellow-100 text-yellow-800'
          : 'bg-red-100 text-red-800'}">
        ${matchScore.toFixed(0)}%
      </span>
    </td>`
  : `<td class="px-3 py-2 text-sm text-gray-300">—</td>`;
```

**Update the jobs fetch call** to include sort by match:
- Add a "Sort by Match" button or dropdown to the filter sidebar
- When clicked, re-fetch with `sort_by=match_score` param:
```javascript
const jobs = await window.API.queryJobs({ ...filters, sort_by: 'match_score' });
```

---

## Step 4 — Add Skill Gap + Cover Letter Panel to Job Detail (`frontend/index.html`)

Find the right panel where job details are displayed when a user clicks a job row. It currently shows the job description and basic metadata.

**After the job description section**, add this new section to the detail panel. Wire it up in the JavaScript click handler that populates the panel:

```html
<!-- Skill Gap Section — injected dynamically by JS -->
<div id="skill-gap-section" class="mt-4 hidden">
  <h3 class="text-sm font-semibold text-gray-700 mb-2">Skill Match</h3>

  <!-- Matched skills -->
  <div id="matched-skills" class="mb-2">
    <p class="text-xs text-gray-500 mb-1">✓ You have</p>
    <div id="matched-chips" class="flex flex-wrap gap-1"></div>
  </div>

  <!-- Missing required -->
  <div id="missing-required-section" class="mb-2">
    <p class="text-xs text-gray-500 mb-1">✗ Missing (Required)</p>
    <div id="missing-required-chips" class="flex flex-wrap gap-1"></div>
  </div>

  <!-- Missing preferred -->
  <div id="missing-preferred-section">
    <p class="text-xs text-gray-500 mb-1">△ Missing (Preferred)</p>
    <div id="missing-preferred-chips" class="flex flex-wrap gap-1"></div>
  </div>
</div>

<!-- Cover Letter Section -->
<div id="cover-letter-section" class="mt-6 border-t pt-4 hidden">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-sm font-semibold text-gray-700">Cover Letter</h3>
    <button
      id="generate-cl-btn"
      class="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded hover:bg-indigo-700 transition-colors"
      onclick="generateCoverLetter()">
      Generate with AI
    </button>
  </div>

  <div id="cl-loading" class="hidden text-xs text-gray-400 animate-pulse">
    Generating with Claude... (this takes ~5 seconds)
  </div>

  <div id="cl-content" class="hidden">
    <textarea
      id="cl-text"
      class="w-full text-sm text-gray-700 border border-gray-200 rounded p-3 h-64 resize-y"
      readonly></textarea>
    <div class="flex gap-2 mt-2">
      <button
        onclick="copyCoverLetter()"
        class="text-xs text-indigo-600 border border-indigo-300 px-3 py-1 rounded hover:bg-indigo-50">
        Copy
      </button>
    </div>
  </div>

  <div id="cl-error" class="hidden text-xs text-red-500 mt-2"></div>
</div>
```

**In the JavaScript** that populates the job detail panel on click, add this logic after setting the job description:

```javascript
async function populateJobDetail(job) {
  // ... existing code to populate title, company, description etc. ...

  // Skill gap section
  const skillGapSection = document.getElementById('skill-gap-section');
  const clSection = document.getElementById('cover-letter-section');

  if (job.skill_gap) {
    skillGapSection.classList.remove('hidden');
    clSection.classList.remove('hidden');

    // Matched chips (green)
    const matchedChips = document.getElementById('matched-chips');
    matchedChips.innerHTML = job.skill_gap.matched.length
      ? job.skill_gap.matched.map(s =>
          `<span class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800">${s}</span>`
        ).join('')
      : '<span class="text-xs text-gray-400">None matched</span>';

    // Missing required chips (red)
    const missingReqChips = document.getElementById('missing-required-chips');
    missingReqChips.innerHTML = job.skill_gap.missing_required.length
      ? job.skill_gap.missing_required.map(s =>
          `<span class="px-2 py-0.5 text-xs rounded-full bg-red-100 text-red-700">${s}</span>`
        ).join('')
      : '<span class="text-xs text-gray-400">None missing</span>';

    // Missing preferred chips (orange)
    const missingPrefChips = document.getElementById('missing-preferred-chips');
    missingPrefChips.innerHTML = job.skill_gap.missing_preferred.length
      ? job.skill_gap.missing_preferred.map(s =>
          `<span class="px-2 py-0.5 text-xs rounded-full bg-amber-100 text-amber-700">${s}</span>`
        ).join('')
      : '<span class="text-xs text-gray-400">None missing</span>';
  } else {
    skillGapSection.classList.add('hidden');
    clSection.classList.add('hidden');
  }

  // Store current job ID for cover letter generation
  window.currentJobId = job.id;

  // Check if cover letter already exists
  const existing = await window.API.getCoverLetter(job.id);
  if (existing) {
    document.getElementById('cl-text').value = existing.cover_letter;
    document.getElementById('cl-content').classList.remove('hidden');
  } else {
    document.getElementById('cl-content').classList.add('hidden');
    document.getElementById('cl-text').value = '';
  }
}

async function generateCoverLetter() {
  const jobId = window.currentJobId;
  if (!jobId) return;

  const btn = document.getElementById('generate-cl-btn');
  const loading = document.getElementById('cl-loading');
  const content = document.getElementById('cl-content');
  const errorEl = document.getElementById('cl-error');

  btn.disabled = true;
  loading.classList.remove('hidden');
  content.classList.add('hidden');
  errorEl.classList.add('hidden');

  try {
    const result = await window.API.generateCoverLetter(jobId);
    if (result.detail) throw new Error(result.detail);
    document.getElementById('cl-text').value = result.cover_letter;
    content.classList.remove('hidden');
  } catch (err) {
    errorEl.textContent = `Error: ${err.message}`;
    errorEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    loading.classList.add('hidden');
  }
}

function copyCoverLetter() {
  const text = document.getElementById('cl-text').value;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
  });
}
```

---

## Step 5 — Add Resume Status Banner to Dashboard (`frontend/index.html`)

Add this banner near the top of the main content area (below the nav, above the filters/table). It checks if a resume is uploaded and prompts the user to upload one if not:

```html
<!-- Resume status banner -->
<div id="resume-banner" class="hidden mx-4 mt-3 p-3 rounded-lg border text-sm"></div>
```

Wire it up in JavaScript (add to the page init):
```javascript
async function checkResumeBanner() {
  const banner = document.getElementById('resume-banner');
  try {
    const resume = await window.API.getResume();
    if (!resume) {
      banner.className = 'mx-4 mt-3 p-3 rounded-lg border text-sm bg-amber-50 border-amber-200 text-amber-800';
      banner.innerHTML = `
        <strong>No resume uploaded.</strong>
        <a href="/profile.html" class="underline ml-1">Upload your resume</a>
        to see match scores and generate cover letters.
      `;
    } else {
      banner.className = 'mx-4 mt-3 p-3 rounded-lg border text-sm bg-green-50 border-green-200 text-green-800';
      banner.innerHTML = `
        ✓ Resume on file: <strong>${resume.name || 'Uploaded'}</strong>
        (${resume.skills_count || resume.parsed_skills?.length || 0} skills, ${resume.experience_years || 0} years experience).
        <a href="/profile.html" class="underline ml-1">Update</a>
      `;
    }
  } catch {
    banner.classList.add('hidden');
  }
}
checkResumeBanner();
```

---

## Step 6 — Create `frontend/applications.html` (Cover Letters Tracker)

Create a new page that lists all generated cover letters. Match the style of `history.html`.

The page should:
- Show a table: Job Title | Company | Match Score | Generated | Preview | Actions
- Each row has a "View" button that expands/shows the full cover letter in a modal
- A "Copy" button per row
- Empty state when no letters exist: "No cover letters yet. Go to the Dashboard and click 'Generate with AI' on any job."

Fetch data from `GET /api/cover-letters` using `window.API.listCoverLetters()`.

---

## Step 7 — Visual QA Checklist

After all changes, open each page in a browser and verify:

**Dashboard (`index.html`):**
- [ ] Nav bar visible at top with links to all 5 pages
- [ ] Resume status banner shows correct state (amber if no resume, green if uploaded)
- [ ] Match Score column appears in jobs table with color-coded badges
- [ ] "Sort by Match" works and reorders jobs
- [ ] Clicking a job with skill gap data shows green/red/orange skill chips
- [ ] Cover letter section shows "Generate with AI" button
- [ ] Cover letter generation triggers loading state, then shows generated text
- [ ] Copy button copies the letter to clipboard

**Profile (`profile.html`):**
- [ ] Nav bar visible
- [ ] File upload works, shows parsed profile after upload

**Cover Letters (`applications.html`):**
- [ ] Nav bar visible
- [ ] Lists all generated letters
- [ ] View/expand works

**Scraper & History pages:**
- [ ] Nav bar visible, no other changes broken

---

## Completion Checklist
- [ ] Shared nav bar added to all 5 pages
- [ ] Nav resume status indicator works
- [ ] Match Score column + color badges in jobs table
- [ ] Sort by match works
- [ ] Skill gap chips (green/red/orange) in job detail panel
- [ ] Cover letter generation button, loading state, and display in job detail panel
- [ ] Resume status banner on dashboard
- [ ] `frontend/applications.html` created with cover letters list
- [ ] All pages visually consistent (same Tailwind style, same fonts)
- [ ] No JavaScript console errors on any page

## What's Next
When done, tell Kenneth "Phase 6 complete" and he will give you `07_evaluation.md`.
