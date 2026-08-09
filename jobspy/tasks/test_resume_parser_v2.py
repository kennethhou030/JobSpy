"""
Full test suite for resume_parser.py v2.
Run from the project root: python tasks/test_resume_parser_v2.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.nlp.resume_parser import (
    _normalize_heading,
    _is_section_header,
    segment_sections,
    extract_email,
    extract_phone,
    extract_linkedin,
    parse_certifications,
    parse_languages,
    calculate_experience_years,
    RE_DATE_RANGE,
    _fix_concatenated_words,
    _parse_single_job_entry,
)

errors = []

def check(name, condition, detail=""):
    if not condition:
        errors.append(f"FAIL [{name}] {detail}")
        print(f"  x {name}: {detail}")
    else:
        print(f"  ok {name}")

print("\n── Section Header Detection ──")
tests = [
    ("work experience",          True, "experience"),
    ("WORK EXPERIENCE",          True, "experience"),
    ("Professional Background",  True, "experience"),
    ("SKILLS",                   True, "skills"),
    ("Areas of Expertise",       True, "skills"),
    ("Core Competencies",        True, "skills"),
    ("Volunteer Experience",     True, "volunteer"),
    ("Community Involvement",    True, "volunteer"),
    ("EXTRACURRICULAR",          True, "volunteer"),
    ("Projects",                 True, "projects"),
    ("Open Source Projects",     True, "projects"),
    ("Certifications",           True, "certifications"),
    ("Licenses & Certifications",True, "certifications"),
    ("EDUCATION",                True, "education"),
    ("Academic Background",      True, "education"),
    ("Summary",                  True, "summary"),
    ("About Me",                 True, "summary"),
    ("Languages",                True, "languages"),
    ("I developed a feature.",   False, None),
    ("The team shipped it.",     False, None),
]
for line, expected_is_header, expected_canonical in tests:
    is_h, canon = _is_section_header(line)
    check(
        f"header: '{line}'",
        is_h == expected_is_header and (canon == expected_canonical or not expected_is_header),
        f"got is_header={is_h}, canonical={canon}"
    )

print("\n── Regex Patterns ──")
check("email basic",    extract_email("Contact: jane.doe@gmail.com") == "jane.doe@gmail.com")
check("email plus",     extract_email("user+tag@example.co.uk") == "user+tag@example.co.uk")
check("phone US",       extract_phone("(404) 555-1234") is not None)
check("phone intl",     extract_phone("+1 800 555 9999") is not None)
check("linkedin",       extract_linkedin("linkedin.com/in/janedoe") is not None)
check("date range 1",   bool(RE_DATE_RANGE.search("Jan 2020 - Mar 2022")))
check("date range 2",   bool(RE_DATE_RANGE.search("2018 - Present")))
check("date range 3",   bool(RE_DATE_RANGE.search("September 2019 to December 2021")))
check("no date match",  not RE_DATE_RANGE.search("We have 2020 goals"))

print("\n── Section Segmentation ──")
sample_resume = """
Jane Doe
jane@example.com | (555) 123-4567

SUMMARY
Experienced software engineer with 5 years building scalable systems.

WORK EXPERIENCE
Software Engineer
Acme Corp
Jan 2021 - Present
Built REST APIs with FastAPI
Led migration to PostgreSQL

Junior Developer
StartupXYZ
Jun 2019 - Dec 2020
Developed React frontend

SKILLS
Python, FastAPI, Docker, PostgreSQL, React, SQL

EDUCATION
B.S. Computer Science
Georgia Tech
2015 - 2019

PROJECTS
JobSpy Personal Project
Built a job scraper using Python and FastAPI
Tech: Python, FastAPI, SQLite

VOLUNTEER EXPERIENCE
Code for Atlanta
2020 - 2021
Taught Python workshops to high school students

CERTIFICATIONS
AWS Certified Solutions Architect
Google Cloud Professional Data Engineer
"""
sections = segment_sections(sample_resume)
check("detects experience section", "experience" in sections)
check("detects skills section",     "skills" in sections)
check("detects education section",  "education" in sections)
check("detects projects section",   "projects" in sections)
check("detects volunteer section",  "volunteer" in sections)
check("detects certifications",     "certifications" in sections)
check("skills content correct",     "Python" in sections.get("skills", ""))

print("\n── Experience Year Calculation ──")
entries = [
    {"start_year": 2019, "end_year": 2021, "is_current": False},
    {"start_year": 2021, "end_year": 2024, "is_current": True},
]
yrs = calculate_experience_years(entries, "")
check("experience years ~5", 4 <= yrs <= 6, f"got {yrs}")

overlapping = [
    {"start_year": 2018, "end_year": 2022, "is_current": False},
    {"start_year": 2020, "end_year": 2024, "is_current": True},
]
yrs2 = calculate_experience_years(overlapping, "")
check("overlap not double-counted", yrs2 <= 7, f"got {yrs2}")

print("\n── Certifications & Languages ──")
cert_text = "- AWS Certified Solutions Architect\n- Google Cloud Professional\n- Certified Scrum Master"
certs = parse_certifications(cert_text)
check("parses 3 certs", len(certs) == 3, str(certs))

lang_text = "English (Fluent), Spanish, Mandarin (Conversational)"
langs = parse_languages(lang_text)
check("parses 3 languages", len(langs) == 3, str(langs))

print("\n── Education Concatenation Fix ──")
check("splits TitleCase institution",
    _fix_concatenated_words("EmoryUniversity") == "Emory University")

check("splits degree with prepositions",
    "Bachelor of Science" in _fix_concatenated_words(
        "BachelorofScienceinComputerScience"))

check("leaves short tokens alone",
    _fix_concatenated_words("GPA PhD AWS") == "GPA PhD AWS")

print("\n── Company-First Format (B1) ──")
import spacy as _spacy
nlp = _spacy.load("en_core_web_md")

entry_b1 = """Ralph Lauren Washington, D.C.
Corporate Finance Intern June 2021-August 2021
Collaborated with 5 interns to analyze revenue.
Analyzed revenue streams from 8 key product lines."""

parsed = _parse_single_job_entry(entry_b1, nlp)
check("B1: title extracted from date line",
    parsed.get("title") == "Corporate Finance Intern",
    str(parsed))
check("B1: company extracted from pre-date line",
    parsed.get("company") is not None and "Ralph Lauren" in parsed["company"],
    str(parsed))
check("B1: location stripped from company",
    "Washington" not in (parsed.get("company") or ""),
    str(parsed))
check("B1: bullets are description not company",
    "Collaborated" in parsed.get("description", ""),
    str(parsed))

entry_b1_dept = """McDonough School of Business, Accounting Department Washington, D.C.
Lead Research Assistant January 2021-Present
Use R to run statistical analyses."""

parsed2 = _parse_single_job_entry(entry_b1_dept, nlp)
check("B1: department company extracted",
    parsed2.get("company") is not None and "McDonough" in parsed2["company"],
    str(parsed2))
check("B1: title correct for department entry",
    parsed2.get("title") == "Lead Research Assistant",
    str(parsed2))

print("\n" + "=" * 50)
if errors:
    print(f"FAILED: {len(errors)} test(s)")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"ALL TESTS PASSED")
