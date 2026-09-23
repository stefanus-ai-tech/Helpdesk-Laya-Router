"""Typed Laya questions for a single-pass helpdesk decision."""

QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which support department should own this customer's primary request?",
        "criteria": {
            "Billing": "charges, invoices, payments, refunds, tax, or payment methods",
            "Technical Support": "outages, defects, API, integrations, website, or mobile app issues",
            "Account Support": "login, access, profile, account settings, or cancellation",
            "Sales": "pricing, plans, contracts, trials, demos, or purchasing",
            "General Support": "general guidance, documentation, feedback, or other help",
        },
    },
    "intent": {
        "type": "choice",
        "instructions": "What is the customer's main intent? Choose only the closest option.",
        "criteria": {
            "Refund Request": "explicitly asks for money back or a refund",
            "Payment Problem": "charge, billing, invoice, or failed payment question without a refund request",
            "Bug Report": "broken feature, error, outage, or unexpected software behavior",
            "Login Problem": "cannot sign in, password reset, or authentication problem",
            "Account Change": "update profile, account information, or account settings",
            "Cancellation": "asks to cancel a plan or close an account",
            "Feature Request": "suggests a new product capability or improvement",
            "Product Question": "asks how a product or feature works",
            "Sales Inquiry": "asks about pricing, plan, demo, quote, or purchase",
            "Other": "none of the above intents fit",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgently must support respond to the customer's situation?",
        "criteria": [
            "Low: routine information or suggestion, no disruption",
            "Medium: inconvenience affecting one person, no serious deadline",
            "High: major workflow blocked, repeated issue, or imminent deadline",
            "Critical: production outage, many customers blocked, security incident, or immediate severe loss",
        ],
    },
    "frustration": {
        "type": "score",
        "instructions": "How frustrated does the customer sound?",
        "criteria": [
            "Neutral: calm and informational",
            "Mildly Frustrated: inconvenience or disappointment",
            "Frustrated: repeated problem or strong complaint",
            "Highly Frustrated: angry, threatening, or demanding immediate action",
        ],
    },
    "refund_requested": {
        "type": "noul",
        "instructions": "Does the customer explicitly request a refund? A mention of refund without requesting it means false.",
    },
    "churn_risk": {
        "type": "noul",
        "instructions": "Does the customer say they may cancel, leave, or stop using the service?",
    },
    "human_escalation": {
        "type": "noul",
        "instructions": "Does this case need prompt attention from a human or senior support agent?",
    },
}
