"""Regenerate the 100 hand-authored synthetic tickets used by the demo and evaluation."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dataset" / "tickets.csv"

# subject, body, intent, urgency, refund, churn, escalation
CASES = {
"Billing": [
 ("Duplicate March charge", "I was billed twice for March. Please refund the second charge to my card.", "Refund Request", "High", 1, 0, 0),
 ("Invoice total looks wrong", "Our invoice is higher than the agreed amount. Can you explain each line item?", "Payment Problem", "Medium", 0, 0, 0),
 ("Payment failed at checkout", "My company card keeps being declined although the bank says it is active.", "Payment Problem", "High", 0, 0, 0),
 ("Refund for accidental upgrade", "I upgraded by mistake today. Please refund the upgrade payment.", "Refund Request", "Medium", 1, 0, 0),
 ("Tax ID missing", "Could you add our tax ID to the latest invoice and send an updated copy?", "Payment Problem", "Low", 0, 0, 0),
 ("Charged after cancellation", "The account was cancelled last week but I was charged again. Refund this payment.", "Refund Request", "High", 1, 1, 1),
 ("Annual billing question", "Can you explain when the annual renewal will be billed and what it covers?", "Payment Problem", "Low", 0, 0, 0),
 ("Need receipt", "Please send the receipt for our July payment to our finance team.", "Payment Problem", "Low", 0, 0, 0),
 ("Wrong currency", "The invoice is in USD instead of EUR. Our finance team cannot process it before Friday.", "Payment Problem", "High", 0, 0, 0),
 ("Refund declined transaction", "A failed transaction still appears as posted on my statement. Please refund it.", "Refund Request", "High", 1, 0, 0),
 ("Billing issue again", "This is the third billing issue this month. Fix it or we're cancelling our plan.", "Payment Problem", "High", 0, 1, 1),
 ("No refund needed", "I don't want a refund. I only want to know why I was charged twice.", "Payment Problem", "Medium", 0, 0, 0),
 ("Update payment method", "Where can I replace the card used for my subscription invoices?", "Payment Problem", "Low", 0, 0, 0),
 ("Credit note request", "Our finance team needs a credit note for the duplicate charge, not a new invoice.", "Payment Problem", "Medium", 0, 0, 0),
 ("Unexpected seat charge", "Five seats were added without approval. Please reverse and refund the extra seat charge.", "Refund Request", "High", 1, 0, 0),
 ("Invoice overdue notice", "We paid yesterday but still received an overdue reminder. Please check the payment status.", "Payment Problem", "Medium", 0, 0, 0),
 ("Refund taking too long", "You approved my refund two weeks ago, and it still hasn't arrived. I need a human update today.", "Refund Request", "High", 1, 0, 1),
 ("PO number on invoice", "Please include purchase order PO-881 on future invoices.", "Payment Problem", "Low", 0, 0, 0),
 ("Charged after trial", "I thought the trial was free. Why was my card charged yesterday?", "Payment Problem", "Medium", 0, 0, 0),
 ("Enterprise billing dispute", "The enterprise renewal charge is incorrect and our CFO will cancel if this is not fixed today.", "Payment Problem", "High", 0, 1, 1),
],
"Technical Support": [
 ("Production API down", "Our production API has been down for 45 minutes and customers cannot checkout.", "Bug Report", "Critical", 0, 0, 1),
 ("Dashboard won't load", "The dashboard stays blank after login on Chrome. I can reproduce it every time.", "Bug Report", "High", 0, 0, 0),
 ("Webhook delivery failures", "Our order webhooks are returning 500 errors since this morning.", "Bug Report", "High", 0, 0, 0),
 ("Mobile app crashes", "The Android app crashes when I open the reports tab.", "Bug Report", "Medium", 0, 0, 0),
 ("Export stuck", "CSV exports have been stuck at 0% for the last hour.", "Bug Report", "Medium", 0, 0, 0),
 ("Integration timeout", "The Salesforce integration times out on every sync job.", "Bug Report", "High", 0, 0, 0),
 ("Search results missing", "Search does not show tickets created today even though they appear in the queue.", "Bug Report", "Medium", 0, 0, 0),
 ("Email notifications delayed", "Ticket notification emails are arriving several hours late.", "Bug Report", "Medium", 0, 0, 0),
 ("Checkout outage", "Checkout is failing for all of our customers in production right now.", "Bug Report", "Critical", 0, 0, 1),
 ("Report chart error", "The weekly report chart shows an error when filtering by team.", "Bug Report", "Low", 0, 0, 0),
 ("API rate limit issue", "We receive 429 responses well below our published rate limit.", "Bug Report", "High", 0, 0, 0),
 ("Broken attachment previews", "PDF attachments now open as empty pages in the helpdesk app.", "Bug Report", "Medium", 0, 0, 0),
 ("SSO outage", "All enterprise staff are locked out after today's SSO update. This blocks production operations.", "Bug Report", "Critical", 0, 0, 1),
 ("Calendar sync duplicates", "Each booking appears twice after connecting our calendar account.", "Bug Report", "Medium", 0, 0, 0),
 ("Lost unsaved form", "The editor resets while I type and deletes the ticket draft.", "Bug Report", "High", 0, 0, 0),
 ("Slow response times", "Page loads now take over 30 seconds for every agent on our team.", "Bug Report", "High", 0, 0, 0),
 ("Security alert", "We can see another company's private ticket data in our dashboard. Please investigate immediately.", "Bug Report", "Critical", 0, 0, 1),
 ("Timezone bug", "Scheduled automations fire one hour early after daylight saving changes.", "Bug Report", "Medium", 0, 0, 0),
 ("Upload error", "Image uploads fail with a generic error only on Safari.", "Bug Report", "Medium", 0, 0, 0),
 ("Intermittent 502s", "The API returns 502 errors several times per minute and our team cannot finish orders.", "Bug Report", "Critical", 0, 0, 1),
],
"Account Support": [
 ("Reset password link expired", "Every password reset link says expired immediately after I request it.", "Login Problem", "High", 0, 0, 0),
 ("Change profile picture", "How can I change my profile picture in account settings?", "Account Change", "Low", 0, 0, 0),
 ("Cannot sign in", "I cannot log in after changing my email address yesterday.", "Login Problem", "High", 0, 0, 0),
 ("Update company name", "Please help change the company name shown on our workspace profile.", "Account Change", "Low", 0, 0, 0),
 ("Remove former employee", "A former employee still has access. Please help revoke their account today.", "Account Change", "High", 0, 0, 1),
 ("Cancel subscription", "Please cancel our subscription at the end of the current term.", "Cancellation", "Medium", 0, 1, 0),
 ("Authenticator lost", "I replaced my phone and cannot use my old two-factor authentication codes.", "Login Problem", "High", 0, 0, 0),
 ("Transfer ownership", "The current workspace owner left. We need to transfer ownership to a new admin.", "Account Change", "Medium", 0, 0, 0),
 ("Delete old workspace", "How do I close an unused workspace after exporting the data?", "Account Change", "Low", 0, 0, 0),
 ("Change contact email", "Please update the contact email for our account from the old address.", "Account Change", "Low", 0, 0, 0),
 ("Team invite missing", "My teammate never got the invitation to join our account.", "Account Change", "Medium", 0, 0, 0),
 ("Cancel after repeated problems", "We've had enough account issues and want to cancel before renewal.", "Cancellation", "High", 0, 1, 1),
 ("Locked after login attempts", "My account says locked after several failed sign-ins. Can an agent restore access?", "Login Problem", "Medium", 0, 0, 0),
 ("Change account language", "Where can I set my profile language to Indonesian?", "Account Change", "Low", 0, 0, 0),
 ("Merge two accounts", "I accidentally created two accounts and need the workspaces merged.", "Account Change", "Medium", 0, 0, 0),
 ("Cannot access admin panel", "I am the owner but the admin page tells me I lack permissions.", "Login Problem", "High", 0, 0, 0),
 ("Pause subscription", "Can I pause our subscription for two months instead of cancelling it?", "Account Change", "Low", 0, 0, 0),
 ("Update notification settings", "I need to turn off email notifications for resolved tickets.", "Account Change", "Low", 0, 0, 0),
 ("Close my account", "I want to close my account when my plan expires next month.", "Cancellation", "Medium", 0, 1, 0),
 ("Login code never arrives", "The one-time login code does not arrive at my email, and I have a meeting soon.", "Login Problem", "High", 0, 0, 0),
],
"Sales": [
 ("Enterprise pricing", "Could you send pricing for an enterprise plan with 200 agents?", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Book a product demo", "Our operations team would like a live product demo next week.", "Sales Inquiry", "Low", 0, 0, 0),
 ("Trial extension", "Can you extend our trial by one week while we finish testing?", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Volume discount", "Do you offer a discount for more than 100 seats?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Security questionnaire", "Before buying, procurement needs your security questionnaire and compliance details.", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Contract deadline", "We need a signed quote by Friday or procurement cannot approve this quarter.", "Sales Inquiry", "High", 0, 0, 0),
 ("Compare plans", "What is included in Pro versus Enterprise?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Nonprofit plan", "Is there special pricing for a small nonprofit organization?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Annual contract quote", "Please provide a formal annual quote for 50 users and SSO.", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Purchase order process", "Can our company buy through a purchase order instead of a card?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Onboarding package", "Do you offer paid onboarding for a 40-person support team?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Reseller inquiry", "We want to resell this platform to clients in our region. Who can discuss terms?", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Add seats pricing", "How much would it cost to add 25 more agent seats next month?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Data residency option", "Is EU data residency available on your enterprise contract?", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Pilot proposal", "Can your sales team prepare a pilot proposal for three departments?", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Implementation timeline", "How long does implementation take for an organization with 500 agents?", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Renewal negotiation", "We are reviewing vendors before renewal. Please share your best offer.", "Sales Inquiry", "High", 0, 1, 0),
 ("Invoice billing for new plan", "Before purchasing, do you allow invoice billing on the enterprise plan?", "Sales Inquiry", "Low", 0, 0, 0),
 ("Custom SLA quote", "Please quote a contract with a one-hour critical incident SLA.", "Sales Inquiry", "Medium", 0, 0, 0),
 ("Request sales call", "I run a growing support team and would like to talk about pricing options.", "Sales Inquiry", "Low", 0, 0, 0),
],
"General Support": [
 ("Getting started guide", "Where can I find a beginner guide for setting up my first support queue?", "Product Question", "Low", 0, 0, 0),
 ("Feature suggestion: dark mode", "It would be great to have a dark theme for the dashboard.", "Feature Request", "Low", 0, 0, 0),
 ("Keyboard shortcuts", "Is there a list of keyboard shortcuts for ticket navigation?", "Product Question", "Low", 0, 0, 0),
 ("Suggest saved views", "Could you add shared saved views for teams in a future release?", "Feature Request", "Low", 0, 0, 0),
 ("Help center link", "Please point me to the help center article about ticket tags.", "Product Question", "Low", 0, 0, 0),
 ("Training resources", "Do you have training videos for new support agents?", "Product Question", "Low", 0, 0, 0),
 ("Feedback on navigation", "The new navigation feels confusing. I would like to share feedback with the product team.", "Other", "Low", 0, 0, 0),
 ("Feature request: custom fields", "We need custom fields on ticket forms for internal reporting.", "Feature Request", "Low", 0, 0, 0),
 ("Status page location", "Where do you publish incident updates and service status?", "Product Question", "Low", 0, 0, 0),
 ("How routing works", "Can you explain how an incoming ticket reaches the right queue?", "Product Question", "Low", 0, 0, 0),
 ("Language availability", "Which languages are supported in the customer portal?", "Product Question", "Low", 0, 0, 0),
 ("Feature request: bulk actions", "Please add a way to archive many resolved tickets at once.", "Feature Request", "Low", 0, 0, 0),
 ("Community forum", "Is there a community forum where other admins share workflows?", "Product Question", "Low", 0, 0, 0),
 ("Public roadmap", "Do you have a public product roadmap that customers can view?", "Product Question", "Low", 0, 0, 0),
 ("Feature idea: mobile widgets", "A mobile home screen widget for open tickets would help our agents.", "Feature Request", "Low", 0, 0, 0),
 ("Accessibility feedback", "The contrast in the settings page is hard to read. Please pass this feedback on.", "Other", "Low", 0, 0, 0),
 ("Documentation typo", "I found a typo in the automation guide. Where should I report it?", "Other", "Low", 0, 0, 0),
 ("Best practices", "What are good practices for organizing a small team's helpdesk?", "Product Question", "Low", 0, 0, 0),
 ("Feature request: templates", "Can you add response templates shared across all workspaces?", "Feature Request", "Low", 0, 0, 0),
 ("General question", "I'm not sure which settings page controls ticket visibility. Can someone point me there?", "Product Question", "Low", 0, 0, 0),
]}

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["ticket_id", "subject", "body", "customer_id", "customer_tier", "previous_ticket_count",
              "product", "source_channel", "created_at", "department", "intent", "urgency", "refund", "churn", "escalation"]
    rows = []
    base = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
    for department, cases in CASES.items():
        assert len(cases) == 20, department
        for subject, body, intent, urgency, refund, churn, escalation in cases:
            i = len(rows) + 1
            rows.append({"ticket_id": f"TCK-{i:04d}", "subject": subject, "body": body,
                         "customer_id": f"CUS-{(i * 17) % 83 + 1:04d}",
                         "customer_tier": "Enterprise" if i % 8 == 0 else ("Pro" if i % 3 == 0 else "Standard"),
                         "previous_ticket_count": (i * 7) % 6, "product": "LayaDesk",
                         "source_channel": ["Email", "Web", "Chat"][i % 3],
                         "created_at": (base - timedelta(minutes=i * 13)).isoformat(),
                         "department": department, "intent": intent, "urgency": urgency,
                         "refund": str(bool(refund)).lower(), "churn": str(bool(churn)).lower(),
                         "escalation": str(bool(escalation)).lower()})
    assert len(rows) == 100
    with OUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")

if __name__ == "__main__":
    main()
