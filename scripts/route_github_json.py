"""Sample real GitHub issues, classify 100 with Laya CUDA, and export Excel."""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

from backend.batch import classify_rows, parse_tickets_csv
from backend.classifier.service import LayaClassifier
from backend.reporting.workbook import build_workbook

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["ticket_id", "subject", "body", "customer_id", "customer_tier", "product",
          "source_channel", "created_at", "repo_name", "issue_url", "issue_state", "github_labels"]


def sample_issues(issues: list[dict], count: int, seed: int) -> list[dict[str, str]]:
    candidates = [issue for issue in issues if isinstance(issue, dict) and
                  len(str(issue.get("title") or "").strip()) >= 3 and
                  80 <= len(str(issue.get("body") or "").strip()) <= 1500 and issue.get("id")]
    random.Random(seed).shuffle(candidates)
    selected, per_repo, seen_ids = [], Counter(), set()
    for issue in candidates:
        repo = str(issue.get("repo_name") or "unknown/unknown").strip()
        issue_id = str(issue["id"])
        if issue_id in seen_ids or per_repo[repo] >= 2:
            continue
        title = str(issue["title"]).strip()[:180]
        body = str(issue["body"]).strip()[:5000]
        labels = ", ".join(str(label.get("name", "")) for label in issue.get("labels", [])
                           if isinstance(label, dict))[:1000]
        selected.append({
            "ticket_id": "GH-" + issue_id, "subject": title, "body": body,
            "customer_id": str((issue.get("user") or {}).get("login") or ""),
            "customer_tier": "Standard", "product": repo, "source_channel": "GitHub Issue",
            "created_at": str(issue.get("created_at") or ""), "repo_name": repo,
            "issue_url": str(issue.get("html_url") or ""), "issue_state": str(issue.get("state") or ""),
            "github_labels": labels,
        })
        seen_ids.add(issue_id)
        per_repo[repo] += 1
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f"Only {len(selected)} usable unique issues found; requested {count}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source github_issues_tickets.json")
    parser.add_argument("--count", type=int, default=100, help="Number of issues (default 100)")
    parser.add_argument("--seed", type=int, default=42, help="Stable sampling seed")
    parser.add_argument("--csv-output", type=Path, default=ROOT / "dataset" / "github_issues_100.csv")
    parser.add_argument("--excel-output", type=Path, default=ROOT / "outputs" / "LayaDesk_GitHub_Issues_100.xlsx")
    args = parser.parse_args()
    if not 1 <= args.count <= 500:
        parser.error("--count must be between 1 and 500")
    with args.input.open(encoding="utf-8") as source:
        issues = json.load(source)
    if not isinstance(issues, list):
        raise ValueError("Expected a JSON array of GitHub issues")
    rows = sample_issues(issues, args.count, args.seed)
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Selected {len(rows)} issues from {len(set(row['repo_name'] for row in rows))} repos", flush=True)
    print(f"CSV: {args.csv_output.resolve()}", flush=True)

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; LayaDesk will not use CPU")
    parsed = parse_tickets_csv(args.csv_output.read_bytes())

    def progress(index: int, total: int, item: dict) -> None:
        if index % 10 == 0 or index == total:
            print(f"Laya CUDA: {index}/{total}", flush=True)

    results = classify_rows(parsed, LayaClassifier(), progress)
    args.excel_output.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(results, args.csv_output.name).save(args.excel_output)
    counts = Counter(item["route"]["status"] for item in results)
    print(f"Excel: {args.excel_output.resolve()}")
    print(f"Routing: {dict(counts)}")


if __name__ == "__main__":
    main()
