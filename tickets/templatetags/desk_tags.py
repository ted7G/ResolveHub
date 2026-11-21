from datetime import timedelta

from django import template
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from tickets import dashboard, rules
from tickets.models import Ticket
from tickets.rules import Status

register = template.Library()

_ACTIVE = ",".join(sorted(rules.ACTIVE_STATUSES))

# Header navigation, in the order people use it. Other admin sections (login
# lockout logs, linked GitHub accounts) stay on the dashboard, so a superuser's
# header doesn't fill up with tables they rarely open.
_NAV_ORDER = [
    "tickets.ticket",
    "tickets.customer",
    "tickets.agent",
    "tickets.tag",
    "auth.user",
    "auth.group",
]


def _greeting(now):
    hour = timezone.localtime(now).hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


@register.inclusion_tag("admin/tickets/top_nav.html", takes_context=True)
def top_nav(context):
    """
    Header links to every admin section the user can open, built from the
    admin's own `available_apps`, so permissions decide what is shown.
    """
    request = context["request"]
    index_url = reverse("admin:index")
    entries = []
    for app in context.get("available_apps", []):
        for model in app["models"]:
            url = model.get("admin_url")
            if not url:
                continue
            key = f"{app['app_label']}.{model['object_name'].lower()}"
            if key not in _NAV_ORDER:
                continue
            entries.append(
                {
                    "name": model["name"],
                    "object_name": model["object_name"],
                    "url": url,
                    "current": request.path.startswith(url),
                    "order": _NAV_ORDER.index(key),
                }
            )
    entries.sort(key=lambda entry: entry["order"])
    return {
        "index_url": index_url,
        "on_index": request.path == index_url,
        "entries": entries,
    }


@register.inclusion_tag("admin/tickets/desk_summary.html", takes_context=True)
def desk_summary(context):
    """
    The numbers at the top of the dashboard, each linking to the ticket list
    filtered to match. One aggregate query, whatever the size of the desk.
    """
    user = context["request"].user
    now = timezone.now()
    summary = {"greeting": _greeting(now), "user": user, "now": now}
    if not user.has_perm("tickets.view_ticket"):
        return summary

    active = Q(status__in=rules.ACTIVE_STATUSES)
    counts = Ticket.objects.aggregate(
        new=Count("pk", filter=Q(status=Status.NEW)),
        open=Count("pk", filter=Q(status=Status.OPEN)),
        pending=Count("pk", filter=Q(status=Status.PENDING)),
        overdue=Count("pk", filter=active & Q(due_at__lt=now)),
        due_soon=Count(
            "pk", filter=active & Q(due_at__gte=now, due_at__lt=now + timedelta(hours=24))
        ),
        unassigned=Count("pk", filter=active & Q(assignee__isnull=True)),
        mine=Count("pk", filter=active & Q(assignee__user_id=user.pk)),
    )
    counts["active"] = counts["new"] + counts["open"] + counts["pending"]

    changelist = reverse("admin:tickets_ticket_changelist")
    summary.update(
        counts=counts,
        show_mine=user.has_perm("tickets.change_ticket"),
        links={
            "active": f"{changelist}?status__in={_ACTIVE}",
            "overdue": f"{changelist}?deadline=overdue",
            "due_soon": f"{changelist}?deadline=due_soon",
            "unassigned": f"{changelist}?assigned=unassigned&status__in={_ACTIVE}",
            "mine": f"{changelist}?assigned=me&status__in={_ACTIVE}",
        },
    )
    return summary


@register.simple_tag(takes_context=True)
def desk_charts(context):
    """Chart data for the dashboard, or None for people who can't see tickets."""
    user = context["request"].user
    if not user.has_perm("tickets.view_ticket"):
        return None
    now = timezone.now()
    return {
        "flow": dashboard.ticket_flow(),
        "priority": dashboard.priority_load(now),
        "workload": dashboard.agent_workload(now),
    }
