import os
import json 
import requests
import time
from datetime import datetime, timezone
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

client = anthropic.Anthropic(api_key=anthropic_api_key)

# Patch helper: write calculated fields back to HubSpot
def patch_company_to_hubspot(company_id, properties_to_patch):
    # Build the HubSpot PATCH endpoint URL for this company id
    url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
    # Build auth headers using the HubSpot private app token
    headers = {"Authorization": f"Bearer {hubspot_api_key}", "Content-Type": "application/json"}
    # HubSpot expects properties under a top-level "properties" key
    payload = {"properties": properties_to_patch}
    # Make the PATCH request to HubSpot
    return requests.patch(url, headers=headers, json=payload, timeout=10)

# Logging helper: append a decision record to a local JSONL file
def log_bdr_decision(decision_record, log_path="bdr_decisions.json"):
    # Add a timestamp so each decision is auditable
    decision_record["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    # Append each decision as a single JSON line for simple streaming logs
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision_record) + "\n")

#1. ICP Classification - is this company a good fit at all?
#2. Intent Detection - are there signals they're actively looking to buy?
#3. Response Generation - if fit and intent are both strong, what should the BDR say?
#4. Confidence Gate and Human Handoff - if any stage is below threshold, route to human queue
#5. Orchestrate - loop through companies and apply functions in right order 


def classify_icp_fit(company_properties):
    #claude response - include prompt that asks claude to evaluate icp tier, confidence, and reasoning bassd on employee count, revenue range, state, medicare enrollment, employees per location fields. Ask for it in JSON. 
    #extract text from response
    #store result = json.load(text)
    props = company_properties or {}
    if not isinstance(props, dict):
        raise TypeError("classify_icp_fit expected a dictionary of company properties")

    numberofemployees = props.get("numberofemployees")
    hs_revenue_range = props.get("hs_revenue_range")
    state = props.get("state")
    medicare_enrollment_resource = props.get("medicare_enrollment_resource")
    number_locations = props.get("number_locations")

    lines = ["Here are the company properties from HubSpot:"]
    lines.append(f"1. numberofemployees: {numberofemployees}")
    lines.append(f"2. hs_revenue_range: {hs_revenue_range}")
    lines.append(f"3. state: {state}")
    lines.append(f"4. medicare_enrollment_resource: {medicare_enrollment_resource}")
    lines.append(f"5. number_locations: {number_locations}")
    lines.append("Return your analysis in the required JSON format.")
    user_message = "\n".join(lines)

    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=PROMPTS["classify_icp_fit"],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIStatusError as e:
        status = getattr(e, "status_code", None)
        if status == 529:
            print("Anthropic overloaded (529). Sleeping 30s then retrying ICP once...")
            time.sleep(30)
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                system=PROMPTS["classify_icp_fit"],
                messages=[{"role": "user", "content": user_message}],
            )
        else:
            raise

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
    "icp_tier": 0,
    "confidence": 0,
    "reasoning": "JSON parsing failed"
    }


def detect_intent(company_name, pain_signal_data):
    #claude -- for properties of company_name found in results from classify_icp_fit, evaluate intent for any above certain ICP gate using pain_signal_type property. Return intent_tier, intent_detected, intent_type, confidence, reasoning.
    #get text, store result = json.loads(text)
    if not company_name:
        raise ValueError("detect_intent expected a company_name")

    data = pain_signal_data or {}
    if not isinstance(data, dict):
        raise TypeError("detect_intent expected pain_signal_data to be a dictionary")

    pain_signal_type = data.get("pain_signal_type")
    pain_signal_score = data.get("pain_signal_score")

    lines = [f"Company name: {company_name}"]
    lines.append("Here are the pain signal attributes from HubSpot:")
    lines.append(f"1. pain_signal_type: {pain_signal_type}")
    lines.append(f"2. pain_signal_score: {pain_signal_score}")
    lines.append("Return your analysis in the required JSON format.")
    user_message = "\n".join(lines)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=PROMPTS["detect_intent"],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIStatusError as e:
        status = getattr(e, "status_code", None)
        if status == 529:
            print("Anthropic overloaded (529). Sleeping 30s then retrying intent once...")
            time.sleep(30)
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                system=PROMPTS["detect_intent"],
                messages=[{"role": "user", "content": user_message}],
            )
        else:
            raise

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
            "intent_detected": False,
            "intent_type": "none",
            "confidence": 0,
            "reasoning": "JSON parsing failed",
        }



def generate_outreach(company_properties, icp_result, intent_result):
    #prompt: for those who pass ICP gating, use company properties, icp_result, intent_result to write an outreach message given xyz pitch / value prop understanding and context on how we reach out to inbounds
    #
    # Validate company properties input (HubSpot company fields)
    props = company_properties or {}
    if not isinstance(props, dict):
        raise TypeError("generate_outreach expected company_properties to be a dictionary")

    # Validate ICP classification result input (output of classify_icp_fit)
    icp = icp_result or {}
    if not isinstance(icp, dict):
        raise TypeError("generate_outreach expected icp_result to be a dictionary")

    # Validate intent detection result input (output of detect_intent)
    intent = intent_result or {}
    if not isinstance(intent, dict):
        raise TypeError("generate_outreach expected intent_result to be a dictionary")

    # Pull company-specific values we want to condition the outreach on
    company_name = props.get("name")
    state = props.get("state")
    numberofemployees = props.get("numberofemployees")

    # Pull ICP values for hook/social proof personalization
    icp_tier = icp.get("icp_tier")
    icp_reasoning = icp.get("reasoning")

    # Pull intent values to tailor CTA (only when intent exists)
    intent_detected = intent.get("intent_detected")
    intent_type = intent.get("intent_type")

    # Build the user message dynamically from the passed-in data
    lines = ["Write an outreach message using the data below:"]
    lines.append(f"Company name: {company_name}")
    lines.append(f"State: {state}")
    lines.append(f"Number of employees: {numberofemployees}")
    lines.append(f"ICP tier: {icp_tier}")
    lines.append(f"ICP reasoning: {icp_reasoning}")
    lines.append(f"Intent detected: {intent_detected}")
    lines.append(f"Intent type: {intent_type}")
    user_message = "\n".join(lines)

    # Call Claude with the outreach system prompt and the company-specific user message
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=300,
            system=PROMPTS["generate_outreach"],
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        # If the Claude call fails for any reason, return None per spec
        print(f"Claude call failed in generate_outreach: {e}")
        return None

    # Extract the raw text response (no JSON parsing for outreach generation)
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()

    # Return the message text (or None if it came back empty)
    return text or None

def run_bdr_pipeline(company_properties):
    # Ensure we have a dictionary of HubSpot company properties
    props = company_properties or {}
    if not isinstance(props, dict):
        raise TypeError("run_bdr_pipeline expected company_properties to be a dictionary")

    # Pull required inputs from HubSpot properties
    company_name = props.get("name")
    pain_signal_score = props.get("pain_signal_score")
    pain_signal_type = props.get("pain_signal_type")
    object_id = props.get("hs_object_id")

    # Build the pain signal payload used by detect_intent
    pain_signal_data = {"pain_signal_type": pain_signal_type, "pain_signal_score": pain_signal_score}

    # Run ICP classification first
    icp_result = classify_icp_fit(props)

    # Pull ICP decision fields for gating
    icp_confidence = icp_result.get("confidence", 0)
    icp_tier = icp_result.get("icp_tier", 3)

    # Compute whether this company passes the ICP gate
    passes_icp_gate = (icp_confidence >= 0.7) and (icp_tier <= 2)
    print(f"ICP result: {icp_result}")
    print(f"Passes ICP gate: {passes_icp_gate}")

    # Start a decision record for audit logging (write one record per company)
    decision_record = {
        "hs_object_id": object_id,
        "company_name": company_name,
        "pain_signal_type": pain_signal_type,
        "pain_signal_score": pain_signal_score,
        "icp_result": icp_result,
        "passes_icp_gate": passes_icp_gate,
    }

    # Always patch ICP outputs back to HubSpot so the decision is visible in CRM
    properties_to_patch = {
        "icp_tier": icp_result.get("icp_tier"),
        "icp_confidence": icp_result.get("confidence"),
        "icp_reasoning": icp_result.get("reasoning"),
    }

    # If the company fails the ICP gate, mark it for human review and stop
    if not passes_icp_gate:
        # Set the human-handoff flag for BDR review
        properties_to_patch["bdr_review_needed"] = True
        # Record the branch decision for logging
        decision_record["branch"] = "fail_icp_gate"

        # Patch HubSpot if we have an object id
        if object_id:
            try:
                patch_company_to_hubspot(object_id, properties_to_patch)
            except Exception as e:
                print(f"HubSpot PATCH failed for {object_id}: {e}")

        # Write the decision log entry
        log_bdr_decision(decision_record)
        # End pipeline for this company
        return

    # If the company passes ICP, run intent detection next
    intent_result = detect_intent(company_name, pain_signal_data)
    print(f"Intent result: {intent_result}")
    decision_record["intent_result"] = intent_result

    # Patch intent outputs back to HubSpot
    properties_to_patch.update(
        {
            "intent_detected": intent_result.get("intent_detected"),
            "intent_type": intent_result.get("intent_type"),
            "intent_confidence": intent_result.get("confidence"),
            "intent_reasoning": intent_result.get("reasoning"),
        }
    )

    # Generate the outbound message using company + ICP + intent context
    outreach_text = generate_outreach(props, icp_result, intent_result)
    print(f"Outreach text: {outreach_text}")
    decision_record["outreach_generated"] = outreach_text is not None

    # Store the outreach message text if generation succeeded
    if outreach_text is not None:
        properties_to_patch["bdr_outreach_message"] = outreach_text
        properties_to_patch["bdr_review_needed"] = False
        decision_record["branch"] = "pass_icp_gate_outreach_generated"
    else:
        properties_to_patch["bdr_review_needed"] = True
        decision_record["branch"] = "pass_icp_gate_outreach_failed"

    # Patch all results back to HubSpot
    if object_id:
        try:
            response = patch_company_to_hubspot(object_id, properties_to_patch)
            print(f"Patch status: {response.status_code}")
            print(f"Patch response: {response.text}")
        except Exception as e:
            print(f"HubSpot PATCH failed for {object_id}: {e}")

    # Log the decision record to local file
    log_bdr_decision(decision_record)
    # End pipeline for this company
    return



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
    'state', 'number_locations', 'medicare_enrollment_resource', 'pain_signal_type', 'pain_signal_score'])

def orchestrate():
    headers = {
    "Authorization": f"Bearer {hubspot_api_key}",
    "Content-Type": "application/json"
    }
    records = load_hubspot_companies(headers)
    for company in records:
        company_properties = company.get("properties")
        run_bdr_pipeline(company_properties)
        time.sleep(1.5)
        print(f"Processing {company_properties.get('name')}")

    return 

#if __name__ == "__main__":
    #test_properties = {
        #"name": "HCA Healthcare",
        #"numberofemployees": "10000",
        #"hs_revenue_range": "1B+",
        #"state": "TN",
        #"medicare_enrollment_resource": "No",
        #"number_locations": "5",
        #"pain_signal_score": "85",
        #"pain_signal_type": "payer contract dispute,leadership change",
        #"hs_object_id": "49750594712"
    #}
    #run_bdr_pipeline(test_properties)

#### to run all companies:
if __name__ == "__main__":
    orchestrate()