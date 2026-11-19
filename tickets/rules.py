"""
Business rules for tickets: the status workflow and response-time targets.

These live outside the model on purpose. They are plain data, so the same
definitions drive model validation, the admin's status dropdown, the bulk
actions and the context given to the form assistant.
"""

from datetime import datetime, timedelta

from django.db import models


class Status(models.TextChoices):
    NEW = "new", "New"
    OPEN = "open", "Open"
    PENDING = "pending", "Waiting on customer"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


# Where a ticket may go next from each status. Closed is final: a customer
# coming back after closure gets a new ticket, which keeps reporting honest.
TRANSITIONS: dict[str, frozenset[str]] = {
    Status.NEW: frozenset({Status.OPEN, Status.RESOLVED, Status.CLOSED}),
    Status.OPEN: frozenset({Status.PENDING, Status.RESOLVED}),
    Status.PENDING: frozenset({Status.OPEN, Status.RESOLVED}),
    Status.RESOLVED: frozenset({Status.OPEN, Status.CLOSED}),
    Status.CLOSED: frozenset(),
}

# Someone has to own a ticket that is being worked on or has been resolved.
REQUIRES_ASSIGNEE = frozenset({Status.OPEN, Status.PENDING, Status.RESOLVED})

# Statuses in which the response deadline still matters.
ACTIVE_STATUSES = frozenset({Status.NEW, Status.OPEN, Status.PENDING})

# Response deadline per priority, in hours from when the ticket was raised.
SLA_HOURS: dict[str, int] = {
    Priority.URGENT: 4,
    Priority.HIGH: 8,
    Priority.NORMAL: 24,
    Priority.LOW: 72,
}


def can_transition(current: str, target: str) -> bool:
    return target == current or target in TRANSITIONS[current]


def allowed_next_statuses(current: str) -> list[str]:
    """Statuses reachable from `current`, in the order they are declared."""
    return [s for s in Status.values if s in TRANSITIONS[current]]


def due_at_for(created_at: datetime, priority: str) -> datetime:
    return created_at + timedelta(hours=SLA_HOURS[priority])


def describe_workflow() -> str:
    """E.g. 'New: Open, Resolved, Closed; Open: Waiting on customer, Resolved; ...'."""
    parts = []
    for status in Status:
        targets = [Status(s).label for s in allowed_next_statuses(status)]
        parts.append(f"{status.label}: {', '.join(targets) or 'nothing (final)'}")
    return "; ".join(parts)


def describe_sla() -> str:
    """Human-readable summary, e.g. 'urgent 4h, high 8h, normal 24h, low 72h'."""
    return ", ".join(f"{Priority(p).label.lower()} {hours}h" for p, hours in SLA_HOURS.items())
