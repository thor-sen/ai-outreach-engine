## What we built

This project is an **AI BDR pipeline** for inbound health system accounts. It pulls firmographic and pain-signal fields from HubSpot, asks Claude to classify **ICP fit** and **intent**, generates a short **outreach message** when the account passes the gate, and writes results back to HubSpot. Every company decision is logged locally so you can audit why the system took a particular action.

At a high level:
- **ICP classification**: Is this company a good fit (tiered) with sufficient confidence?
- **Intent detection**: Based on pain signal fields, is there buying intent and what type?
- **Outreach generation**: If fit is strong, write a concise BDR message aligned to Chapter’s value prop.
- **Confidence gate + human handoff**: If confidence is low or fit is weak, flag for manual review instead of generating automation noise.

## How to run

1) Install dependencies (minimal):

```bash
pip3 install python-dotenv requests anthropic
```

2) Create a `.env` file in this folder with:

```bash
HUBSPOT_API_KEY="YOUR_HUBSPOT_PRIVATE_APP_TOKEN"
ANTHROPIC_API_KEY="YOUR_ANTHROPIC_API_KEY"
```

3) Run the pipeline:

```bash
python3 ai_bdr.py
```

What to expect:
- The script fetches HubSpot companies with properties like `name`, `hs_object_id`, `numberofemployees`, `hs_revenue_range`, `state`, `number_locations`, `medicare_enrollment_resource`, `pain_signal_type`, and `pain_signal_score`.
- It loops through companies and runs ICP → gate → intent → outreach.
- It writes decision logs to `bdr_decisions.json` (one JSON object per line).
- It patches results back to HubSpot using the company’s `hs_object_id`.

## Features

- **Dynamic prompting from real CRM fields**: Claude is prompted using the actual values pulled from HubSpot (no hardcoded examples).
- **Two-stage decisioning**:
  - **ICP gate**: `confidence >= 0.7` and `icp_tier <= 2`
  - **Intent + outreach** only run after passing ICP
- **CRM hygiene via human handoff**: accounts that fail the gate are marked with `bdr_review_needed: true` instead of writing low-quality automation.
- **Portfolio-grade audit trail**: every decision (inputs, model outputs, and which branch executed) is appended to `bdr_decisions.json`.
- **Operational resilience**:
  - HubSpot pagination and error handling in `fetch_all_records`
  - Anthropic 529 overload retry (sleep + retry once) and reduced request rate between companies

## Limitations

- **Not a real “inbound detector”**: right now it runs over the companies returned by the HubSpot API call; production would filter to “new inbound this week/day” or to specific lifecycle stages.
- **Limited signal richness**: intent detection currently depends on `pain_signal_type` and `pain_signal_score` fields rather than full-text sources (news, website intent, calls, emails).
- **Hard-coded gates**: the 0.7 confidence threshold and `icp_tier <= 2` rule are heuristics; they should be calibrated using labeled outcomes (meetings booked, pipeline created, close rates).
- **Patch schema assumes custom properties exist**: the script patches fields like ICP/intent outputs and `bdr_outreach_message`. In a real HubSpot portal, those custom properties must be created first and mapped to workflows.
- **Scaling constraints**: calling Claude multiple times per company can be slow/costly at high volume; a production system would batch, cache, or run asynchronously and add stronger rate limiting.

## Ideal Architecture

### 1. Inbound Detection and Enrichment

**Fetching:** Production would detect inbound companies from multiple sources — landing page submissions, website visit duration thresholds, demo requests through lead capture forms, or inbound calls. Each source type could carry different intent signals and priority levels. The pipeline would pull qualifying company records into a standardized format for downstream processing.

**Enrichment:** Enrich each company with industry, vertical, employee count, revenue, and vertical-specific fields (e.g., Medicare enrollment for healthcare). Enrichment sources vary in coverage and cost — the enrichment layer should be provider-agnostic so sources can be swapped or layered. Enriched fields are patched back to HubSpot.

**Classification:** A scoring model evaluates firmographic fit. Healthcare companies run through the health system scoring model; other verticals would need separate models tuned to their own ICP definitions. The output is a firmographic score patched back to HubSpot.

### 2. Intent Detection

If a company passes the firmographic gate, the pipeline uses Claude to detect pain signals relevant to the vertical. A production version would consume real data sources — intent data providers, news APIs, scraped press releases — rank signals by relevance and recency, and return structured outputs: intent score, intent flag, and intent tags, all patched back to HubSpot.

### 3. Response Generation

Two paths based on gating results. Companies that pass the classification gate get a BDR message generated from firmographic inputs. Companies that also show high intent get a more personalized message incorporating the specific pain signal. Both populate a HubSpot property like `personalized_message_suggestion`. A HubSpot workflow assigns ownership and enrolls the lead in an inbound sequence with the personalized message as a dynamic field. BDRs edit and send manually, and time saved is measurable.

### 4. Confidence Gate and Human Handoff

Only accounts that meet the confidence and fit gates get fully automated outputs. Accounts below the classification gate are flagged into a manual review queue at low priority, keeping the CRM clean and rep attention focused on the highest-quality leads.

