# JobSpy
### Free NLP-Assisted Job Discovery & Cover Letter Generation

---

**The problem.** Job seekers juggle 5–8 platforms, copy-paste their resume into ChatGPT for every cover letter, and pay $29/month for tools like Teal — pricing out the students and early-career applicants who need tooling most.

**What it does.**
1. **Aggregates** postings from multiple US job boards (LinkedIn + Indeed live)
2. **Scores** each job against your stored resume with a visible skill gap
3. **Generates** cover letters grounded in your actual background — no copy-paste

**Key technical work.** 1,400+ entry skill taxonomy merged from curated internal list + pyresparser. 3-layer resume parser with 200+ heading synonyms. Context-aware required/preferred skill classifier (600-char signal lookback). Weighted match score (70% required + 30% preferred, alias-normalized). Claude API cover letter generation with explicit groundedness constraints.

**Evaluation.** Pilot study on 50 manually-labeled US SWE jobs. Precision@10 = 0.70, F1 = 0.67 at threshold 10%. 3-rater human eval across 4 criteria (relevance, fluency, professionalism, groundedness) on 5 generated letters.

**Tech stack.** FastAPI · SQLAlchemy · spaCy · Claude API · Vanilla JS + Tailwind · Railway

---

![Architecture](architecture.png)

---

**Try it:** [QR CODE 1 → Railway URL]      **Code:** [QR CODE 2 → GitHub repo]

Team: Kenneth Hou · Yida Xu · Miya Fu · Zichen Wang
CS/QTM/LING-329 · Emory University