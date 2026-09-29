# Autonomous Insurance Claims Processing Agent

A lightweight Python agent that processes FNOL (First Notice of Loss) documents:
extracts key fields, detects missing/inconsistent data, routes the claim, and explains why.

## Approach
1. **Read** the document (`.txt` directly, `.pdf` via `pypdf`).
2. **Extract** 16 fields (policy, incident, parties, asset, claim details) by matching
   `Label: value` lines, with aliases (e.g. "VIN" = Asset ID). Multi-line values are supported.
3. **Validate**: a field that is empty / "N/A" is *missing*. Two consistency checks are run:
   incident date inside policy period, and estimated damage vs initial estimate.
4. **Route** using these rules, in priority order:

| Priority | Condition | Route |
|---|---|---|
| 1 | Description contains "fraud", "inconsistent", "staged" | Investigation Flag |
| 2 | Any mandatory field missing (or inconsistency found) | Manual Review |
| 3 | Claim type = Injury | Specialist Queue |
| 4 | Estimated damage < Rs.25,000 | Fast-track |
| 5 | Otherwise | Standard Processing |

Why this order: suspected fraud must never be fast-tracked, and incomplete claims can't be trusted for
other rules. This priority is my design decision since the brief doesn't say what to do when rules overlap.

No external AI API is used, so it is deterministic, free, and needs no API key.

## Run it
```bash
pip install -r requirements.txt
python agent.py samples/                 # all sample claims
python agent.py samples/claim1_fasttrack.txt   # one claim
```
JSON results print to the terminal and are saved in `output/`.

## Output format
```json
{
  "extractedFields": {},
  "missingFields": [],
  "inconsistentFields": [],
  "recommendedRoute": "",
  "reasoning": ""
}
```

## Sample results
| File | Route |
|---|---|
| claim1_fasttrack | Fast-track |
| claim2_missing | Manual Review |
| claim3_injury | Specialist Queue |
| claim4_fraud | Investigation Flag |
| claim5_standard | Standard Processing |

## Limitations / future work
- Extraction assumes `Label: value` layout; scanned PDFs would need OCR.
- An LLM could be added for free-form documents.
