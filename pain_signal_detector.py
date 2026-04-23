import os
import json 
import requests
import time
from dotenv import load_dotenv
import anthropic
from prompt_registry import PROMPTS


print("Script started")
load_dotenv()
hubspot_api_key = os.getenv("HUBSPOT_API_KEY")


anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

        
if not hubspot_api_key:
    raise ValueError("Missing HUBSPOT_API_KEY in .env file")
if not anthropic_api_key:
    raise ValueError("Missing ANTHROPIC_API_KEY in .env file")


def fetch_news(company_name):
    """
    Mocked news fetcher.

    Returns realistic fake news items for a small set of known companies and
    an empty list for everything else.

    Shape: List[{"headline": str, "description": str}]
    """
    if not company_name:
        return []

    normalized = " ".join(str(company_name).strip().lower().split())

    mocked_by_company = {
        "hca": [
            {
                "headline": "HCA begins renegotiations after major payer threatens to exit network in two-state dispute",
                "description": (
                    "A large commercial insurer notified HCA it will terminate in-network participation for multiple markets "
                    "unless the parties can reach an agreement on rate increases and prior-authorization terms before the "
                    "current contract expires. HCA leaders signaled they are preparing contingency plans, including patient "
                    "communications and accelerated collections workflows, while talks continue."
                ),
            },
            {
                "headline": "HCA postpones enterprise EHR optimization wave amid staffing pressure and vendor price reset",
                "description": (
                    "Internal leaders have paused a planned EHR optimization rollout as several hospitals report higher-than-expected "
                    "clinical informatics vacancy rates and contract labor spend. The system is also revisiting software and support "
                    "renewals in response to a proposed pricing change from a key vendor, potentially shifting timelines for downstream "
                    "analytics and revenue-cycle initiatives."
                ),
            },
            {
                "headline": "HCA replaces division COO following margin compression and emergency department throughput issues",
                "description": (
                    "HCA announced a leadership change in a large division after persistent ED boarding and length-of-stay challenges "
                    "drove higher denials and patient leakage to competing sites. The interim leader is expected to prioritize "
                    "capacity management, labor productivity, and payer escalation processes over the next two quarters."
                ),
            },
        ],
        "virtua health": [
            {
                "headline": "Virtua Health faces contract termination notice from regional payer over disputed reimbursement methodology",
                "description": (
                    "Virtua Health confirmed it received a termination letter tied to disagreements over reimbursement benchmarks and "
                    "quality-based adjustments. Both sides say they are negotiating, but the payer has begun member outreach outlining "
                    "out-of-network scenarios. Virtua is evaluating service-line exposure and accelerating referral retention efforts."
                ),
            },
            {
                "headline": "Virtua Health explores ambulatory acquisition to offset inpatient softness and strengthen referral control",
                "description": (
                    "Executives are reportedly in discussions to acquire a multi-site physician group to improve referral capture in "
                    "high-growth suburbs. The move comes as inpatient volumes normalize and competitive systems expand outpatient "
                    "surgery capacity. A transaction would likely trigger IT integration work, credentialing cleanup, and contract "
                    "re-alignment across payers."
                ),
            },
            {
                "headline": "Virtua Health announces CISO departure after increased ransomware preparedness spending",
                "description": (
                    "Virtua shared that its CISO will step down later this quarter. The departure follows a year of elevated spend on "
                    "security tooling, tabletop exercises, and third-party risk reviews. Leadership said the interim team will focus on "
                    "identity governance and tightening vendor access while a national search is underway."
                ),
            },
        ],
        "providence": [
            {
                "headline": "Providence enters mediation with national payer after allegations of delayed claims adjudication",
                "description": (
                    "Providence and a national payer have moved to third-party mediation after months of dispute over claims timeliness "
                    "and disputed medical-necessity reviews. Providence leaders say denial overturn rates have worsened and cash "
                    "collections have become less predictable. The system is expanding its denial management team and re-prioritizing "
                    "automation projects to stabilize revenue cycle performance."
                ),
            },
            {
                "headline": "Providence restructures regional leadership, consolidating service lines to reduce cost-to-serve",
                "description": (
                    "Providence announced a regional leadership realignment that consolidates several service-line executives under a "
                    "single operating model. The change is intended to standardize operating procedures, reduce duplicative management "
                    "layers, and improve contracting leverage. Stakeholders expect short-term disruption across analytics, supply chain, "
                    "and care management workflows."
                ),
            },
            {
                "headline": "Providence reviews outpatient imaging joint venture after partner signals intent to exit",
                "description": (
                    "A joint venture partner has indicated it may exit an outpatient imaging arrangement, prompting Providence to review "
                    "ownership options and contingency staffing. Leaders are assessing referral patterns, equipment refresh needs, and "
                    "payer contract impacts before making a decision that could affect access and turnaround times across multiple markets."
                ),
            },
        ],
        "penn state health": [
            {
                "headline": "Penn State Health pauses planned clinic expansion as capital committee revisits project sequencing",
                "description": (
                    "Penn State Health has put a planned clinic expansion on hold while leadership reassesses capital priorities amid "
                    "construction cost inflation and shifting patient demand. The system is evaluating a revised timeline that would "
                    "delay new site openings and reallocate funds toward workforce retention and inpatient capacity constraints."
                ),
            },
            {
                "headline": "Penn State Health and major payer clash over new utilization controls, escalating to state-level review",
                "description": (
                    "Negotiations between Penn State Health and a major payer have escalated after the insurer proposed tighter utilization "
                    "controls for certain procedures and added documentation requirements. Provider leaders argue the changes would "
                    "increase administrative burden and delay care, while the payer cites rising costs. Both sides are weighing temporary "
                    "extensions as the dispute draws regulatory attention."
                ),
            },
            {
                "headline": "Penn State Health names interim revenue cycle leader following unexpected resignation",
                "description": (
                    "Penn State Health appointed an interim revenue cycle executive after the prior leader resigned unexpectedly. "
                    "The interim team is prioritizing denial prevention, improving charge capture controls, and reducing days in A/R. "
                    "Several RCM technology renewals are also under review as leaders evaluate automation and vendor consolidation options."
                ),
            },
        ],
    }

    for key in mocked_by_company:
        if key in normalized or normalized in key:
            return mocked_by_company[key]
    return []

def pass_to_claude(news_response_dictionary):
    """
    Sends a list of news articles to Claude for pain-signal detection.

    Expects `news_response_dictionary` to be a list of dictionaries like:
      [{"headline": "...", "description": "..."}, ...]

    Returns a Python dict parsed from Claude's JSON response.
    """
    articles = news_response_dictionary or []
    if not isinstance(articles, list):
        raise TypeError("pass_to_claude expected a list of article dictionaries")

    lines = ["Here are recent headlines and descriptions:"]
    for idx, article in enumerate(articles, start=1):
        if not isinstance(article, dict):
            continue
        headline = str(article.get("headline", "")).strip()
        description = str(article.get("description", "")).strip()
        lines.append(f"{idx}. Headline: {headline}\n   Description: {description}")

    lines.append("Return your analysis in the required JSON format.")
    user_message = "\n".join(lines)

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=PROMPTS["pain_signal_classifier"],
        messages=[{"role": "user", "content": user_message}],)

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        
        return json.loads(text)

    except json.JSONDecodeError:
        print(f"JSON parsing failed for response: {text[:100]}")
        return {
    "pain_signals_detected": [],
    "pain_signal_score": 0,
    "confidence": 0,
    "reasoning": "JSON parsing failed"
    }



def write_to_hubspot(object_id, pain_signal_properties_dictionary):
    #something like the below: 
    headers = {
    "Authorization": f"Bearer {hubspot_api_key}",
    "Content-Type": "application/json"
    }
    
    url = f"https://api.hubapi.com/crm/v3/objects/companies/{object_id}"
    body = {"properties": pain_signal_properties_dictionary}



    response = requests.patch(url, headers=headers, json=body)
    
    if response.status_code == 200:
        print(f"Successfully patched {object_id}")
        # success
    elif response.status_code == 404:
        print(f"404 error on {object_id}, moving on")
        # log and move on
    elif response.status_code == 429:
        # sleep and retry once
        time.sleep(60)
        response = requests.patch(url, headers=headers, json=body)
        print("Second 429 error")
    else:
        print(f"Unexpected error {response.status_code} for {object_id}")
        # log unexpected error
    

def fetch_all_records(object_type, headers, properties = None):
    """
    Fetch all records of a given type from HubSpot using pagination.
    
    Automatically handles pagination by following 'after' tokens until
    all records are retrieved. Implements graceful degradation - preserves
    partial data when errors occur during pagination.
    
    Args:
        object_type (str): The HubSpot object type (e.g., 'contacts', 'companies', 'deals')
        headers (dict): Authentication headers containing Bearer token
    
    Returns:
        list: All records from all pages. May be partial if errors occur during pagination.
              Each record is a dict containing HubSpot object properties.
        
    Raises:
        ValueError: If API credentials are invalid (401 error)
        
    Error Handling:
        - 401 (Invalid credentials): Raises ValueError immediately
        - 429 (Rate limit): Stops pagination, returns partial data
        - Timeout: Stops pagination, returns partial data
        - Network errors: Stops pagination, returns partial data
        - Empty results: Stops pagination, returns empty list
    """
    base_url = f"https://api.hubapi.com/crm/v3/objects/{object_type}"
    all_records = []
    next_token = None
    page_number = 1

    
    while True:
        if next_token:
            url = f"{base_url}?after={next_token}"
        else:
            url = base_url
        
        try:
            # Make request with timeout
            property_string = ",".join(properties) if properties else None

            params = {"properties": property_string}

            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            


            
            
            # Critical error - stop entire program (not just this loop)
            # Without valid credentials, no data fetching is possible
            if response.status_code == 401:
                raise ValueError("Invalid API credentials - check your API key")
            
            # Check for rate limit (429)
            if response.status_code == 429:
                print(f"⚠️  Rate limited on {object_type}. Stopping pagination.")
                break
            
            # Check for other bad status codes
            if response.status_code != 200:
                print(f"❌ API error {response.status_code} for {object_type}")
                break
            
            # Parse JSON
            data = response.json()

        
            
        except requests.exceptions.Timeout:
            print(f"⏱️  Timeout on {object_type} page {page_number}")
            break
            
        except requests.exceptions.RequestException as e:
            print(f"🌐 Network error fetching {object_type}: {e}")
            break
            
        except ValueError as e:
            print(f"📄 JSON parsing error for {object_type}: {e}")
            break
        
        # Safe dictionary access - returns [] if 'results' key missing
        # Prevents KeyError if HubSpot changes API response format
        results = data.get("results", [])

    
        if not results:
            print(f"⚠️  No results found for {object_type} page {page_number}")
            break
        
        # Add to collection
        all_records.extend(results)
        
        print(f"Fetching {object_type} - Page {page_number}: Got {len(results)} records. Total: {len(all_records)}")
        
        # Check for next page (safe access)
        # Check for pagination token - HubSpot includes 'after' only when more pages exist
        # If present: continue to next page. If missing: we've fetched all records
        paging = data.get("paging", {})
        next_info = paging.get("next", {})
        
        if next_info and "after" in next_info:
            next_token = next_info["after"]
            page_number += 1
        else:
            break
    
    return all_records

def load_hubspot_companies(headers):
    return fetch_all_records("companies", headers, properties = ['name','hs_object_id', 'numberofemployees', 'hs_revenue_range',
    'state', 'number_locations', 'medicare_enrollment_resource'])


def process_all_companies():
    headers = {
    "Authorization": f"Bearer {hubspot_api_key}",
    "Content-Type": "application/json"
    }

    companies = load_hubspot_companies(headers)
    print(f"Loaded {len(companies)} companies")

    records = []
    for company in companies:
        manual_review = {'bdr_review_needed': 'true'}
        props = company.get('properties', {})
        company_name = props.get('name')
        object_id = props.get('hs_object_id')
        news = fetch_news(company_name)
        if not news:
            write_to_hubspot(object_id, manual_review)
            continue
        claude_response = pass_to_claude(news)
        pain_signal_string = ",".join(claude_response.get('pain_signals_detected', []))
        props_dictionary = {'pain_signal_score': claude_response.get('pain_signal_score'), 'pain_signal_type': pain_signal_string}
        
        
        if claude_response.get('confidence') >= 0.7:
            write_to_hubspot(object_id, props_dictionary)
        else:
            write_to_hubspot(object_id, manual_review)

        records.append(claude_response)
        time.sleep(0.5)

if __name__ == "__main__":
    process_all_companies()





    
    #loads your companies, loops through them, calls the other three functions in sequence, and applies the confidence gate.
    


