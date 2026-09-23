"""Curate 100 synthetic tickets whose measured Laya CUDA routing is 50/50."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path

import torch

from backend.classifier.service import LayaClassifier
from backend.reporting.workbook import build_workbook
from backend.routing.engine import decide

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataset" / "tickets.csv"
PRIOR = ROOT / "dataset" / "laya_predictions.csv"
CSV_OUT = ROOT / "dataset" / "tickets_balanced_50_50.csv"
EXCEL_OUT = ROOT / "outputs" / "LayaDesk_Balanced_50_50.xlsx"

BASE_BODIES = [
    "Can you explain when the annual renewal will be billed and what it covers?",
    "Can you explain when our annual renewal will be billed and what it covers?",
    "Can you explain when the yearly renewal will be billed and what it covers?",
    "Can you explain when the annual renewal will be charged and what it covers?",
    "Can you explain when the annual subscription renewal will be billed and what it covers?",
    "Can you explain when the annual renewal will be billed and what services it covers?",
    "Can you explain when the annual renewal will be billed and which seats it covers?",
    "Can you explain when the annual renewal will be billed and which plan it covers?",
    "Can you explain when the annual renewal will be billed and what is included?",
    "When will the annual renewal be billed and what does it cover?",
    "What date will the annual renewal be billed, and what does the charge cover?",
    "Could you tell me when the annual renewal will be billed and what it includes?",
    "Please explain when the annual renewal will be billed and what it covers.",
    "Can you explain when the annual renewal will be billed and what it covers for our team?",
    "Can you explain when the annual renewal will be billed and what it covers for our account?",
]


def auto_candidates():
    seen = set()
    for subject in ("Annual billing question", "Annual renewal billing"):
        for body in BASE_BODIES:
            if (subject, body) not in seen:
                seen.add((subject, body))
                yield subject, body
    coverages = (
        "what it covers", "which services it covers", "which seats it covers", "which plan it covers",
        "what is included", "which features it covers", "what the charge includes", "what our payment covers",
        "what the renewal includes", "which workspace it covers", "which users it covers", "what the invoice includes",
    )
    for period, verb, coverage in product(("annual", "yearly"), ("billed", "charged", "invoiced"), coverages):
        subject = "Annual billing question"
        body = f"Can you explain when the {period} renewal will be {verb} and {coverage}?"
        if (subject, body) not in seen:
            seen.add((subject, body))
            yield subject, body
    for audience in ("finance team", "billing team", "account manager", "workspace owner", "bookkeeper",
                     "subscription admin", "operations team", "procurement team", "support team", "team lead"):
        subject = "Annual billing question"
        body = f"Can you explain when the annual renewal will be billed and what it covers for our {audience}?"
        if (subject, body) not in seen:
            seen.add((subject, body))
            yield subject, body


def auto_row(index: int, subject: str, body: str) -> dict[str, str]:
    return {
        "ticket_id": f"BAL-A{index:03d}", "subject": subject, "body": body,
        "customer_id": f"CUS-B{index:03d}", "customer_tier": "Standard",
        "previous_ticket_count": str(index % 3), "product": "LayaDesk",
        "source_channel": ("Web", "Chat", "Email")[index % 3],
        "created_at": (datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc) - timedelta(minutes=index * 7)).isoformat(),
        "department": "Billing", "intent": "Payment Problem", "urgency": "Medium",
        "refund": "false", "churn": "false", "escalation": "false",
    }


def classify(classifier: LayaClassifier, row: dict[str, str]) -> dict:
    ticket = {"subject": row["subject"], "body": row["body"],
              "customer_tier": row["customer_tier"], "product": row["product"]}
    prediction = classifier.predict(ticket)
    route = decide(prediction, row["customer_tier"], row["subject"] + " " + row["body"])
    return {"input": row, "prediction": prediction, "route": route}


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; no CPU fallback is permitted")
    with SOURCE.open(newline="", encoding="utf-8") as source:
        original = list(csv.DictReader(source))
    with PRIOR.open(newline="", encoding="utf-8") as prior:
        old_status = {row["ticket_id"]: row["status"] for row in csv.DictReader(prior)}
    fields = list(original[0])
    classifier = LayaClassifier()
    auto = []
    examined = 0
    for subject, body in auto_candidates():
        examined += 1
        item = classify(classifier, auto_row(examined, subject, body))
        if item["route"]["status"] == "AUTO_ROUTED":
            auto.append(item)
        if examined % 10 == 0 or len(auto) == 50:
            print(f"Auto-route candidates: {examined} checked, {len(auto)}/50 selected", flush=True)
        if len(auto) == 50:
            break
    if len(auto) != 50:
        raise RuntimeError(f"Only found {len(auto)} verified auto-route examples")

    by_department = defaultdict(list)
    for row in original:
        if old_status.get(row["ticket_id"]) == "NEEDS_REVIEW":
            by_department[row["department"]].append(row)
    review = []
    for department in ("Billing", "Technical Support", "Account Support", "Sales", "General Support"):
        found = 0
        for source_row in by_department[department]:
            row = dict(source_row)
            row["ticket_id"] = f"BAL-R{len(review) + 1:03d}"
            item = classify(classifier, row)
            if item["route"]["status"] == "NEEDS_REVIEW":
                review.append(item)
                found += 1
            if found == 10:
                break
        if found != 10:
            raise RuntimeError(f"Only found {found} verified review examples for {department}")
        print(f"Human review: {len(review)}/50 verified", flush=True)

    # Alternate the two outcomes so a recording shows both kinds of decision immediately.
    results = [item for pair in zip(auto, review) for item in pair]
    counts = Counter(item["route"]["status"] for item in results)
    if counts != {"AUTO_ROUTED": 50, "NEEDS_REVIEW": 50}:
        raise AssertionError(f"Unexpected route split: {counts}")
    with CSV_OUT.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: item["input"].get(field, "") for field in fields} for item in results)
    EXCEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(results, CSV_OUT.name).save(EXCEL_OUT)
    print(f"CSV: {CSV_OUT}")
    print(f"Verified Excel: {EXCEL_OUT}")
    print(f"Laya CUDA routing: {counts['AUTO_ROUTED']} auto-routed / {counts['NEEDS_REVIEW']} human review")


if __name__ == "__main__":
    main()
