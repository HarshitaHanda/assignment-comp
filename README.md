# Composio AI Product Ops — 100 App Research System

A reproducible evidence-first research pipeline and interactive case study for the Composio AI Product Ops Intern take-home assignment.

**Live case study:** https://assignment-comp.vercel.app/  
**Repository:** https://github.com/HarshitaHanda/assignment-comp

## Final research snapshot

The committed dataset contains research across all 100 requested apps.

- **100 / 100** apps researched
- **64** classified as buildable now
- **20** classified as partially buildable
- **16** remain buildability-unknown
- **76 / 100** developer-access models resolved
- **35** rows explicitly flagged for human review
- **60** apps matched to an existing Composio toolkit
- **0.74** average confidence

The goal is not to force every row into a confident answer. When official evidence is incomplete, the system leaves the field unresolved and surfaces it for review.

---

## What I built

The assignment is treated as a research-system problem rather than manually filling 100 rows.

The pipeline has four stages:

### 1. Discover

Start from the official URL provided for each app and retrieve likely developer, API, authentication, webhook and MCP documentation.

Primary tooling:

- `requests`
- BeautifulSoup
- official-source crawling only

### 2. Classify

A deterministic rules engine extracts explicit signals for:

- OAuth 2.0
- API keys
- bearer tokens
- JWT
- REST
- GraphQL
- webhooks
- public APIs
- developer-access models
- access gates
- MCP references

The classifier also recognizes procedural evidence such as:

- generating an API key
- creating a personal access token
- registering an OAuth application
- creating a private/internal integration
- provisioning credentials through a developer dashboard

Clear cases are classified automatically.

Missing or contradictory evidence remains `unknown`.

### 3. Escalate

Ambiguous rows can optionally go through an LLM fallback cascade:

```text
Bazaar → Groq → Gemini
```

Only unresolved cases reach the fallback layer.

The models receive compact excerpts from the same retrieved official documentation rather than unrestricted external context.

The LLM is used to fill evidence gaps — not to overwrite stronger deterministic findings.

### 4. Verify

A separate Playwright / Chromium pass renders a sample of official evidence pages and independently checks the first-pass classifications.

The verification layer records:

- browser evidence coverage
- field-level agreement
- inconclusive findings
- contradictions / corrections
- optional human checks

This is intentionally separate from the first-pass crawler.

---

## Architecture

```text
data/apps.json
      |
      v
official documentation crawler
(requests + BeautifulSoup)
      |
      v
deterministic evidence extraction
(auth / API / access / MCP)
      |
      +------> ambiguous only
      |          |
      |          v
      |   Bazaar → Groq → Gemini
      |
      +------> Composio SDK catalog lookup
      |
      v
data/results.json
      |
      +------> summary generation
      |
      +------> Playwright verification
      |
      v
data/summary.json
data/verification.json
      |
      v
interactive static case-study UI
```

---

## Why this design

This is an integration-research problem before it is an LLM problem.

Developer documentation often contains explicit signals such as:

- OAuth flows
- API-key creation
- REST / GraphQL references
- webhook documentation
- developer-console instructions
- MCP references

Those do not need an LLM to reinterpret them.

Using deterministic extraction first gives the pipeline several advantages:

- lower cost
- easier auditing
- traceable evidence
- reproducible classifications
- fewer unsupported guesses

The LLM layer is intentionally an escalation mechanism rather than the default research engine.

---

## How Composio is used

The Composio SDK is used during research enrichment.

The pipeline queries the live toolkit catalog with:

```python
composio.toolkits.list()
```

Each researched app is checked against the catalog and the result is stored with the row.

This adds a Product Ops dimension to the analysis:

> Is this requested integration already represented in Composio's toolkit catalog, or does it potentially represent a product gap?

The current dataset matches **60 of the 100 requested apps** to a Composio toolkit.

---

## Research methodology

Each app produces a structured row containing:

- app name
- category
- description
- authentication methods
- developer-access model
- programmable API surface
- MCP status
- buildability
- primary blocker
- confidence
- human-review flag
- classification method
- Composio toolkit match
- evidence URLs

Every evidence-backed classification links back to the official source used by the pipeline.

---

## Developer access classification

The access model is intentionally stricter than simply detecting whether an API exists.

Possible values include:

```text
self-serve
self-serve-free
self-serve-trial
self-serve-paid
admin-gated
partner-gated
contact-sales
unknown
```

`self-serve` is used when official documentation shows that a developer can provision credentials or register an application without an explicit sales / partner / admin approval requirement.

`unknown` means the retrieved official documentation did not provide enough evidence to classify developer access confidently.

---

## Final access distribution

```text
self-serve        42
unknown           24
self-serve-trial  19
self-serve-free   12
self-serve-paid    3
```

The system resolves developer-access status for **76% of the requested apps** while leaving the remaining cases visible rather than guessing.

---

## Final buildability distribution

```text
yes      64
partial  20
unknown  16
```

A row is considered buildable when the system finds:

1. a documented programmable surface,
2. a realistic authentication method,
3. developer access that is not explicitly gated.

---

## Local setup

### 1. Clone

```bash
git clone https://github.com/HarshitaHanda/assignment-comp.git
cd assignment-comp
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

For optional LLM fallbacks:

```bash
pip install -r requirements-llm.txt
```

---

## Environment configuration

Copy:

```text
.env.example
```

to:

```text
.env
```

Example:

```env
COMPOSIO_API_KEY=your_composio_key

USE_LLM_FALLBACK=false

RESEARCH_MAX_PAGES=8
RESEARCH_TIMEOUT_SECONDS=15
RULE_CONFIDENCE_THRESHOLD=0.72
```

`.env` is ignored by Git and should never be committed.

### Optional LLM cascade

```env
USE_LLM_FALLBACK=true

LLM_FALLBACK_ORDER=bazaar,groq,gemini

BAZAARLINK_API_KEY=your_key
BAZAARLINK_MODEL=auto:free

GROQ_API_KEY=your_key
GROQ_MODEL=openai/gpt-oss-20b

GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.8-flash
```

If a provider fails, is rate-limited, or returns an insufficient result, the pipeline proceeds to the next provider.

Provider attempts are retained in `fallback_attempts`.

---

## Run the research pipeline

Test a few apps first:

```bash
python -m agent.run_pipeline --limit 3 --skip-verify
```

Run the research set:

```bash
python -m agent.run_pipeline
```

Resume from a particular app:

```bash
python -m agent.run_pipeline --start 41
```

The pipeline checkpoints `data/results.json` after every app so completed research is not lost if a later request fails.

---

## Generate summary

```bash
python -m agent.summary
```

This produces:

```text
data/summary.json
```

which powers the headline metrics and visualizations in the frontend.

---

## Verification

Run a browser-rendered spot check:

```bash
python -m agent.verify --sample-size 5
```

The verification pass uses Playwright / Chromium rather than the first-pass `requests` crawler.

The frontend distinguishes:

- **Browser agreement** — field-level agreement between the two automated passes
- **Human validated accuracy** — only shown when actual manual checks exist
- **Corrections** — disagreements retained instead of silently hidden

The verification sample is a spot check, not a statistical accuracy estimate.

---

## Human checks

Manual validation can be recorded in:

```text
data/human_checks.json
```

Example:

```json
{
  "checks": [
    {
      "app_id": 1,
      "app_name": "Salesforce",
      "claims_checked": 6,
      "claims_correct_after_verification": 6,
      "notes": "Checked auth, API surface, access, MCP, buildability and blocker.",
      "evidence": [
        "https://developer.salesforce.com/"
      ]
    }
  ]
}
```

Human-validated accuracy is not shown unless real manual checks exist.

---

## Result schema

Example researched row:

```json
{
  "id": 1,
  "name": "Example",
  "category": "CRM and Sales",
  "description": "Official-page description where available",
  "auth_methods": [
    "OAuth2"
  ],
  "access_model": "self-serve",
  "api_surface": "REST, Webhooks",
  "mcp_status": "none-found",
  "buildability": "yes",
  "main_blocker": null,
  "confidence": 0.88,
  "needs_human_review": false,
  "classification_method": "deterministic-rules",
  "composio_toolkit": {
    "name": "Example",
    "slug": "example"
  },
  "evidence": [
    {
      "url": "https://official.example.dev/docs/auth",
      "supports": "Authentication evidence: OAuth2"
    }
  ]
}
```

---

## Serve the case study locally

```bash
python -m http.server 8000
```

Open:

```text
http://localhost:8000
```

Do not open `index.html` directly through `file://` because the frontend fetches the generated JSON files.

---

## Deploy on Vercel

This repository deploys as a static site.

Use:

```text
Framework preset: Other
Build command:    leave empty
Output directory: leave empty
Root directory:   repository root
```

No production API keys are required.

Research runs locally and the generated JSON files are committed with the case study.

---

## Repository structure

```text
.
├── agent/
│   ├── browser_verifier.py
│   ├── composio_enrichment.py
│   ├── crawler.py
│   ├── llm.py
│   ├── models.py
│   ├── research.py
│   ├── rule_extractor.py
│   ├── run_pipeline.py
│   ├── summary.py
│   └── verify.py
│
├── data/
│   ├── apps.json
│   ├── human_checks.json
│   ├── results.json
│   ├── summary.json
│   └── verification.json
│
├── index.html
├── app.js
├── styles.css
├── requirements.txt
├── requirements-llm.txt
├── vercel.json
├── .env.example
├── .gitignore
└── README.md
```

---

## Limitations

- Rule-based extraction can miss unusual contextual wording.
- Some sites rely heavily on JavaScript and are difficult to retrieve through the first-pass crawler.
- Some developer-access requirements are only visible after login.
- Pricing, account entitlements and partner requirements can change.
- `none-found` for MCP means no official reference was found in the retrieved pages; it does not prove that an MCP implementation does not exist elsewhere.
- Browser verification is a sampled spot check rather than full coverage of all 100 apps.
- Ambiguous cases are intentionally retained for human review.

---

## Author

**Harshita Handa**

Composio AI Product Ops Intern take-home
