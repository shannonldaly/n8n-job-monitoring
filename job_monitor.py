#!/usr/bin/env python3
"""
Job Evaluator Agent - Score job postings against Shannon's career criteria
Reads from Google Sheets, fetches job content, scores fit using Claude
"""

import json
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

# Load .env file from script directory
load_dotenv(Path(__file__).parent / ".env")

import anthropic
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# =============================================================================
# CONFIGURATION
# =============================================================================

CREDENTIALS_FILE = Path(__file__).parent / "google_credentials.json"
CRITERIA_FILE = Path(__file__).parent / "career-context-skill.md"
WRITING_STYLE_FILE = Path(__file__).parent / "writing-style-skill.md"
COVER_LETTERS_DIR = Path(__file__).parent / "cover_letters"
SPREADSHEET_ID = "1k2v6UZBlSsbz_SIUXlkprFCvybijSwFgYQzNVCIABdk"
COVER_LETTER_THRESHOLD = 7  # Generate cover letters for scores >= this

# Column mappings (0-indexed) - matches your sheet structure
COLUMNS = {
    "job_id": 0,            # A: job_id
    "company": 1,           # B: company
    "title": 2,             # C: title
    "url": 3,               # D: url
    "status": 4,            # E: status
    "date_added": 5,        # F: date_added
    "application_status": 6, # G: application status
    "score": 7,             # H: score (1-10)
    "notes": 8,             # I: notes (rationale)
}

MODEL_NAME = "claude-sonnet-4-20250514"
MAX_TOKENS = 2048


# =============================================================================
# GOOGLE SHEETS CONNECTION
# =============================================================================

def get_sheets_service(credentials_path: Path):
    """Create authenticated Google Sheets service."""
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {credentials_path}\n"
            "Please save your service account JSON to this location."
        )

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_file(
        str(credentials_path), scopes=scopes
    )

    service = build("sheets", "v4", credentials=credentials)
    return service


def read_sheet_data(service, spreadsheet_id: str, range_name: str = "Sheet1") -> List[List]:
    """Read all data from a sheet."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        return result.get("values", [])
    except HttpError as e:
        raise RuntimeError(f"Failed to read sheet data: {e}")


def batch_update_row(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_number: int,
    updates: dict
) -> None:
    """Update multiple cells in a row."""
    data = []
    for col_name, value in updates.items():
        col_index = COLUMNS.get(col_name)
        if col_index is None:
            continue
        col_letter = chr(ord('A') + col_index)
        range_name = f"{sheet_name}!{col_letter}{row_number}"
        data.append({
            "range": range_name,
            "values": [[value]]
        })

    if not data:
        return

    try:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": data
            }
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"Failed to batch update row {row_number}: {e}")


# =============================================================================
# JOB CONTENT FETCHING
# =============================================================================

def fetch_job_content(url: str) -> Tuple[str, Optional[str]]:
    """
    Fetch job posting content from URL.
    Returns: (content, error_message)
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text, None
    except requests.RequestException as e:
        return "", f"Failed to fetch URL: {str(e)}"


# =============================================================================
# CLAUDE SCORING
# =============================================================================

def create_scoring_prompt(job_content: str, criteria: str, company: str, title: str) -> str:
    """Create the prompt for Claude to score a job posting."""
    return f"""You are evaluating a job posting for fit against Shannon Daly's background and job search criteria.

## SHANNON'S CAREER CONTEXT AND CRITERIA
{criteria}

## SCORING GUIDE (Use Shannon's criteria from above)
- 9-10: Direct domain match (authorization/payments/observability infrastructure) + sweet spot factors (platform PM, enables non-technical users, 0-to-1, 50-300 employees, coaching culture, low ego)
- 7-8: Strong transferable experience + good company fit (workflow automation, API-first, developer tools that don't require coding, good culture signals)
- 5-6: Decent fit but missing key elements (right level but wrong domain, or right domain but concerning signals like large company bureaucracy)
- 3-4: Stretch role or company concerns (requires coding, slow enterprise sales, >1500 employees, vague PM role)
- 1-2: Hard exclusions (traditional banks, insurance, defense, .NET shops, <$160K, Product Owner roles, consumer-only, requires developer background)

## JOB POSTING
Company: {company}
Title: {title}

Content:
{job_content[:20000]}

## INSTRUCTIONS
1. Analyze how well this role matches Shannon's background, skills, and preferences from the criteria above
2. Consider: domain fit, company size/stage, remote-friendliness, platform vs feature PM, technical requirements, culture signals
3. Check against hard exclusions first
4. Provide a score from 1-10 based on the scoring guide
5. Write a brief rationale (1-2 sentences) explaining the key factors - be specific about what matched or didn't

## OUTPUT FORMAT
Return ONLY valid JSON in this exact format:
{{"score": <number 1-10>, "rationale": "<1-2 sentence explanation with specific reasons>"}}
"""


def score_job_with_claude(
    client: anthropic.Anthropic,
    job_content: str,
    criteria: str,
    company: str,
    title: str
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Use Claude to score a job posting.
    Returns: (score, rationale, error_message)
    """
    try:
        prompt = create_scoring_prompt(job_content, criteria, company, title)

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract text from response
        response_text = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                response_text += block.text

        # Parse JSON response
        json_match = re.search(r'\{[^}]+\}', response_text)
        if not json_match:
            return None, None, "Could not find JSON in Claude's response"

        data = json.loads(json_match.group())
        score = int(data.get("score", 0))
        rationale = data.get("rationale", "No rationale provided")

        if not 1 <= score <= 10:
            return None, None, f"Invalid score: {score}"

        return score, rationale, None

    except json.JSONDecodeError as e:
        return None, None, f"Invalid JSON response: {e}"
    except anthropic.RateLimitError:
        return None, None, "Rate limit hit - wait and retry"
    except Exception as e:
        return None, None, f"Claude API error: {str(e)}"


# =============================================================================
# COVER LETTER GENERATION
# =============================================================================

def sanitize_filename(text: str) -> str:
    """Convert text to a safe filename."""
    # Replace spaces and special chars with underscores
    safe = re.sub(r'[^\w\s-]', '', text)
    safe = re.sub(r'[\s-]+', '_', safe)
    return safe.strip('_')


def create_cover_letter_prompt(
    job_content: str,
    criteria: str,
    writing_style: str,
    company: str,
    title: str
) -> str:
    """Create the prompt for Claude to generate a cover letter."""
    return f"""You are writing a cover letter for Shannon Daly applying to a specific job.

## SHANNON'S BACKGROUND AND EXPERIENCE
{criteria}

## SHANNON'S WRITING STYLE GUIDELINES
{writing_style}

## JOB POSTING
Company: {company}
Title: {title}

Content:
{job_content[:15000]}

## INSTRUCTIONS
Write a cover letter for Shannon applying to this role. Follow these rules strictly:

1. **Length**: 250-300 words maximum. No exceptions.
2. **Structure**:
   - Opening: Why this company + role specifically (2-3 sentences)
   - Relevant Experience: 2-3 concrete examples with metrics from Shannon's background
   - Why She Fits: Connect her superpowers to their needs
   - Closing: Direct ask + enthusiasm (1-2 sentences)

3. **Style Rules** (from writing style guide):
   - Direct, no corporate speak
   - Lead with impact and metrics (30M+ transactions/day, 152 hours saved, etc.)
   - Use active voice and action verbs
   - NO em dashes (use periods, commas, or parentheses instead)
   - NO hedging words (should, might, could, probably)
   - NO AI slop phrases (delve, foster, leverage, synergy, etc.)
   - Be confident but not arrogant
   - Show personality without being unprofessional

4. **Content**:
   - Reference specific things from the job posting
   - Connect Shannon's Capital One platform experience to their needs
   - Highlight democratization/enabling non-technical users if relevant
   - Mention relevant metrics from her background

## OUTPUT
Write ONLY the cover letter text. No preamble, no "Here's a cover letter", just the letter itself.
Start with a greeting and end with her name.
"""


def generate_cover_letter(
    client: anthropic.Anthropic,
    job_content: str,
    criteria: str,
    writing_style: str,
    company: str,
    title: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Generate a cover letter using Claude.
    Returns: (cover_letter_text, error_message)
    """
    try:
        prompt = create_cover_letter_prompt(
            job_content, criteria, writing_style, company, title
        )

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract text from response
        cover_letter = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                cover_letter += block.text

        if not cover_letter.strip():
            return None, "Empty response from Claude"

        return cover_letter.strip(), None

    except anthropic.RateLimitError:
        return None, "Rate limit hit - wait and retry"
    except Exception as e:
        return None, f"Claude API error: {str(e)}"


def save_cover_letter(
    cover_letter: str,
    company: str,
    title: str,
    output_dir: Path
) -> Path:
    """Save cover letter to a text file."""
    output_dir.mkdir(exist_ok=True)

    filename = f"{sanitize_filename(company)}_{sanitize_filename(title)}.txt"
    filepath = output_dir / filename

    filepath.write_text(cover_letter)
    return filepath


# =============================================================================
# MAIN EVALUATION FLOW
# =============================================================================

def load_criteria(criteria_path: Path) -> str:
    """Load scoring criteria from file."""
    if not criteria_path.exists():
        raise FileNotFoundError(
            f"Criteria file not found: {criteria_path}\n"
            "Please create this file with your background and job preferences."
        )
    return criteria_path.read_text()


def find_jobs_to_evaluate(rows: List[List], header_row: int = 0) -> List[Tuple[int, dict]]:
    """
    Find rows where status='new' and score is empty.
    Returns: List of (row_number, row_data_dict)
    """
    jobs = []
    max_col = max(COLUMNS.values())

    for i, row in enumerate(rows):
        if i <= header_row:
            continue

        # Pad row to ensure we can access all columns
        while len(row) <= max_col:
            row.append("")

        status = row[COLUMNS["status"]].strip().lower()
        score = row[COLUMNS["score"]].strip()

        # Check criteria: status is "new" and score is empty
        if status == "new" and not score:
            job_data = {
                "url": row[COLUMNS["url"]],
                "company": row[COLUMNS["company"]],
                "title": row[COLUMNS["title"]],
            }
            # Row numbers in Sheets are 1-indexed
            jobs.append((i + 1, job_data))

    return jobs


def evaluate_jobs(
    spreadsheet_id: str = SPREADSHEET_ID,
    sheet_name: str = "Sheet1",
    dry_run: bool = False
) -> None:
    """Main function to evaluate all pending jobs."""

    print("\n" + "=" * 60)
    print("JOB EVALUATOR AGENT")
    print("=" * 60)

    # Load criteria
    print("\nLoading evaluation criteria...")
    try:
        criteria = load_criteria(CRITERIA_FILE)
        print(f"  Loaded from {CRITERIA_FILE.name}")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        return

    # Load writing style
    print("\nLoading writing style...")
    try:
        writing_style = load_criteria(WRITING_STYLE_FILE)
        print(f"  Loaded from {WRITING_STYLE_FILE.name}")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        return

    # Connect to Google Sheets
    print("\nConnecting to Google Sheets...")
    try:
        service = get_sheets_service(CREDENTIALS_FILE)
        print("  Connected successfully")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        return
    except Exception as e:
        print(f"  ERROR: Failed to connect: {e}")
        return

    # Read sheet data
    print(f"\nReading data from '{sheet_name}'...")
    try:
        rows = read_sheet_data(service, spreadsheet_id, sheet_name)
        print(f"  Found {len(rows)} total rows")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Find jobs to evaluate
    jobs_to_evaluate = find_jobs_to_evaluate(rows)
    print(f"\nFound {len(jobs_to_evaluate)} jobs to evaluate (status='new', score empty)")

    if not jobs_to_evaluate:
        print("\nNo jobs to evaluate. Done!")
        return

    # Initialize Claude client
    print("\nInitializing Claude client...")
    client = anthropic.Anthropic()

    # Process each job
    evaluated = 0
    errors = 0
    cover_letters = 0

    for row_num, job_data in jobs_to_evaluate:
        url = job_data["url"]
        company = job_data["company"]
        title = job_data["title"]

        print(f"\n{'─' * 60}")
        print(f"[Row {row_num}] {company} - {title}")
        print(f"  URL: {url[:60]}..." if len(url) > 60 else f"  URL: {url}")

        if not url:
            print("  SKIP: No URL provided")
            errors += 1
            continue

        # Fetch job content
        print("  Fetching job content...")
        content, fetch_error = fetch_job_content(url)
        if fetch_error:
            print(f"  ERROR: {fetch_error}")
            errors += 1
            continue

        if len(content) < 100:
            print(f"  ERROR: Content too short ({len(content)} chars) - may need JavaScript rendering")
            errors += 1
            continue

        # Score with Claude
        print("  Scoring with Claude...")
        score, rationale, score_error = score_job_with_claude(
            client, content, criteria, company, title
        )

        if score_error:
            print(f"  ERROR: {score_error}")
            errors += 1
            continue

        # Display results
        score_emoji = "🔥" if score >= 8 else "✓" if score >= 5 else "⚠️"
        print(f"  {score_emoji} Score: {score}/10")
        print(f"  Rationale: {rationale}")

        # Update spreadsheet
        if not dry_run:
            print("  Writing to sheet...")
            try:
                batch_update_row(
                    service,
                    spreadsheet_id,
                    sheet_name,
                    row_num,
                    {"score": str(score), "notes": rationale}
                )
                print("  Done!")
                evaluated += 1
            except Exception as e:
                print(f"  ERROR updating sheet: {e}")
                errors += 1
                continue
        else:
            print("  [DRY RUN] Would update spreadsheet")
            evaluated += 1

        # Generate cover letter for high-scoring jobs
        if score >= COVER_LETTER_THRESHOLD:
            print(f"  Generating cover letter (score >= {COVER_LETTER_THRESHOLD})...")
            cover_letter, cl_error = generate_cover_letter(
                client, content, criteria, writing_style, company, title
            )

            if cl_error:
                print(f"  ERROR generating cover letter: {cl_error}")
            elif not dry_run:
                filepath = save_cover_letter(
                    cover_letter, company, title, COVER_LETTERS_DIR
                )
                print(f"  Saved: {filepath.name}")
                cover_letters += 1
            else:
                print("  [DRY RUN] Would save cover letter")
                cover_letters += 1

        # Small delay to avoid rate limits
        time.sleep(1)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Jobs evaluated: {evaluated}")
    print(f"Cover letters generated: {cover_letters}")
    print(f"Errors: {errors}")
    if dry_run:
        print("(Dry run - no changes written to sheet)")
    if cover_letters > 0 and not dry_run:
        print(f"Cover letters saved to: {COVER_LETTERS_DIR}")
    print()


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate job postings and score fit using Claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 job_evaluator.py                    # Evaluate all new jobs
  python3 job_evaluator.py --dry-run          # Test without writing to sheet
  python3 job_evaluator.py --sheet "Jobs"     # Use different sheet name
        """
    )
    parser.add_argument(
        "--sheet",
        default="Sheet1",
        help="Sheet name within the spreadsheet (default: Sheet1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate jobs but don't write to spreadsheet"
    )

    args = parser.parse_args()

    evaluate_jobs(
        sheet_name=args.sheet,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
