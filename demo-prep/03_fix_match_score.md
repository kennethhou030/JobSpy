# 03 — Fix Match Score (for Claude Code)

**Owner:** Claude Code.
**Goal:** Make match scores spread across a meaningful range. Algorithm is correct — the fix is data, not logic.
**Time box:** 1–2 hours.

## Context for CC (READ THIS BEFORE CHANGING ANY CODE)

I was wrong earlier. `jobspy/nlp/match_scorer.py` is NOT broken TF-IDF cosine. It's a proper weighted skill-overlap score:

```
required_ratio  = |resume_skills ∩ job_required_skills|  / |job_required_skills|
preferred_ratio = |resume_skills ∩ job_preferred_skills| / |job_preferred_skills|
score = required_ratio * 0.7 + preferred_ratio * 0.3  (→ 0–100)
```

With alias normalization (nodejs → node.js, k8s → kubernetes, etc.). This is architecturally correct. Do not replace it.

**Why scores are low in practice:** `job.required_skills` and `job.preferred_skills` are mostly empty lists, because `extract_skills()` only matches terms present in `data/skills_taxonomy.csv` — and that file only has ~170 entries (README overclaims 1000+). Small taxonomy → thin extraction → tiny intersection with resume → low scores.

## Tasks

### Step 1 — Verify the diagnosis (15 min)

Create `scripts/diagnose_match.py`:

```python
"""Diagnostic: print exactly where the signal is being lost."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job, get_resume_profile
from jobspy.nlp.match_scorer import compute_match_score, compute_skill_gap

resume = get_resume_profile(user_id="default")
if not resume:
    print("No resume uploaded."); sys.exit(1)

resume_skills = resume.parsed_skills or []
print(f"Resume: {len(resume_skills)} skills → {resume_skills[:15]}")

with SessionLocal() as s:
    jobs = s.query(Job).filter(Job.description.isnot(None)).limit(10).all()

print(f"\n{'Title':<45} {'Req':<5} {'Pref':<5} {'Score':<6}")
print("-" * 70)
for j in jobs:
    req, pref = j.required_skills or [], j.preferred_skills or []
    score = compute_match_score(resume_skills, req, pref)
    print(f"{(j.title or '')[:44]:<45} {len(req):<5} {len(pref):<5} {score:<6}")

# Aggregate stats
totals = [(len(j.required_skills or []), len(j.preferred_skills or [])) for j in jobs]
avg_req = sum(r for r, _ in totals) / len(totals) if totals else 0
avg_pref = sum(p for _, p in totals) / len(totals) if totals else 0
print(f"\nAvg required skills per job: {avg_req:.1f}")
print(f"Avg preferred skills per job: {avg_pref:.1f}")
```

Run it. If avg_req and avg_pref are < 3, taxonomy coverage is the culprit. Proceed to Step 2.

### Step 2 — Expand the skills taxonomy (45–60 min)

Your current `data/skills_taxonomy.csv` has ~170 entries. Target: ~500–700 entries covering the common vocabulary of CS/tech job descriptions. Ask CC to generate a comprehensive list across these categories:

- **Languages:** Python, JavaScript, TypeScript, Java, Kotlin, C++, C#, Go, Rust, Ruby, Swift, R, Scala, PHP, Objective-C, Dart, Perl, Haskell, Elixir, Clojure, Lua, Bash, PowerShell, Shell
- **Web frameworks:** React, Vue, Angular, Svelte, Next.js, Nuxt, Ember, Backbone, jQuery, Django, Flask, FastAPI, Express, NestJS, Koa, Rails, Laravel, Symfony, Spring, Spring Boot, ASP.NET, Gin, Fiber
- **Mobile:** React Native, Flutter, Ionic, SwiftUI, Jetpack Compose, Xamarin, Kotlin Multiplatform
- **Cloud providers:** AWS (and services: EC2, S3, Lambda, RDS, DynamoDB, SQS, SNS, CloudFront, Route 53, IAM, CloudFormation), GCP (BigQuery, Cloud Run, GKE, Pub/Sub, Cloud Functions), Azure (Functions, AKS, Cosmos DB, Service Bus), DigitalOcean, Heroku, Vercel, Netlify, Railway
- **Containers/orchestration:** Docker, Docker Compose, Kubernetes, Helm, Istio, OpenShift, Nomad, ECS, Fargate
- **CI/CD:** GitHub Actions, GitLab CI, CircleCI, Jenkins, Travis CI, TeamCity, Argo CD, Bamboo, Buildkite, Drone
- **IaC:** Terraform, Pulumi, CloudFormation, Ansible, Chef, Puppet, Packer, Vagrant
- **Databases:** PostgreSQL, MySQL, SQLite, MariaDB, SQL Server, Oracle, MongoDB, Cassandra, Redis, Elasticsearch, OpenSearch, Neo4j, DynamoDB, CosmosDB, Firestore, Supabase, Snowflake, BigQuery, Redshift, Databricks, ClickHouse, DuckDB, Timescale, Influx
- **Data/ML:** pandas, NumPy, SciPy, scikit-learn, TensorFlow, PyTorch, Keras, XGBoost, LightGBM, CatBoost, Hugging Face, Transformers, LangChain, LlamaIndex, spaCy, NLTK, OpenCV, Jupyter, MLflow, Weights & Biases, Airflow, Dagster, Prefect, dbt, Spark, Hadoop, Kafka, Flink, Beam, Tableau, Power BI, Looker, Metabase, Superset
- **Testing:** Jest, Mocha, Jasmine, Cypress, Playwright, Selenium, Puppeteer, Vitest, Testing Library, pytest, unittest, JUnit, RSpec, Gradle Test, Karma
- **Dev tools:** Git, GitHub, GitLab, Bitbucket, Jira, Linear, Asana, Notion, Confluence, Figma, Sketch, Adobe XD, VS Code, IntelliJ, PyCharm, WebStorm, Xcode, Android Studio
- **API/protocols:** REST, GraphQL, gRPC, WebSocket, Server-Sent Events, OpenAPI, Swagger, Postman, Insomnia, JSON-RPC, SOAP
- **Security:** OAuth, OAuth2, JWT, SAML, SSO, OIDC, TLS, PKI, OWASP, SAST, DAST, SOC 2, GDPR, HIPAA, Zero Trust, Penetration Testing
- **Monitoring/observability:** Datadog, New Relic, Splunk, Grafana, Prometheus, ELK Stack, Loki, Sentry, PagerDuty, OpsGenie, OpenTelemetry, Jaeger, Honeycomb
- **Soft/PM skills:** Agile, Scrum, Kanban, Waterfall, SAFe, OKRs, stakeholder management, cross-functional collaboration, technical writing, code review, mentoring, roadmapping, product discovery, A/B testing, user research
- **Analytics:** Google Analytics, Mixpanel, Amplitude, Segment, Heap, Hotjar, FullStory, Pendo
- **Business tools:** Salesforce, HubSpot, Zendesk, Intercom, Stripe, Braintree, Twilio, SendGrid

Give CC an instruction like: "Expand `data/skills_taxonomy.csv` to at least 500 rows. One skill per row. Preserve existing entries. Use this list as a starting point and add common variations." Then have it de-duplicate.

### Step 3 — Re-extract skills on existing jobs (10 min)

Extraction runs at scrape time, so existing DB rows have the OLD thin extraction. Either:

**Option A (faster):** Do a fresh scrape. New jobs get the new taxonomy.

**Option B:** Write a one-time backfill script that loops existing jobs and re-runs `extract_skills(description)`:

```python
# scripts/backfill_skills.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jobspy.database import SessionLocal, Job
from jobspy.nlp.skill_extractor import extract_skills

with SessionLocal() as s:
    jobs = s.query(Job).filter(Job.description.isnot(None)).all()
    for i, job in enumerate(jobs, 1):
        result = extract_skills(job.description)
        job.required_skills = result["required"]
        job.preferred_skills = result["preferred"]
        if i % 50 == 0:
            s.commit(); print(f"  backfilled {i}/{len(jobs)}")
    s.commit()
print("done")
```

### Step 4 — Re-run diagnostic and verify spread (5 min)

Re-run `scripts/diagnose_match.py`. Target outcomes:
- Average required skills per job: ≥ 5
- Match scores span a meaningful range (e.g. 20%–85%, not all clustered under 20%)
- A perfect-fit job scores 70+
- A no-fit job scores under 30

### Step 5 — Update the README (5 min)

`README.md` currently says "curated 1000+ skill taxonomy." Change to match reality:

```markdown
- spaCy `PhraseMatcher` against a curated skill taxonomy (~500+ entries in `data/skills_taxonomy.csv`)
```

Overclaiming is a bigger demo risk than a lower number.

## Definition of done

- [ ] `scripts/diagnose_match.py` exists and shows intermediate values
- [ ] `data/skills_taxonomy.csv` has 500+ de-duplicated entries
- [ ] Existing jobs re-extracted via backfill or fresh scrape
- [ ] Match scores span 20%–85% across a 10-job sample
- [ ] README claim aligned with actual taxonomy size

## Demo talking point (~30 seconds)

> "The match score is a weighted skill-overlap — required matches count twice as heavily as preferred, at 70/30. We normalize aliases so 'NodeJS', 'node.js', and 'Node js' all collapse to the same canonical skill. Under every job, you see the skill gap — the missing required skills — so users know exactly what to learn next, not just that they're a 43% match with no explanation why."
