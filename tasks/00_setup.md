# Phase 0 — Setup & Dependencies
> Feed this file to Claude Code first before any other phase.

## Context
This is a multi-phase project to extend the existing JobSpy codebase (a FastAPI + SQLite job scraper) with NLP features: skill extraction, resume parsing, semantic match scoring, skill gap analysis, and AI-generated cover letters.

The project is for a Computational Linguistics course (CS/QTM/LING-329). You are Kenneth's AI coding assistant. Do NOT rewrite or refactor anything that already works. Only add to the existing codebase.

---

## Your Job in This Phase
Set up the project structure, install all new dependencies, and confirm the existing app still runs. No feature code yet.

---

## Step 1 — Read These Existing Files First
Before touching anything, read and understand these files so you know the codebase:

1. `jobspy/__init__.py` — the main `scrape_jobs()` entry point
2. `jobspy/model.py` — the `JobPost` Pydantic model and all enums
3. `jobspy/database.py` — SQLAlchemy ORM: `Job` table, `ScrapeSession` table, `save_jobs()`, `get_jobs()`
4. `api/main.py` — all FastAPI routes
5. `api/schemas.py` — all Pydantic request/response schemas
6. `pyproject.toml` — current dependencies

---

## Step 2 — Create the NLP Module Directory

Create the following empty files (with minimal content):

**`jobspy/nlp/__init__.py`**
```python
# NLP subpackage: skill extraction, resume parsing, match scoring, cover letter generation
```

**`data/.gitkeep`** — empty file so the data/ directory exists in git

**`tasks/.gitkeep`** — empty file (this tasks/ folder should already exist)

---

## Step 3 — Install New Dependencies

Run these commands one at a time and confirm each succeeds:

```bash
pip install spacy --break-system-packages
python -m spacy download en_core_web_md
pip install scikit-learn --break-system-packages
pip install pypdf --break-system-packages
pip install python-docx --break-system-packages
pip install anthropic --break-system-packages
```

Then verify installations:
```bash
python -c "import spacy; nlp = spacy.load('en_core_web_md'); print('spacy OK')"
python -c "from sklearn.feature_extraction.text import TfidfVectorizer; print('sklearn OK')"
python -c "from pypdf import PdfReader; print('pypdf OK')"
python -c "from docx import Document; print('python-docx OK')"
python -c "import anthropic; print('anthropic OK')"
```

---

## Step 4 — Update pyproject.toml

Add the following to the `[project.dependencies]` or `[tool.poetry.dependencies]` section of `pyproject.toml`:

```toml
spacy = ">=3.7"
scikit-learn = ">=1.4"
pypdf = ">=4.0"
python-docx = ">=1.1"
anthropic = ">=0.25"
```

---

## Step 5 — Create the Skills Taxonomy CSV

Create `data/skills_taxonomy.csv` with the following content. This is the reference list spaCy will match against when extracting skills from job descriptions. Add it exactly as shown (Claude Code: expand this list to at least 200 entries covering software engineering, data science, product, design, and business roles):

```csv
skill
Python
JavaScript
TypeScript
Java
C++
C#
Go
Rust
Ruby
Swift
Kotlin
R
MATLAB
SQL
PostgreSQL
MySQL
SQLite
MongoDB
Redis
Elasticsearch
FastAPI
Flask
Django
Express
React
Vue
Angular
Next.js
Node.js
Spring Boot
Docker
Kubernetes
Terraform
AWS
GCP
Azure
CI/CD
GitHub Actions
Jenkins
Linux
Bash
Git
REST API
GraphQL
gRPC
Kafka
RabbitMQ
Spark
Hadoop
Airflow
dbt
Pandas
NumPy
Scikit-learn
TensorFlow
PyTorch
Hugging Face
spaCy
NLTK
OpenAI API
LangChain
Machine Learning
Deep Learning
NLP
Computer Vision
Data Engineering
Data Analysis
Statistical Modeling
A/B Testing
Figma
Product Management
Agile
Scrum
Jira
Excel
Tableau
Power BI
Looker
Communication
Leadership
Problem Solving
Project Management
```

---

## Step 6 — Create the data/resumes/ Directory

```bash
mkdir -p data/resumes
touch data/resumes/.gitkeep
```

---

## Step 7 — Verify the Existing App Still Runs

Run the existing FastAPI app and confirm it starts without errors:

```bash
uvicorn api.main:app --port 8000 --reload
```

Wait 5 seconds then hit `Ctrl+C`. If it starts cleanly, this phase is done.

If there are import errors, fix only those — do not refactor existing code.

---

## Completion Checklist
- [ ] `jobspy/nlp/__init__.py` created
- [ ] `data/skills_taxonomy.csv` created with 100+ skills
- [ ] `data/resumes/` directory exists
- [ ] All 5 pip packages installed and verified
- [ ] `pyproject.toml` updated with new deps
- [ ] `uvicorn api.main:app` starts without errors

## What's Next
When done, tell Kenneth "Phase 0 complete" and he will give you `01_platform_selector.md`.
