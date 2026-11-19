from datetime import UTC, datetime, timedelta

import pytest

from tickets import rules
from tickets.rules import Priority, Status


def test_every_status_has_a_transition_entry():
    assert set(rules.TRANSITIONS) == set(Status.values)


def test_closed_is_final():
    assert rules.allowed_next_statuses(Status.CLOSED) == []
    assert not rules.can_transition(Status.CLOSED, Status.OPEN)


def test_staying_in_the_same_status_is_always_allowed():
    for status in Status.values:
        assert rules.can_transition(status, status)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (Status.NEW, Status.OPEN, True),
        (Status.OPEN, Status.PENDING, True),
        (Status.PENDING, Status.OPEN, True),
        (Status.RESOLVED, Status.OPEN, True),
        (Status.RESOLVED, Status.CLOSED, True),
        (Status.OPEN, Status.CLOSED, False),
        (Status.PENDING, Status.NEW, False),
        (Status.OPEN, Status.NEW, False),
    ],
)
def test_transitions(current, target, allowed):
    assert rules.can_transition(current, target) is allowed


@pytest.mark.parametrize(
    ("priority", "hours"),
    [(Priority.URGENT, 4), (Priority.HIGH, 8), (Priority.NORMAL, 24), (Priority.LOW, 72)],
)
def test_due_at_for(priority, hours):
    created = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

    assert rules.due_at_for(created, priority) == created + timedelta(hours=hours)


def test_describe_sla_mentions_every_priority():
    assert rules.describe_sla() == "urgent 4h, high 8h, normal 24h, low 72h"
