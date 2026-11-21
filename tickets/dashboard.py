"""
Numbers and chart geometry for the admin dashboard.

Each chart is a handful of aggregate queries; the template only places what
is computed here (percentages for positions, tick labels, link targets).
"""

from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from . import rules
from .models import Agent, Ticket
from .rules import Priority

FLOW_DAYS = 14
WORKLOAD_ROWS = 8
_ACTIVE_PARAM = ",".join(sorted(rules.ACTIVE_STATUSES))


def nice_ceiling(value, steps=4):
    """Smallest round axis maximum >= value that splits into `steps` whole ticks."""
    if value <= steps:
        return steps
    raw_step = value / steps
    magnitude = 10 ** (len(str(int(raw_step))) - 1)
    for multiple in (1, 2, 2.5, 3, 4, 5, 6, 8, 10):
        step = multiple * magnitude
        if step >= raw_step and step == int(step):
            return int(step * steps)
    return int(10 * magnitude * steps)


def _ticks(maximum, steps=4):
    return [{"value": maximum * i // steps, "bottom": 100 * i / steps} for i in range(steps + 1)]


def ticket_flow(days=FLOW_DAYS):
    """Tickets created and resolved per day over the last `days` days."""
    today = timezone.localdate()
    start_day = today - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(start_day, time.min))

    def per_day(field):
        rows = (
            Ticket.objects.filter(**{f"{field}__gte": start})
            .annotate(day=TruncDate(field))
            .values("day")
            .annotate(n=Count("pk"))
            .values_list("day", "n")
        )
        return dict(rows)

    created, resolved = per_day("created_at"), per_day("resolved_at")
    dates = [start_day + timedelta(days=i) for i in range(days)]
    maximum = nice_ceiling(max([*created.values(), *resolved.values(), 1]))

    points = []
    for index, day in enumerate(dates):
        made, done = created.get(day, 0), resolved.get(day, 0)
        points.append(
            {
                "date": day,
                "created": made,
                "resolved": done,
                "x": 100 * index / max(days - 1, 1),
                "created_y": 100 - 100 * made / maximum,
                "resolved_y": 100 - 100 * done / maximum,
                # Every second day is labelled; every fourth on narrow screens.
                "label": index % 2 == (days - 1) % 2,
                "label_narrow": index % 4 == (days - 1) % 4,
                # Today is still filling up; say so rather than show a "drop".
                "is_today": day == today,
            }
        )
    return {
        "points": points,
        "ticks": _ticks(maximum),
        "created_line": " ".join(f"{p['x']:.2f},{p['created_y']:.2f}" for p in points),
        "resolved_line": " ".join(f"{p['x']:.2f},{p['resolved_y']:.2f}" for p in points),
        "created_total": sum(created.get(d, 0) for d in dates),
        "resolved_total": sum(resolved.get(d, 0) for d in dates),
        "last": points[-1],
        "days": days,
        "zone": timezone.get_current_timezone_name(),
    }


def _split_bars(rows, maximum):
    """Add bar widths (percent of the axis) for the on-track and overdue parts."""
    for row in rows:
        row["on_track"] = row["active"] - row["overdue"]
        row["on_track_width"] = 100 * row["on_track"] / maximum
        row["overdue_width"] = 100 * row["overdue"] / maximum
    return rows


def priority_load(now):
    """Active tickets per priority, split into on track and overdue."""
    counts = {
        row["priority"]: row
        for row in Ticket.objects.active()
        .values("priority")
        .annotate(active=Count("pk"), overdue=Count("pk", filter=Q(due_at__lt=now)))
    }
    changelist = reverse("admin:tickets_ticket_changelist")
    rows = []
    for priority in (Priority.URGENT, Priority.HIGH, Priority.NORMAL, Priority.LOW):
        found = counts.get(priority, {"active": 0, "overdue": 0})
        rows.append(
            {
                "label": priority.label,
                "active": found["active"],
                "overdue": found["overdue"],
                "url": f"{changelist}?priority__exact={priority.value}&status__in={_ACTIVE_PARAM}",
            }
        )
    maximum = nice_ceiling(max([r["active"] for r in rows] + [1]))
    return {"rows": _split_bars(rows, maximum), "ticks": _ticks(maximum)}


def agent_workload(now, limit=WORKLOAD_ROWS):
    """The agents with the most active tickets, split into on track and overdue."""
    active = Q(tickets__status__in=rules.ACTIVE_STATUSES)
    agents = (
        Agent.objects.select_related("user")
        .annotate(
            active=Count("tickets", filter=active),
            overdue=Count("tickets", filter=active & Q(tickets__due_at__lt=now)),
        )
        .filter(active__gt=0)
        .order_by("-active", "user__first_name")[:limit]
    )
    changelist = reverse("admin:tickets_ticket_changelist")
    rows = [
        {
            "label": str(agent),
            "active": agent.active,
            "overdue": agent.overdue,
            "url": f"{changelist}?assignee__id__exact={agent.pk}&status__in={_ACTIVE_PARAM}",
        }
        for agent in agents
    ]
    maximum = nice_ceiling(max([r["active"] for r in rows] + [1]))
    return {"rows": _split_bars(rows, maximum), "ticks": _ticks(maximum)}
