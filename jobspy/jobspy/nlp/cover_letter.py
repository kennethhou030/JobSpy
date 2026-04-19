"""
cover_letter.py
Generates personalized, resume-grounded cover letters using the Claude API.
The resume profile (stored in DB from Phase 3) and job description are automatically
combined into a structured prompt — no manual copy-paste required.
"""

from __future__ import annotations
import os
import anthropic

# The model to use for generation (as specified in the proposal)
CLAUDE_MODEL = "claude-opus-4-6"

# Maximum tokens for cover letter (roughly 400–600 words)
MAX_TOKENS = 1024

COVER_LETTER_SYSTEM = """You are a seasoned hiring manager and professional writer with 15 years of experience \
in tech recruiting and career coaching. You write cover letters that read like they came from a real person \
who knows the industry, not a career-advice template.

Your letters:
- Sound conversational and confident, the way a senior professional would actually write
- Reference the specific company and role with genuine, grounded enthusiasm
- Draw only on skills and experiences present in the candidate's profile
- Use varied sentence structure and natural transitions, never formulaic phrasing
- Never use bullet points, dashes, em dashes, or list formatting of any kind
- Never use hyphens as punctuation (compound adjectives like "well-known" are fine; em dashes and en dashes are not)
- Read as 3 to 4 cohesive paragraphs of flowing prose
- Avoid hollow openers like "I am excited to apply" or "I am writing to express my interest"
- Never invent credentials, titles, or experiences not in the candidate's profile"""

COVER_LETTER_PROMPT = """Write a tailored cover letter for the job application below.

=== CANDIDATE PROFILE ===
Name: {name}
Years of Experience: {experience_years}
Summary: {summary}
Skills: {resume_skills}

=== TARGET JOB ===
Role: {job_title}
Company: {company_name}
Location: {location}

Required Skills: {required_skills}
Preferred Skills: {preferred_skills}

Matched Skills (candidate already has): {matched_skills}
Missing Required Skills (candidate lacks): {missing_required}

Job Description (excerpt):
{job_description}

=== INSTRUCTIONS ===
Write 3 to 4 paragraphs of natural, flowing prose. No bullet points. No dashes or em dashes as punctuation.

Paragraph 1: Open with a strong, specific statement about why this role and company. Lead with the candidate's most relevant qualification.
Paragraph 2: Walk through 2 or 3 concrete skills from the candidate's profile that directly address what the role requires. Be specific about what the candidate built or accomplished.
Paragraph 3: Explain why this company or role fits where the candidate wants to take their career. Connect something real in the job description to the candidate's goals.
Paragraph 4 (closing): Express genuine interest, invite next steps, and close professionally.

Do not mention any skill listed under "Missing Required Skills" as something the candidate has.
Output only the cover letter text. Start with "Dear Hiring Manager," unless a contact name is available. No preamble, no subject line, no label."""


def generate_cover_letter(resume: dict, job: dict) -> str:
    """
    Generate a tailored cover letter using Claude.

    Args:
        resume: Parsed resume profile dict (from get_resume_profile())
                Expected keys: name, summary, parsed_skills, experience_years
        job: Job dict with title, company, location, description, required_skills, preferred_skills

    Returns:
        Cover letter as a string
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Add it to your .env file or export it in your shell."
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Compute skill alignment for the prompt
    from jobspy.nlp.match_scorer import compute_skill_gap
    gap = compute_skill_gap(
        resume_skills=resume.get("parsed_skills") or [],
        job_required_skills=job.get("required_skills") or [],
        job_preferred_skills=job.get("preferred_skills") or [],
    )

    # Truncate job description to stay within token limits
    description = (job.get("description") or "")[:3000]

    prompt = COVER_LETTER_PROMPT.format(
        name=resume.get("name") or "the candidate",
        experience_years=resume.get("experience_years") or "N/A",
        summary=(resume.get("summary") or "")[:400],
        resume_skills=", ".join(resume.get("parsed_skills") or [])[:500],
        job_title=job.get("title") or "the position",
        company_name=job.get("company") or "the company",
        location=job.get("location") or "N/A",
        required_skills=", ".join(job.get("required_skills") or []),
        preferred_skills=", ".join(job.get("preferred_skills") or []),
        matched_skills=", ".join(gap.get("matched") or []),
        missing_required=", ".join(gap.get("missing_required") or []),
        job_description=description,
    )

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=COVER_LETTER_SYSTEM,
        messages=[
            {"role": "user", "content": prompt}
        ],
        timeout=30.0,
    )

    # Guard: find the first text block in the response
    for block in message.content:
        if hasattr(block, "text"):
            return block.text.strip()

    raise ValueError("Claude returned no text content in its response.")
