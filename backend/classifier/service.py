from __future__ import annotations

import os
from typing import Any

from .questions import QUESTIONS
from backend.routing.engine import DEPARTMENTS, INTENTS, URGENCIES


def _clamp(value: Any) -> float:
    return max(0.0, min(1.0, float(value)))


def _answer_choice(answers: dict, key: str, valid: tuple[str, ...]) -> tuple[str, float]:
    answer = answers[key]
    label = answer["choice"]
    if label not in valid:
        raise ValueError(f"Unexpected Laya {key}: {label}")
    return label, _clamp(answer["confidence"])


def _answer_score(answers: dict, key: str) -> tuple[int, float]:
    answer = answers[key]
    score = max(0, min(3, round(float(answer["score"]))))
    return score, _clamp(answer.get("confidence", 0.5))


def normalize_laya(result: dict) -> dict:
    answers = result["answers"]
    department, department_confidence = _answer_choice(answers, "department", DEPARTMENTS)
    intent, intent_confidence = _answer_choice(answers, "intent", INTENTS)
    urgency_index, urgency_confidence = _answer_score(answers, "urgency")
    frustration, frustration_confidence = _answer_score(answers, "frustration")
    return {
        "department": department,
        "department_confidence": department_confidence,
        "intent": intent,
        "intent_confidence": intent_confidence,
        "urgency": URGENCIES[urgency_index],
        "urgency_confidence": urgency_confidence,
        "frustration": frustration,
        "frustration_confidence": frustration_confidence,
        "refund_probability": _clamp(answers["refund_requested"]["noul"]),
        "churn_probability": _clamp(answers["churn_risk"]["noul"]),
        "escalation_probability": _clamp(answers["human_escalation"]["noul"]),
        "model": result.get("routing", {}).get("model", "laya"),
        "source": "laya",
    }


class LayaClassifier:
    def __init__(self) -> None:
        self._router = None

    def predict(self, ticket: dict) -> dict:
        if self._router is None:
            from laya import Router
            self._router = Router(device="cuda")
        state = {
            "subject": ticket["subject"],
            "body": ticket["body"],
            "customer_tier": ticket.get("customer_tier", "Standard"),
            "product": ticket.get("product", "LayaDesk"),
        }
        return normalize_laya(self._router.predict(state, QUESTIONS))


class DemoClassifier:
    """Deterministic presentation simulation; never represented as model output."""

    def predict(self, ticket: dict) -> dict:
        text = (ticket["subject"] + " " + ticket["body"]).lower()
        labels = ticket.get("sample_labels") or {}
        if labels:
            dept = labels["department"]
            intent = labels["intent"]
            urgency = labels["urgency"]
            refund = labels["refund"]
            churn = labels["churn"]
            escalation = labels["escalation"]
        else:
            groups = [
                ("Billing", ("charge", "invoice", "payment", "refund", "billed"), "Payment Problem"),
                ("Technical Support", ("error", "bug", "api", "outage", "crash", "broken", "down"), "Bug Report"),
                ("Account Support", ("login", "password", "account", "profile", "cancel"), "Account Change"),
                ("Sales", ("pricing", "quote", "demo", "trial", "contract", "plan"), "Sales Inquiry"),
            ]
            matches = [(d, i) for d, words, i in groups if any(w in text for w in words)]
            dept, intent = matches[0] if matches else ("General Support", "Product Question")
            if "refund" in text and not any(p in text for p in ("don't want a refund", "do not want a refund", "not asking for a refund")):
                intent = "Refund Request"
            elif "login" in text or "password" in text:
                intent = "Login Problem"
            elif "cancel" in text:
                intent = "Cancellation"
            refund = intent == "Refund Request"
            churn = any(w in text for w in ("cancel", "leav", "switch provider", "moving to another"))
            urgency = "Critical" if any(w in text for w in ("production", "outage", "all customers", "security breach")) else ("High" if churn or "blocked" in text else "Medium")
            escalation = urgency == "Critical" or churn
        ambiguous = any(w in text for w in ("maybe", "not sure", "unclear", "something feels", "don't know"))
        confidence = 0.49 if ambiguous else (0.77 if len(text) < 65 else 0.93)
        return {
            "department": dept, "department_confidence": confidence,
            "intent": intent, "intent_confidence": max(0.42, confidence - 0.03),
            "urgency": urgency, "urgency_confidence": 0.86,
            "frustration": 2 if churn else 0, "frustration_confidence": 0.78,
            "refund_probability": 0.96 if refund else 0.04,
            "churn_probability": 0.91 if churn else 0.06,
            "escalation_probability": 0.93 if escalation else 0.12,
            "model": "demo-simulation", "source": "simulation",
        }


def make_classifier():
    return DemoClassifier() if os.getenv("LAYADESK_MODE", "laya").lower() == "demo" else LayaClassifier()
