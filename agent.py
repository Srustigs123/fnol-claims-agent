"""Autonomous Insurance Claims Processing Agent (FNOL).

Reads FNOL documents (.txt or .pdf), extracts fields, finds missing or
inconsistent ones, routes the claim, and explains the decision.

Usage:
    python agent.py samples/            # process a whole folder
    python agent.py samples/claim1.txt  # process a single file
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------- 1. Fields we want and the labels they may appear under ----------
FIELD_ALIASES = {
    "policy_number": ["policy number", "policy no", "policy #"],
    "policyholder_name": ["policyholder name", "policyholder", "insured name"],
    "effective_dates": ["effective dates", "policy period", "effective date"],
    "incident_date": ["date of loss", "incident date", "date"],
    "incident_time": ["time of loss", "incident time", "time"],
    "location": ["location", "incident location"],
    "description": ["description", "incident description", "description of loss"],
    "claimant": ["claimant", "claimant name"],
    "third_parties": ["third parties", "third party"],
    "contact_details": ["contact details", "contact", "phone", "contact number"],
    "asset_type": ["asset type", "vehicle type"],
    "asset_id": ["asset id", "vin", "vehicle id", "registration number"],
    "estimated_damage": ["estimated damage", "damage estimate"],
    "claim_type": ["claim type", "type of claim"],
    "attachments": ["attachments", "attached documents"],
    "initial_estimate": ["initial estimate"],
}
LABEL_TO_FIELD = {a: f for f, names in FIELD_ALIASES.items() for a in names}
MANDATORY = list(FIELD_ALIASES.keys())  # every field is mandatory here

SUSPICIOUS_WORDS = ["fraud", "inconsistent", "staged"]
FAST_TRACK_LIMIT = 25000  # rupees
EMPTY_VALUES = {"", "n/a", "na", "none", "null", "-", "not provided", "unknown"}


# ---------- 2. Read the document ----------
def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader  # pip install pypdf
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8")


# ---------- 3. Extract the fields ----------
def extract_fields(text: str) -> dict:
    fields = {f: None for f in FIELD_ALIASES}
    current = None
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z #/]+?)\s*:\s*(.*)$", line)
        if m and m.group(1).strip().lower() in LABEL_TO_FIELD:
            current = LABEL_TO_FIELD[m.group(1).strip().lower()]
            fields[current] = m.group(2).strip()
        elif current and line.strip():  # continuation of a multi-line value
            fields[current] = (fields[current] + " " + line.strip()).strip()
    for k, v in fields.items():
        if v is not None and v.strip().lower() in EMPTY_VALUES:
            # "None" is a valid answer for third parties (there were none)
            if k == "third_parties" and v.strip().lower() == "none":
                continue
            fields[k] = None
    return fields


# ---------- 4. Helpers to check the data ----------
def to_amount(value):
    if not value:
        return None
    digits = re.sub(r"[^\d.]", "", value)
    return float(digits) if digits else None


def to_date(value):
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None


def find_inconsistencies(f: dict) -> list:
    issues = []
    # Incident date must fall inside the policy period
    if f["effective_dates"] and f["incident_date"]:
        parts = re.split(r"\s+to\s+|\s+-\s+", f["effective_dates"])
        if len(parts) == 2:
            start, end, inc = to_date(parts[0]), to_date(parts[1]), to_date(f["incident_date"])
            if start and end and inc and not (start <= inc <= end):
                issues.append("Incident date is outside the policy effective dates")
    # Two estimates should roughly agree
    a, b = to_amount(f["estimated_damage"]), to_amount(f["initial_estimate"])
    if a and b and abs(a - b) / max(a, b) > 0.5:
        issues.append("Estimated damage and initial estimate differ by more than 50%")
    return issues


# ---------- 5. Route the claim ----------
def route_claim(f: dict, missing: list, issues: list):
    reasons = []
    desc = (f["description"] or "").lower()
    hits = [w for w in SUSPICIOUS_WORDS if w in desc]
    damage = to_amount(f["estimated_damage"])
    if damage is None:
        damage = to_amount(f["initial_estimate"])

    # Priority: fraud > missing data > injury > fast-track > standard
    if hits:
        return "Investigation Flag", (
            f"Description contains suspicious word(s): {', '.join(hits)}. "
            "Flagged for investigation regardless of other rules.")
    if missing:
        return "Manual Review", (
            f"Mandatory field(s) missing: {', '.join(missing)}. "
            "A human must complete or verify the claim.")
    if issues:
        return "Manual Review", "Inconsistencies found: " + "; ".join(issues) + "."
    if (f["claim_type"] or "").lower() == "injury":
        return "Specialist Queue", "Claim type is injury, so it goes to the specialist queue."
    if damage is not None and damage < FAST_TRACK_LIMIT:
        return "Fast-track", (
            f"Estimated damage Rs.{damage:,.0f} is below Rs.{FAST_TRACK_LIMIT:,}, "
            "all fields present, no red flags.")
    return "Standard Processing", (
        f"Estimated damage Rs.{damage:,.0f} is at or above Rs.{FAST_TRACK_LIMIT:,}; "
        "no special rule applies.")


# ---------- 6. Put it all together ----------
def process(path: Path) -> dict:
    fields = extract_fields(read_document(path))
    missing = [k for k in MANDATORY if not fields[k]]
    issues = find_inconsistencies(fields)
    route, reasoning = route_claim(fields, missing, issues)
    return {
        "extractedFields": fields,
        "missingFields": missing,
        "inconsistentFields": issues,
        "recommendedRoute": route,
        "reasoning": reasoning,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python agent.py <file-or-folder>")
    target = Path(sys.argv[1])
    files = sorted(p for p in target.iterdir() if p.suffix.lower() in (".txt", ".pdf")) \
        if target.is_dir() else [target]
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    for f in files:
        result = process(f)
        (out_dir / f"{f.stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n=== {f.name} ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
