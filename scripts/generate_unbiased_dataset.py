"""Sample real tickets at random, classify with Laya CUDA, and report accuracy
PER CONFIDENCE BAND — the piece needed to pick decide() thresholds from data
instead of guessing. Otherwise identical to generate_unbiased_dataset.py.
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

from backend.classifier.service import LayaClassifier
from backend.reporting.workbook import build_workbook
from backend.routing.engine import decide

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataset" / "tickets.csv"
CSV_OUT = ROOT / "dataset" / "tickets_unbiased_sample.csv"
EXCEL_OUT = ROOT / "outputs" / "LayaDesk_Unbiased_Sample.xlsx"

# Confidence bucket edges. Adjust freely — finer buckets need more samples per
# bucket to be trustworthy, so don't go finer than this without a bigger --count.
BUCKET_EDGES = [0.0, 0.15, 0.25, 0.35, 0.45, 0.60, 0.75, 0.85, 1.01]


def bucket_label(conf: float) -> str:
    for lo, hi in zip(BUCKET_EDGES, BUCKET_EDGES[1:]):
        if lo <= conf < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "1.00+"


def classify(classifier: LayaClassifier, row: dict[str, str]) -> dict:
    ticket = {
        "subject": row["subject"],
        "body": row["body"],
        "customer_tier": row["customer_tier"],
        "product": row["product"],
    }
    prediction = classifier.predict(ticket)
    route = decide(prediction, row["customer_tier"], row["subject"] + " " + row["body"])
    return {"input": row, "prediction": prediction, "route": route}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100, help="Sample size (default 100)")
    parser.add_argument("--seed", type=int, default=42, help="Stable sampling seed")
    parser.add_argument("--source", type=Path, default=SOURCE, help="Full ticket pool to sample from")
    parser.add_argument("--csv-output", type=Path, default=CSV_OUT)
    parser.add_argument("--excel-output", type=Path, default=EXCEL_OUT)
    args = parser.parse_args()

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; no CPU fallback is permitted")

    with args.source.open(newline="", encoding="utf-8") as source:
        pool = list(csv.DictReader(source))
    if len(pool) < args.count:
        raise ValueError(f"Pool has only {len(pool)} tickets; requested {args.count}")

    sample = random.Random(args.seed).sample(pool, args.count)

    classifier = LayaClassifier()
    results = []
    for i, row in enumerate(sample, 1):
        item = classify(classifier, row)
        results.append(item)
        if i % 10 == 0 or i == len(sample):
            print(f"{i}/{len(sample)}  {row.get('ticket_id', '?')}  "
                  f"{item['prediction'].get('department', '?')}  {item['route']['status']}", flush=True)

    counts = Counter(item["route"]["status"] for item in results)
    fields = list(pool[0])
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: item["input"].get(field, "") for field in fields} for item in results)

    args.excel_output.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(results, args.csv_output.name).save(args.excel_output)

    print(f"CSV: {args.csv_output}")
    print(f"Excel: {args.excel_output}")
    print(f"Natural routing split over {len(results)} randomly sampled tickets: {dict(counts)}")

    has_labels = "department" in fields
    if has_labels:
        correct = sum(1 for item in results
                      if item["input"].get("department") == item["prediction"].get("department"))
        print(f"Overall department accuracy: {correct}/{len(results)} ({correct / len(results):.1%})")

    # --- The part that matters for picking thresholds ---
    print("\nConfidence-band reliability (is confidence trustworthy for auto-routing?):")
    print(f"{'band':<12}{'n':>5}{'correct':>9}{'accuracy':>11}{'status split'}")
    buckets: dict[str, list] = defaultdict(list)
    for item in results:
        conf = float(item["prediction"]["department_confidence"])
        buckets[bucket_label(conf)].append(item)
    for lo, hi in zip(BUCKET_EDGES, BUCKET_EDGES[1:]):
        label = f"{lo:.2f}-{hi:.2f}"
        items = buckets.get(label, [])
        if not items:
            continue
        n = len(items)
        if has_labels:
            correct_n = sum(1 for item in items
                            if item["input"].get("department") == item["prediction"].get("department"))
            acc_str = f"{correct_n}/{n} ({correct_n / n:.0%})"
        else:
            acc_str = "n/a (no ground truth in source csv)"
        status_split = dict(Counter(item["route"]["status"] for item in items))
        print(f"{label:<12}{n:>5}{'':>9}{acc_str:>20}   {status_split}")

    print(
        "\nRead this top to bottom: pick AUTO_THRESHOLD at the lowest band where "
        "accuracy is consistently high enough for your risk tolerance, and "
        "REVIEW_THRESHOLD (below which -> manual_triage instead of human_confirmation) "
        "at a band where accuracy is clearly too low to trust unsupervised. "
        "A band with very few tickets (n<10) is too noisy to set a threshold on alone — "
        "rerun with a larger --count to firm it up before trusting it."
    )


if __name__ == "__main__":
    main()