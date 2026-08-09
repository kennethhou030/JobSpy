"""
cover_letter_eval.py
Generates cover letters for a batch of labeled jobs and exports them
to a file for human evaluation (5 reviewers, 1-5 Likert scale).

Usage:
    python evaluation/cover_letter_eval.py --n 10 --output evaluation/cl_for_review.md
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job, get_resume_profile
from jobspy.nlp.cover_letter import generate_cover_letter
from jobspy.nlp.match_scorer import compute_match_score


def generate_batch(n: int = 10, output_path: str = "evaluation/cl_for_review.md"):
    """
    Generate cover letters for the top N matching jobs and export for review.
    """
    print(f"Loading resume profile...")
    resume = get_resume_profile(user_id="default")
    if not resume:
        print("ERROR: No resume found.")
        sys.exit(1)

    resume_dict = {
        "name": resume.name,
        "summary": resume.summary,
        "parsed_skills": resume.parsed_skills or [],
        "experience_years": resume.experience_years,
    }

    print(f"Fetching top {n} jobs from DB...")
    with SessionLocal() as session:
        jobs = session.query(Job).filter(
            Job.description.isnot(None)
        ).limit(n * 3).all()  # fetch more, filter below

    if not jobs:
        print("ERROR: No jobs with descriptions found in DB. Run a scrape first.")
        sys.exit(1)

    # Sort by match score and take top N
    scored = []
    for job in jobs:
        score = compute_match_score(
            resume_dict["parsed_skills"],
            job.required_skills or [],
            job.preferred_skills or [],
        )
        scored.append((score, job))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_jobs = scored[:n]

    print(f"Generating {len(top_jobs)} cover letters...\n")

    output_lines = [
        f"# Cover Letter Human Evaluation",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Candidate: {resume.name}",
        f"",
        f"## Instructions for Reviewers",
        f"Rate each cover letter on a 1-5 Likert scale across 4 criteria:",
        f"- **Relevance** (1-5): How well does it address the specific job?",
        f"- **Fluency** (1-5): Is it well-written and grammatically correct?",
        f"- **Professionalism** (1-5): Does it have an appropriate professional tone?",
        f"- **Groundedness** (1-5): Does it accurately reflect the candidate's actual resume?",
        f"",
        f"---",
        f"",
    ]

    for i, (score, job) in enumerate(top_jobs, 1):
        print(f"  [{i}/{len(top_jobs)}] Generating for: {job.title} @ {job.company}...")
        try:
            job_dict = {
                "title": job.title,
                "company": job.company,
                "location": str(job.location) if job.location else "N/A",
                "description": job.description,
                "required_skills": job.required_skills or [],
                "preferred_skills": job.preferred_skills or [],
            }
            letter = generate_cover_letter(resume_dict, job_dict)

            output_lines += [
                f"## Cover Letter {i}: {job.title} @ {job.company}",
                f"**Job ID:** `{job.id}`",
                f"**Match Score:** {score:.1f}%",
                f"**Required Skills:** {', '.join(job.required_skills or ['none extracted'])}",
                f"**Candidate Skills (from resume):** {', '.join(resume_dict['parsed_skills'][:10])}",
                f"",
                f"### Generated Cover Letter",
                f"```",
                letter,
                f"```",
                f"",
                f"### Reviewer Ratings (fill in below)",
                f"| Criteria | Reviewer 1 | Reviewer 2 | Reviewer 3 | Reviewer 4 | Reviewer 5 | Average |",
                f"|----------|-----------|-----------|-----------|-----------|-----------|---------|",
                f"| Relevance (1-5) | | | | | | |",
                f"| Fluency (1-5) | | | | | | |",
                f"| Professionalism (1-5) | | | | | | |",
                f"| Groundedness (1-5) | | | | | | |",
                f"",
                f"**Notes:**",
                f"",
                f"---",
                f"",
            ]
        except Exception as e:
            print(f"    ERROR generating letter: {e}")
            output_lines.append(f"## Cover Letter {i}: GENERATION FAILED\nError: {e}\n\n---\n")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"\nReview document saved to: {output_file}")
    print("Share this file with your 5 reviewers to fill in the rating table.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate cover letters for human evaluation")
    parser.add_argument("--n", type=int, default=10, help="Number of cover letters to generate")
    parser.add_argument("--output", default="evaluation/cl_for_review.md")
    args = parser.parse_args()
    generate_batch(args.n, args.output)
