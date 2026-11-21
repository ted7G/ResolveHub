from django import template
from django.urls import reverse
from django.utils.text import capfirst

register = template.Library()

# What the panel says and suggests, by the kind of page it is opened on.
PAGES = {
    "form": {
        "toggle_label": "Help with this form",
        "hint": "Ask what a field means, how to fill it in, or why something isn't allowed.",
        "placeholder": "e.g. Why can't I set this ticket to Closed?",
        "suggestions": {
            "tickets.ticket": [
                "Which status should I choose next?",
                "How do I pick the right priority?",
                "Can I assign this ticket to a colleague?",
            ],
        },
        "default_suggestions": ["Which fields are required?", "What does each field mean?"],
    },
    "list": {
        "toggle_label": "Ask about this list",
        "hint": "Ask how to find, filter or update records on this list.",
        "placeholder": "e.g. How do I find my overdue tickets?",
        "suggestions": {
            "tickets.ticket": [
                "How do I find my overdue tickets?",
                "How do I close several tickets at once?",
                "What does the deadline column mean?",
            ],
        },
        "default_suggestions": ["How do I search this list?", "What can I change here?"],
    },
    "general": {
        "toggle_label": "Ask AI",
        "hint": "Ask how the desk works: statuses, deadlines, roles and where to find things.",
        "placeholder": "e.g. What counts as overdue?",
        "suggestions": {},
        "default_suggestions": [
            "What do the numbers on the dashboard mean?",
            "What can my role do?",
            "How does the ticket workflow go?",
        ],
    },
}


@register.inclusion_tag("assistant/widget.html", takes_context=True)
def assistant_widget(context):
    """
    The assistant panel, on every admin page for signed-in staff. It knows
    which kind of page it is on: a form (field-level help), a list (search,
    filters, bulk actions) or anything else (the desk in general).
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if (
        not context.get("has_permission")
        or context.get("is_popup")
        or user is None
        or not user.is_staff
    ):
        return {"show": False}

    opts = context.get("opts")
    original = context.get("original")
    if opts is not None and context.get("adminform") is not None:
        page, scope = "form", f"{capfirst(opts.verbose_name)} form"
    elif opts is not None and context.get("cl") is not None:
        page, scope = "list", f"{capfirst(opts.verbose_name_plural)} list"
    else:
        page, scope, opts = "general", "Help desk", None

    copy = PAGES[page]
    model = opts.label_lower if opts is not None else ""
    return {
        "show": True,
        "endpoint": reverse("assistant:ask"),
        "page": page,
        "scope": scope,
        "model": model,
        "object_id": original.pk if page == "form" and original is not None else "",
        "toggle_label": copy["toggle_label"],
        "hint": copy["hint"],
        "placeholder": copy["placeholder"],
        "suggestions": copy["suggestions"].get(model, copy["default_suggestions"]),
    }
