"""Sample text for the seed command, grouped by the kind of request."""

from tickets.models import Agent

TAGS = [
    "2fa",
    "account-deletion",
    "api",
    "billing",
    "bug",
    "data-export",
    "email-delivery",
    "feature-request",
    "integration",
    "invoice",
    "login",
    "mobile-app",
    "onboarding",
    "outage",
    "password-reset",
    "performance",
    "permissions",
    "refund",
]

# Each category: which team usually handles it, its tags, and subject and
# description templates. Placeholders are filled in by the seed command.
CATEGORIES = [
    {
        "team": Agent.Team.ACCOUNTS,
        "weight": 18,
        "tags": ["login", "password-reset", "2fa", "permissions"],
        "subjects": [
            "Can't log in after resetting my password",
            "Two-factor codes are always rejected",
            "Locked out after too many attempts",
            "SSO login keeps sending me back to the sign-in page",
            "Password reset email never arrives",
            "New team member can't see the shared projects",
        ],
        "descriptions": [
            "Since {date} I get 'invalid credentials' every time, even right after a reset. "
            "I'm using {browser}. Our whole {dept} team relies on this account.",
            "I've tried three times today. The page just reloads with no error. "
            "My colleague on the same network can log in fine.",
            "We switched our identity provider last week and since then nobody at "
            "{company} can sign in through SSO.",
        ],
    },
    {
        "team": Agent.Team.BILLING,
        "weight": 22,
        "tags": ["billing", "invoice", "refund"],
        "subjects": [
            "Charged twice for this month's subscription",
            "Need a copy of invoice {invoice}",
            "Refund for unused seats",
            "Card declined on renewal but bank says it's fine",
            "VAT number missing from our invoices",
            "Please downgrade our plan before the next billing date",
        ],
        "descriptions": [
            "Our card statement shows two charges of {amount} on {date}. "
            "Please refund the duplicate.",
            "Our finance team needs invoice {invoice} re-issued with the company "
            "name {company} and our VAT number.",
            "We reduced the team from {seats_before} to {seats_after} people last month "
            "and would like the unused seats refunded.",
        ],
    },
    {
        "team": Agent.Team.TECHNICAL,
        "weight": 34,
        "tags": ["bug", "api", "performance", "mobile-app", "integration", "data-export", "outage"],
        "subjects": [
            "CSV export times out for large reports",
            "Dashboard charts don't load in Safari",
            "API returns 500 on the orders endpoint",
            "Webhook deliveries delayed by several hours",
            "Mobile app crashes when uploading a photo",
            "Search doesn't find records created today",
            "Calendar sync stopped working",
            "Pages are very slow since this morning",
        ],
        "descriptions": [
            "Steps: open Reports, pick the last 12 months, click Export. After about "
            "a minute it fails with error {error_code}. Smaller ranges work.",
            "Started around {date}. Request ID {request_id}. We haven't changed "
            "anything on our side and it affects every user at {company}.",
            "On {device}, the app closes as soon as the upload starts. Reinstalling didn't help.",
            "Our integration logs show {error_code} responses roughly one in five "
            "requests. Happy to share more logs if useful.",
        ],
    },
    {
        "team": Agent.Team.ACCOUNTS,
        "weight": 11,
        "tags": ["account-deletion", "permissions", "onboarding"],
        "subjects": [
            "Transfer account ownership to a new admin",
            "Add {seats_after} seats to our plan",
            "Please delete my account and personal data",
            "Change the company name on our account",
            "Merge two workspaces into one",
        ],
        "descriptions": [
            "Our current owner is leaving {company} at the end of the month. "
            "Ownership should move to {colleague}.",
            "Under GDPR I'd like my account and all associated personal data deleted.",
            "We accidentally created two workspaces. Can they be merged without losing history?",
        ],
    },
    {
        "team": Agent.Team.GENERAL,
        "weight": 15,
        "tags": ["feature-request", "onboarding", "email-delivery"],
        "subjects": [
            "How do I set up roles for my team?",
            "Feature request: scheduled reports",
            "Where can I find the audit log?",
            "Can we book an onboarding call?",
            "Notification emails go to spam",
            "Question about data retention",
        ],
        "descriptions": [
            "We're rolling this out to {seats_after} people at {company} and want to "
            "make sure permissions are right from day one.",
            "It would save our {dept} team a lot of time if reports could be emailed "
            "automatically every Monday.",
            "Several colleagues say the notification emails land in their spam folder. "
            "We use {email_provider}.",
        ],
    },
]

AGENT_FIRST_REPLIES = [
    "Hi {first}, thanks for getting in touch. I'm looking into this now.",
    "Thanks for the details, {first}. I'll check this and get back to you today.",
    "Hi {first}, sorry about the trouble. I've started investigating.",
]

AGENT_QUESTIONS = [
    "Could you send a screenshot of the error and roughly when it happened?",
    "Which browser and version are you using?",
    "Can you confirm the email address on the account so I can verify ownership?",
    "Does this happen for everyone on your team or just some users?",
    "Could you share the request ID from the error page?",
]

AGENT_PROGRESS = [
    "I've reproduced the issue and passed it to our engineering team.",
    "Thanks, that helps. I can see the problem in our logs.",
    "I've made the change on our side. It may take a few minutes to apply.",
]

AGENT_RESOLUTIONS = [
    "This should now be fixed. Could you try again and let me know?",
    "I've issued the refund. It should show on your statement within 5 to 10 business days.",
    "Done, the changes are live on your account.",
    "Engineering deployed a fix this morning. Everything should work as expected now.",
]

CUSTOMER_REPLIES = [
    "Thanks, screenshot attached.",
    "It's still happening on my side, unfortunately.",
    "Any update on this? It's blocking our team.",
    "We're using the latest Chrome on Windows.",
    "Yes, it happens for everyone here.",
]

CUSTOMER_THANKS = [
    "That worked, thank you!",
    "All good now, thanks for the quick help.",
    "Confirmed, it's fixed. Appreciate it.",
]

INTERNAL_NOTES = [
    "Customer is on the legacy plan; check pricing before offering a discount.",
    "Looks like the same root cause as the export timeouts last week.",
    "Escalated to tier 2.",
    "Waiting on the fix in the next release.",
    "Verified identity over the phone before making changes.",
    "Large account, keep the account manager in the loop.",
]

BROWSERS = ["Chrome 131", "Firefox 133", "Safari 18", "Edge 131"]
DEVICES = ["iPhone 15", "Pixel 8", "Galaxy S24", "iPad Air"]
DEPARTMENTS = ["finance", "operations", "sales", "support", "marketing", "engineering"]
EMAIL_PROVIDERS = ["Outlook", "Gmail", "Proton Mail", "our own mail server"]
ERROR_CODES = [
    "504 Gateway Timeout",
    "500 Internal Server Error",
    "ERR_TIMEOUT",
    "429 Too Many Requests",
]
