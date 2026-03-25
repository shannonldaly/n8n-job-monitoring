#!/usr/bin/env python3
"""
Company Discovery Script using Perplexity API
Discovers companies matching specific job search criteria
"""

import requests
import json
from datetime import datetime
from getpass import getpass

def discover_companies(api_key: str) -> str:
    """Make API request to Perplexity to discover companies."""

    url = "https://api.perplexity.ai/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    discovery_prompt = """Find 15 US-based technology companies in TRAVEL TECHNOLOGY INFRASTRUCTURE:

SPECIFIC CATEGORIES (travel tech only):
- Travel APIs and platforms (flight, hotel, car rental data aggregation)
- Travel payment and fintech infrastructure
- Travel distribution and booking engine infrastructure (B2B platforms, not consumer booking sites)
- Hospitality technology platforms (property management APIs, guest experience infrastructure)
- Travel data and analytics platforms
- Corporate travel management platforms
- Travel loyalty and rewards infrastructure
- Aviation and airport technology platforms (software, not hardware)
- Ground transportation APIs (rideshare infrastructure, fleet management platforms)

REQUIREMENTS:
- Series A through F funding (include Series F only if still shipping innovative products)
- 40-2000 employees (for 1000-2000 range, only include if culture is fast-moving and startup-like)
- Remote-friendly for US employees
- Founded 2015+ OR significant recent innovation/pivot
- Modern tech stack (AWS/GCP/Azure)
- AI integration (core to product OR actively building AI features)

EXCLUDE:
- Consumer travel booking apps/sites (Expedia, Booking.com competitors)
- Traditional travel agencies
- Airlines themselves
- Hotel chains themselves
- Hardware companies
- Legacy GDS systems without modern innovation

For each company, provide in this exact format:

**Company Name**
- What they build: [1 sentence]
- Stage & Size: [e.g., Series B, 200 employees]
- Remote Policy: [Fully remote / Remote-friendly / Hybrid details]
- AI Angle: [How AI is core to their product OR what AI features they're building]
- Why Relevant: [Specific connection to target background: platform PM, infrastructure experience, enabling non-technical users]
- Website: [URL]

IDEAL CANDIDATE PROFILE - find companies that would value:
- Platform PM who built authorization infrastructure at Capital One (8 years)
- Strong marketing background (positioning, GTM, customer discovery)
- Comfortable bridging technical and non-technical users
- Experience enabling teams through platform infrastructure"""

    payload = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": "You are a research assistant helping identify technology companies for job opportunities. Provide accurate, current information with real company details."
            },
            {
                "role": "user",
                "content": discovery_prompt
            }
        ],
        "temperature": 0.2,
        "max_tokens": 8000
    }

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]

def save_results(content: str, timestamp: str) -> str:
    """Save results to a timestamped file."""
    filename = f"discovered_companies_{timestamp}.txt"

    header = f"""================================================================================
COMPANY DISCOVERY RESULTS
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Criteria: Series A-E, 50-1000 employees, AI/ML/Platform/Fintech infrastructure
Target: Platform PM opportunities
================================================================================

"""

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(header + content)

    return filename

def main():
    import sys
    import os

    print("\n" + "="*60)
    print("COMPANY DISCOVERY TOOL")
    print("Using Perplexity API to find matching companies")
    print("="*60 + "\n")

    # Get API key from environment variable or command line argument
    api_key = os.environ.get('PERPLEXITY_API_KEY') or (sys.argv[1] if len(sys.argv) > 1 else None)

    if not api_key:
        print("Error: No API key provided")
        print("Usage: python company_discovery.py <api_key>")
        print("   or: PERPLEXITY_API_KEY=your_key python company_discovery.py")
        return

    if not api_key.strip():
        print("Error: API key cannot be empty")
        return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    print("\nSearching for companies...")
    print("This may take a minute...\n")

    try:
        results = discover_companies(api_key)

        # Save to file
        filename = save_results(results, timestamp)

        print("="*60)
        print("DISCOVERY COMPLETE!")
        print(f"Results saved to: {filename}")
        print("="*60 + "\n")

        # Print results to console
        print(results)

        print("\n" + "="*60)
        print(f"Results also saved to: {filename}")
        print("="*60 + "\n")

    except requests.exceptions.HTTPError as e:
        print(f"\nAPI Error: {e}")
        if e.response.status_code == 401:
            print("Invalid API key. Please check your Perplexity API key.")
        elif e.response.status_code == 429:
            print("Rate limit exceeded. Please wait and try again.")
        else:
            print(f"Response: {e.response.text}")
    except requests.exceptions.Timeout:
        print("\nError: Request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        print(f"\nNetwork error: {e}")
    except KeyError as e:
        print(f"\nUnexpected response format: {e}")
    except Exception as e:
        print(f"\nUnexpected error: {e}")

if __name__ == "__main__":
    main()
