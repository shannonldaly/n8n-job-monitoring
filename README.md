# n8n Job Monitoring Workflows 🤖

Automated job board monitoring using n8n, scraping multiple ATS platforms 
into a Google Sheet for daily evaluation.

**The problem:** Target companies use different ATS platforms (Ashby, 
Greenhouse, Lever, PeopleForce). Monitoring all of them manually is 
inefficient.

**What it does:**
- Scrapes job boards from 34 companies across 4 ATS platforms
- Deduplicates and normalizes postings
- Populates a Google Sheet for downstream evaluation by the job evaluator 
  script

## Coverage
- 18 companies via Ashby
- 15 companies via Greenhouse  
- 1 company via PeopleForce
- Lever (configured)

## Notes
Company names and target lists have been redacted from the workflow 
documentation for privacy. The workflow architecture and logic are intact.

**Status:** Running. Personal use only. Not monetized.
