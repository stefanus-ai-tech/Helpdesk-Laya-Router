from __future__ import annotations

import re
from typing import Any

DEPARTMENTS = ("Billing", "Technical Support", "Account Support", "Sales", "General Support")
INTENTS = (
    "Refund Request", "Payment Problem", "Bug Report", "Login Problem", "Account Change",
    "Cancellation", "Feature Request", "Product Question", "Sales Inquiry", "Other",
)
URGENCIES = ("Low", "Medium", "High", "Critical")


def decide(prediction: dict[str, Any], customer_tier: str = "Standard", text: str = "") -> dict[str, Any]:
    """Advisory routing only. No refund, cancellation, or account mutation."""
    confidence = float(prediction["department_confidence"])
    urgency = prediction["urgency"]
    message = text.lower()
    negated_refund = bool(re.search(r"\b(?:don't|do not|not)\s+(?:want|need|asking for)\s+(?:a\s+)?refund\b", message))
    explicit_exit = bool(re.search(r"\b(?:cancel\w*|leav\w*|switch\w*|moving to another provider)\b", message))
    negated_exit = bool(re.search(r"\b(?:don't|do not|not)\s+(?:want|plan|intend)\s+to\s+(?:cancel|leave|switch)\b", message))
    widespread = bool(re.search(r"\b(?:production|all (?:of our )?(?:customers|users|staff|agents))\b", message))
    service_failure = bool(re.search(r"\b(?:down|outage|failing|locked out|cannot checkout|blocks? production)\b", message))
    cross_tenant_exposure = bool(re.search(r"\b(?:another company|other customer).*(?:private|data)\b", message))
    transaction_failure = bool(re.search(r"\b(?:api|service).*(?:5\d\d|server error).*(?:cannot|can't|blocked)\b", message))
    critical_policy = (widespread and service_failure) or cross_tenant_exposure or transaction_failure
    tags = []
    if prediction["refund_probability"] >= 0.80 and not negated_refund:
        tags.append("refund-request")
    if prediction["churn_probability"] >= 0.80:
        tags.append("churn-risk")
    if urgency == "Critical":
        tags.append("p1-critical")
    if prediction["escalation_probability"] >= 0.85:
        tags.append("senior-review")

    immediate = urgency == "Critical" and customer_tier.lower() == "enterprise"
    if immediate:
        tags.append("enterprise-escalation")

    if confidence < 0.60:
        status = "NEEDS_REVIEW"
        gate = "manual_triage"
        queue = "Human Triage"
    elif confidence < 0.85:
        status = "NEEDS_REVIEW"
        gate = "human_confirmation"
        queue = prediction["department"] + " · Confirm"
    else:
        status = "AUTO_ROUTED"
        gate = "auto_route"
        queue = prediction["department"]

    # A critical case always needs human attention, even with high model confidence.
    if urgency == "Critical" or immediate:
        status = "NEEDS_REVIEW"
        gate = "critical_escalation"
        queue = "Senior Support"
    elif prediction["escalation_probability"] >= 0.85:
        status = "NEEDS_REVIEW"
        gate = "senior_confirmation"
        queue = prediction["department"] + " · Senior Review"

    # Deterministic safety checks do not alter or masquerade as model probabilities.
    if explicit_exit and not negated_exit and urgency != "Critical":
        status = "NEEDS_REVIEW"
        gate = "policy_escalation"
        queue = prediction["department"] + " · Senior Review"
        tags.append("cancellation-language-review")
    if negated_refund and prediction["refund_probability"] >= 0.80 and gate not in ("critical_escalation", "policy_escalation"):
        status = "NEEDS_REVIEW"
        gate = "refund_conflict"
        queue = "Human Triage"
        tags.append("refund-negation-review")
    if critical_policy and urgency != "Critical":
        status = "NEEDS_REVIEW"
        gate = "policy_critical"
        queue = "Senior Support"
        tags.append("p1-policy-override")

    return {
        "status": status,
        "gate": gate,
        "queue": queue,
        "priority": "P1" if critical_policy else {"Critical": "P1", "High": "P2", "Medium": "P3", "Low": "P4"}[urgency],
        "tags": tags,
    }
