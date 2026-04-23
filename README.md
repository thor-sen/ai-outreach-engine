# AI Outreach Engine

A four-stage BDR pipeline. Pulls company data from HubSpot, classifies ICP fit with Claude, detects buying intent from pain signals, generates an outreach message, and writes the result back to HubSpot for human review. Every decision is logged to a local audit file so you can trace exactly why the pipeline took the action it did.

The pain signal detector is a companion pipeline that analyzes news articles (currently mocked) for GTM-relevant pain signals and writes structured results back to HubSpot. The BDR pipeline then reads those pain signal fields as input for intent detection and outreach personalization.

## Tech Stack

- **Language:** Python
- **Libraries:** anthropic (Claude SDK), requests, python-dotenv
- **APIs:** Anthropic Claude (claude-sonnet-4-5), HubSpot CRM v3 (companies)
- **Model usage:** ICP classification, intent detection, pain signal detection, outreach generation

## How It Fits Into the GTM System

This is the action layer. It reads firmographic data and pain signal data produced by the enrichment and scoring pipelines upstream, applies the ICP gate, runs intent detection and outreach generation on the companies that pass, and writes either a ready-for-review message or a human-review flag back to HubSpot. Downstream HubSpot workflows pick up from there.

## Key Design Decisions

**The pipeline fails fast at the ICP gate.** Companies that don't pass ICP classification get flagged for manual review and never reach the Claude outreach call. That's deliberate. Running every company through the full pipeline would waste API cost on companies we already know aren't a fit, and it would generate outreach that shouldn't exist in the first place. The four stages run in order: ICP classification (gate), intent detection, outreach generation, human handoff flag (`bdr_review_needed` set, decision written to `bdr_decisions.json`). Stages two and three only run if stage one passes.

**Generated outreach is written to HubSpot as a custom property, not sent directly to prospects.** I could have wired the pipeline straight to an email sender. I didn't. The pipeline writes the message to a `bdr_outreach_message` property and flags the company with `bdr_review_needed`. A rep reviews every message before it goes out. That makes this AI augmentation rather than replacement, and it protects against brand damage if Claude generates something off. The rep in the loop is the feature, not the bottleneck.

**This pipeline reads composite scores as an input. It doesn't calculate them.** Scoring lives in the composite scorer. One responsibility per service. If scoring logic needs to change, I change it in one place. If the BDR pipeline needs to change (new stages, a different LLM, a revised prompt registry), I don't touch scoring. Clean boundaries make both systems easier to reason about.

## Architecture Overview

The system has two pipelines that work together:

### Pain Signal Detector (`pain_signal_detector.py`)

- **`fetch_news(company_name)`**: Returns news articles for a company. Currently mocked with realistic healthcare news for a small set of known companies (HCA, Virtua Health, Providence, Penn State Health). Returns empty list for unknown companies.
- **`pass_to_claude(articles)`**: Sends articles to Claude with the `pain_signal_classifier` prompt. Returns structured JSON: detected signal types, pain signal score (0-100), confidence (0-1), and reasoning.
- **`write_to_hubspot(object_id, properties)`**: PATCHes pain signal properties back to HubSpot. Handles 429 rate limits with a single retry.
- **`process_all_companies()`**: Orchestrates the loop. If confidence >= 0.7, writes pain signals to HubSpot. If below, flags `bdr_review_needed: true`.

### AI BDR Pipeline (`ai_bdr.py`)

- **`classify_icp_fit(company_properties)`**: Sends firmographic fields (employee count, revenue, state, medicare status, locations) to Claude with the `classify_icp_fit` prompt. Returns ICP tier (1-3), confidence (0-1), and reasoning. Handles 529 overload with 30s retry.
- **`detect_intent(company_name, pain_signal_data)`**: Sends pain signal type and score to Claude with the `detect_intent` prompt. Returns intent detected (bool), intent type, confidence, and reasoning.
- **`generate_outreach(company_properties, icp_result, intent_result)`**: Sends company context, ICP result, and intent result to Claude with the `generate_outreach` prompt. Returns plain text BDR message (not JSON). Uses Chapter's value prop and social proof.
- **`run_bdr_pipeline(company_properties)`**: Runs the three stages in sequence with gating logic. If ICP gate fails, patches `bdr_review_needed: true` and stops. If ICP passes, runs intent and outreach, patches all results back to HubSpot. Logs every decision to `bdr_decisions.json`.
- **`orchestrate()`**: Fetches all companies from HubSpot and loops through them with 1.5s delay between companies.

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

This repo is the action layer of a larger GTM system. The scripts depend on upstream pipelines having populated HubSpot with firmographic data and pain signal fields. Running them standalone against a fresh HubSpot portal will not produce meaningful output.

**What you need before running:**

- A HubSpot Private App token with `crm.objects.companies.read` and `crm.objects.companies.write` scopes.
- An Anthropic API key with access to `claude-sonnet-4-5`.
- A HubSpot portal populated with companies that have already been enriched upstream (`numberofemployees`, `hs_revenue_range`, `state`, `number_locations`, `medicare_enrollment_resource`, and the pain signal fields `pain_signal_type` and `pain_signal_score`).
- Custom properties on the HubSpot company object: `bdr_outreach_message`, `bdr_review_needed`, and the pain signal fields the detector writes to.

**Setup:**

```bash
pip install -r requirements.txt
```

Create a `.env` file with:

```
HUBSPOT_API_KEY=your_token_here
ANTHROPIC_API_KEY=your_key_here
```

**Running the pipelines:**

The pain signal detector currently uses mocked news data. To run it against that mock data and patch results back to HubSpot:

```bash
python pain_signal_detector.py
```

To run the BDR pipeline (reads scored and enriched companies from HubSpot, runs the ICP gate, intent detection, and outreach generation, writes results back to HubSpot, and logs decisions to `bdr_decisions.json`):

```bash
python ai_bdr.py
```

**If you don't have a configured HubSpot portal:**

The repo is still useful as reference. Read the architecture overview and design decisions sections above to understand the system. The prompt registry (`prompt_registry.py`) and decision logs (`bdr_decisions.json`) are also worth reading on their own as examples of structured Claude API usage.

## Documentation

For the full system architecture and design decisions, see [ai_bdr.md](ai_bdr.md).

For the pain signal confidence gate rationale, see [pain_signal_decision_policy.md](pain_signal_decision_policy.md).

## Planned Extensions

- Replace mocked news data with a real news API (NewsAPI, healthcare-specific feed) for live pain signal detection.
- Add inbound filtering so the pipeline only processes new inbound companies rather than the entire CRM.
- Calibrate confidence thresholds using labeled outcomes (meetings booked, pipeline created) instead of heuristics.
- Batch Claude calls or run them asynchronously to reduce latency at scale.
- Add a BDR review queue UI where reps can validate borderline signals and feed corrections back into prompt tuning.
