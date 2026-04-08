# AI Outreach Engine

An AI BDR pipeline that pulls company data from HubSpot, uses Claude to classify ICP fit, detect buying intent from pain signals, and generate personalized outreach messages. Companies that pass a confidence gate get automated outreach written back to HubSpot. Companies that fail get flagged for human review. Every decision is logged to a local audit file so you can trace exactly why the system took a particular action.

The pain signal detector is a companion pipeline that analyzes news articles (currently mocked) for GTM-relevant pain signals and writes structured results back to HubSpot. The BDR pipeline then consumes those pain signal fields as input for intent detection and outreach personalization.

## Tech Stack

- **Language:** Python
- **Libraries:** anthropic (Claude SDK), requests, python-dotenv
- **APIs:** Anthropic Claude (claude-sonnet-4-5), HubSpot CRM v3 (companies)
- **Model usage:** ICP classification, intent detection, pain signal detection, outreach generation

## How It Fits Into the GTM System

This is the final action layer. It consumes the firmographic and pain signal data produced by the upstream enrichment and scoring pipelines, applies AI-driven classification and gating, and outputs either a ready-to-send BDR message or a human review flag — both written back to HubSpot where workflows can pick them up.

## Key Design Decisions

- **Confidence gating over blanket automation** — The pipeline only generates outreach when ICP confidence >= 0.7 and tier <= 2. Everything below that threshold gets flagged for human review rather than producing low-quality automation noise. This keeps the CRM clean and rep attention focused.
- **Staged pipeline with early termination** — ICP classification runs first. If a company fails the gate, the pipeline stops immediately without burning Claude calls on intent detection and outreach generation. This reduces API cost and latency for companies that aren't a fit.

## Architecture Overview

The system has two pipelines that work together:

### Pain Signal Detector (`pain_signal_detector.py`)

- **`fetch_news(company_name)`** — Returns news articles for a company. Currently mocked with realistic healthcare news for a small set of known companies (HCA, Virtua Health, Providence, Penn State Health). Returns empty list for unknown companies.
- **`pass_to_claude(articles)`** — Sends articles to Claude with the `pain_signal_classifier` prompt. Returns structured JSON: detected signal types, pain signal score (0-100), confidence (0-1), and reasoning.
- **`write_to_hubspot(object_id, properties)`** — PATCHes pain signal properties back to HubSpot. Handles 429 rate limits with a single retry.
- **`process_all_companies()`** — Orchestrates the loop. If confidence >= 0.7, writes pain signals to HubSpot. If below, flags `bdr_review_needed: true`.

### AI BDR Pipeline (`ai_bdr.py`)

- **`classify_icp_fit(company_properties)`** — Sends firmographic fields (employee count, revenue, state, medicare status, locations) to Claude with the `classify_icp_fit` prompt. Returns ICP tier (1-3), confidence (0-1), and reasoning. Handles 529 overload with 30s retry.
- **`detect_intent(company_name, pain_signal_data)`** — Sends pain signal type and score to Claude with the `detect_intent` prompt. Returns intent detected (bool), intent type, confidence, and reasoning.
- **`generate_outreach(company_properties, icp_result, intent_result)`** — Sends company context, ICP result, and intent result to Claude with the `generate_outreach` prompt. Returns plain text BDR message (not JSON). Uses Chapter's value prop and social proof.
- **`run_bdr_pipeline(company_properties)`** — Runs the three stages in sequence with gating logic. If ICP gate fails, patches `bdr_review_needed: true` and stops. If ICP passes, runs intent and outreach, patches all results back to HubSpot. Logs every decision to `bdr_decisions.json`.
- **`orchestrate()`** — Fetches all companies from HubSpot and loops through them with 1.5s delay between companies.

### Prompt Registry (`prompt_registry.py`)

Centralized system prompts for all four Claude calls. Each prompt defines the expected JSON schema (or plain text for outreach) and constrains Claude's output format.

## Sample Output

Decision log entry (`bdr_decisions.json`):

```json
{
  "hs_object_id": "49750594712",
  "company_name": "HCA Healthcare",
  "pain_signal_type": "payer contract dispute,leadership change",
  "pain_signal_score": "85",
  "icp_result": {
    "confidence": 0.85,
    "icp_tier": 1,
    "reasoning": "Large health system with high revenue, strong employee-to-location ratio, and no existing Medicare resource"
  },
  "passes_icp_gate": true,
  "intent_result": {
    "intent_detected": true,
    "intent_type": "payer dispute resolution",
    "confidence": 0.9,
    "reasoning": "Active payer contract dispute signals operational pain that aligns with Chapter value prop"
  },
  "outreach_generated": true,
  "branch": "pass_icp_gate_outreach_generated",
  "timestamp_utc": "2026-03-17T18:40:36.827955+00:00"
}
```

## How to Run

**1. Install dependencies:**

```bash
pip install -r requirements.txt
```

**2. Create a `.env` file:**

```
HUBSPOT_API_KEY=pat-na1-your-token-here
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Your HubSpot Private App needs `crm.objects.companies.read` and `crm.objects.companies.write` scopes. The Anthropic key needs access to claude-sonnet-4-5.

**3. Run the pain signal detector (optional — populates pain signal fields in HubSpot):**

```bash
python pain_signal_detector.py
```

**4. Run the BDR pipeline:**

```bash
python ai_bdr.py
```

This fetches all companies from HubSpot, runs the ICP > intent > outreach pipeline, patches results back to HubSpot, and logs decisions to `bdr_decisions.json`.

## Documentation

For the full system architecture and design decisions, see [ai_bdr.md](ai_bdr.md).

For the pain signal confidence gate rationale, see [pain_signal_decision_policy.md](pain_signal_decision_policy.md).

## Planned Extensions

- Replace mocked news data with a real news API (NewsAPI, healthcare-specific feed) for live pain signal detection
- Add inbound filtering so the pipeline only processes new inbound companies rather than the entire CRM
- Calibrate confidence thresholds using labeled outcomes (meetings booked, pipeline created) instead of heuristics
- Batch Claude calls or run asynchronously to reduce latency at scale
- Add a BDR review queue UI where reps can validate borderline signals and provide feedback for prompt tuning
# ai-outreach-engine
