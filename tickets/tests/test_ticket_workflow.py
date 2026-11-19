from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from tickets.models import Ticket
from tickets.rules import Priority, Status

pytestmark = pytest.mark.django_db


# --- SLA ---------------------------------------------------------------------


def test_due_at_is_set_from_priority_on_create(make_ticket):
    ticket = make_ticket(priority=Priority.HIGH)

    assert ticket.due_at == ticket.created_at + timedelta(hours=8)


def test_changing_priority_recalculates_due_at_from_creation_time(make_ticket):
    ticket = make_ticket(priority=Priority.LOW)

    ticket.priority = Priority.URGENT
    ticket.save()

    assert ticket.due_at == ticket.created_at + timedelta(hours=4)


def test_ticket_past_its_deadline_is_overdue_while_active(make_ticket, make_agent):
    created = timezone.now() - timedelta(hours=30)
    ticket = make_ticket(priority=Priority.NORMAL, created_at=created)

    assert ticket.is_overdue
    assert list(Ticket.objects.overdue()) == [ticket]

    ticket.assignee = make_agent()
    ticket.transition_to(Status.RESOLVED)

    assert not ticket.is_overdue
    assert not Ticket.objects.overdue().exists()


def test_ticket_within_its_deadline_is_not_overdue(make_ticket):
    ticket = make_ticket(priority=Priority.LOW)

    assert not ticket.is_overdue
    assert not Ticket.objects.overdue().exists()


# --- Status workflow ---------------------------------------------------------


def test_new_ticket_can_be_opened_once_assigned(make_ticket, make_agent):
    ticket = make_ticket()
    ticket.assignee = make_agent()

    ticket.transition_to(Status.OPEN)

    ticket.refresh_from_db()
    assert ticket.status == Status.OPEN


def test_opening_requires_an_assignee(make_ticket):
    ticket = make_ticket()

    with pytest.raises(ValidationError) as exc:
        ticket.transition_to(Status.OPEN)

    assert "assignee" in exc.value.message_dict
    assert ticket.status == Status.NEW


def test_invalid_transition_is_rejected_and_nothing_changes(make_ticket, make_agent):
    ticket = make_ticket(status=Status.OPEN, assignee=make_agent())

    with pytest.raises(ValidationError) as exc:
        ticket.transition_to(Status.CLOSED)

    assert "Allowed next: Waiting on customer, Resolved" in exc.value.message_dict["status"][0]
    assert ticket.status == Status.OPEN
    ticket.refresh_from_db()
    assert ticket.status == Status.OPEN


def test_closed_ticket_cannot_be_reopened(make_ticket):
    ticket = make_ticket()
    ticket.transition_to(Status.CLOSED)

    with pytest.raises(ValidationError, match="Closed is final"):
        ticket.transition_to(Status.OPEN)


def test_new_tickets_must_start_as_new_or_open(customer):
    ticket = Ticket(subject="x", description="y", customer=customer, status=Status.RESOLVED)

    with pytest.raises(ValidationError) as exc:
        ticket.full_clean()

    assert exc.value.message_dict["status"] == ["New tickets start as New or Open."]


def test_full_clean_checks_the_transition_against_the_saved_status(make_ticket, make_agent):
    """The admin form goes through full_clean, not transition_to."""
    ticket = make_ticket(status=Status.OPEN, assignee=make_agent())
    reloaded = Ticket.objects.get(pk=ticket.pk)
    reloaded.status = Status.NEW

    with pytest.raises(ValidationError) as exc:
        reloaded.full_clean()

    assert "status" in exc.value.message_dict


def test_resolve_reopen_and_close_keep_timestamps_consistent(make_ticket, make_agent):
    ticket = make_ticket(assignee=make_agent())

    ticket.transition_to(Status.RESOLVED)
    assert ticket.resolved_at is not None

    ticket.transition_to(Status.OPEN)
    assert ticket.resolved_at is None

    ticket.transition_to(Status.RESOLVED)
    ticket.transition_to(Status.CLOSED)
    assert ticket.resolved_at is not None
    assert ticket.closed_at is not None


def test_unavailable_agent_cannot_be_given_a_ticket(make_ticket, make_agent):
    ticket = make_ticket()
    ticket.assignee = make_agent(is_available=False)

    with pytest.raises(ValidationError) as exc:
        ticket.full_clean()

    assert "unavailable" in exc.value.message_dict["assignee"][0]


def test_agent_going_unavailable_keeps_existing_tickets_workable(make_ticket, make_agent):
    agent = make_agent()
    ticket = make_ticket(assignee=agent)
    agent.is_available = False
    agent.save()

    ticket.refresh_from_db()
    ticket.transition_to(Status.OPEN)

    assert ticket.status == Status.OPEN


def test_database_rejects_resolved_ticket_without_timestamp(make_ticket):
    ticket = make_ticket()

    with pytest.raises(IntegrityError):
        Ticket.objects.filter(pk=ticket.pk).update(status=Status.RESOLVED)
