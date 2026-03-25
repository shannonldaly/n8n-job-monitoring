# Job Search Automation System 🔍

An end-to-end automated job search pipeline built to solve a personal pain point: monitoring dozens of target companies across multiple ATS platforms daily is tedious, inconsistent, and easy to miss. This system handles discovery, monitoring, and evaluation automatically.

## The Problem

Senior PM job searches are highly targeted. You're not applying to hundreds of roles — you're watching 20-40 specific companies for the right role to open. Doing that manually across Ashby, Greenhouse, Lever, and PeopleForce every day is unsustainable.

## What This System Does

Three scripts working together as a pipeline:

```
company_discovery.py  →  job_monitor.py  →  [job_evaluator.py]
   Find targets           Monitor ATS          Score & draft
```

**1. Company Discovery** (`company_discovery.py`)
Uses the Perplexity API to research and identify target companies matching specific criteria — funding stage, size, remote policy, AI integration, tech stack. Outputs a structured list of companies with relevant context for each.

**2. Job Monitor** (`job_monitor.py`)
Monitors target companies across Ashby and Greenhouse ATS platforms for new Senior/Staff/Principal PM roles. Tracks state between runs to detect new postings and removed roles. Alerts on changes.

**3. Job Evaluator** (separate repo)
Scores job postings 1-10 against career criteria using Claude and generates cover letters for high-scoring roles. See [job-evaluator](../job-evaluator) for details.

---

## Scripts

### `company_discovery.py`

Queries Perplexity's sonar-pro model to identify companies matching defined criteria.

**What it finds:**
- Funding stage (Series A-F)
- Employee count range
- Remote policy
- AI integration depth
- Tech stack signals
- Relevance to target background

**Usage:**
```bash
python3 company_discovery.py <perplexity_api_key>
# or
PERPLEXITY_API_KEY=your_key python3 company_discovery.py
```

**Output:** Timestamped text file with structured company profiles.

---

### `job_monitor.py`

Monitors multiple companies across two ATS platforms for PM role openings.

**ATS Coverage:**
- **Ashby** — direct API integration, structured JSON response
- **Greenhouse** — direct API integration, structured JSON response
- **Other ATS** — Claude web_fetch tool for scraping

**Role Filtering:**
```python
INCLUDE_ROLES = [
    "Senior Product Manager", "Senior PM",
    "Staff Product Manager", "Staff PM", 
    "Principal Product Manager", "Principal PM",
    "Platform Product Manager", "Platform PM",
    "Infrastructure Product Manager", "Infrastructure PM"
]
```

**Change Detection:**
Maintains a JSON state file between runs. On each run, compares current postings against previous state to identify:
- 🚨 New postings (not seen before)
- 📉 Removed postings (likely filled)
- 📊 Unchanged postings (still active)

**Usage:**
```bash
python3 job_monitor.py                    # Check all companies
python3 job_monitor.py --company n8n      # Check single company
python3 job_monitor.py --dry-run          # Test without saving state
```

**Rate limiting:** Exponential backoff on Claude API rate limit errors. 2-second delay between companies.

---

## Architecture

```
┌─────────────────────┐
│  company_discovery  │  ← Perplexity API
│  (research layer)   │
└──────────┬──────────┘
           │ target company list
           ▼
┌─────────────────────┐
│    job_monitor      │  ← Ashby API
│  (monitoring layer) │  ← Greenhouse API
│                     │  ← Claude web_fetch
└──────────┬──────────┘
           │ new postings → Google Sheets
           ▼
┌─────────────────────┐
│   job_evaluator     │  ← Claude API
│ (evaluation layer)  │  (separate repo)
└─────────────────────┘
           │
           ▼
    scored roles +
    cover letters
```

---

## Setup

### Dependencies
```
anthropic>=0.40.0
requests>=2.31.0
python-dotenv>=1.0.0
```

Install: `pip3 install -r requirements.txt`

### Environment Variables
Create a `.env` file:
```
ANTHROPIC_API_KEY=your-key-here
PERPLEXITY_API_KEY=your-key-here
```

### Automation
Run job_monitor.py on a daily cron:
```bash
0 9 * * * /path/to/run_monitor.sh
```

Note: On Mac, ensure your machine is awake during scheduled run windows. Consider dual-scheduling (9am + 10:30am) as a reliability backup.

---

## File Structure

```
job-search-automation/
├── company_discovery.py    # Company research via Perplexity
├── job_monitor.py          # ATS monitoring via Ashby/Greenhouse APIs
├── job_postings.json       # State file (auto-generated, not committed)
├── .env                    # API keys (not committed)
├── requirements.txt        # Python dependencies
└── README.md
```

---

## Honest Assessment

This works well for its intended purpose. Known limitations:

- **Mac sleep issue** — cron jobs don't run if the machine is asleep. Workaround: dual-schedule or use a cloud VM
- **ATS coverage** — Lever and PeopleForce require different integration approaches, not fully automated here
- **JavaScript-rendered pages** — some ATS platforms require JS rendering that requests can't handle; Claude web_fetch helps but isn't perfect
- **State file is local** — no cloud sync, state resets if you switch machines

Built for a user of 1. Not production hardened.

---

**Created:** January 2026  
**Built with:** Claude Code, Perplexity API  
**Stack:** Python, Anthropic SDK, Google Sheets API
