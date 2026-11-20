import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.urls import reverse

from tickets.models import Agent, Ticket
from tickets.rules import Status

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:tickets_ticket_changelist")


def run_action(client, action, tickets, **extra):
    data = {"action": action, "_selected_action": [t.pk for t in tickets], **extra}
    response = client.post(CHANGELIST, data, follow=True)
    assert response.status_code == 200
    return [str(m) for m in get_messages(response.wsgi_request)]


def test_bulk_resolve_moves_valid_tickets_and_reports_the_rest(
    superuser_client, make_ticket, make_agent
):
    agent = make_agent()
    open_tickets = [make_ticket(status=Status.OPEN, assignee=agent) for _ in range(3)]
    unassigned = make_ticket()
    closed = make_ticket()
    closed.transition_to(Status.CLOSED)

    messages = run_action(superuser_client, "mark_resolved", [*open_tickets, unassigned, closed])

    assert Ticket.objects.filter(status=Status.RESOLVED).count() == 3
    assert "3 tickets moved to Resolved." in messages
    assert any("1 ticket skipped: Assign an agent" in m for m in messages)
    assert any("1 ticket skipped: closed tickets can't be changed" in m for m in messages)
    assert LogEntry.objects.filter(change_message__contains="bulk action").count() == 3


def test_assign_to_me_requires_an_agent_profile(superuser_client, make_ticket):
    ticket = make_ticket()

    messages = run_action(superuser_client, "assign_to_me", [ticket])

    assert messages == ["Your login isn't linked to an agent profile."]
    ticket.refresh_from_db()
    assert ticket.assignee is None


def test_assign_to_me(superuser_client, make_ticket):
    agent = Agent.objects.create(user=superuser_client.user)
    tickets = [make_ticket(), make_ticket()]

    messages = run_action(superuser_client, "assign_to_me", tickets)

    assert messages == ["2 tickets assigned to you."]
    assert set(Ticket.objects.values_list("assignee", flat=True)) == {agent.pk}


def test_assign_to_agent_uses_the_agent_picker(superuser_client, make_ticket, make_agent):
    agent = make_agent()
    tickets = [make_ticket(), make_ticket()]

    run_action(superuser_client, "assign_to_agent", tickets, agent=agent.pk)

    assert set(Ticket.objects.values_list("assignee", flat=True)) == {agent.pk}


def test_assign_to_agent_without_picking_one(superuser_client, make_ticket):
    messages = run_action(superuser_client, "assign_to_agent", [make_ticket()])

    assert messages == ["Pick an agent in the box next to the action menu first."]


def test_unavailable_agents_are_not_offered_or_accepted(superuser_client, make_ticket, make_agent):
    away = make_agent(is_available=False)
    present = make_agent()

    page = superuser_client.get(CHANGELIST)
    offered = list(page.context["action_form"].fields["agent"].queryset)
    assert offered == [present]

    # A hand-crafted POST naming the unavailable agent is rejected as well.
    run_action(superuser_client, "assign_to_agent", [make_ticket()], agent=away.pk)
    assert not Ticket.objects.filter(assignee=away).exists()


def test_mark_agents_away(superuser_client, make_agent):
    agents = [make_agent(), make_agent()]
    url = reverse("admin:tickets_agent_changelist")

    superuser_client.post(
        url, {"action": "mark_agents_away", "_selected_action": [a.pk for a in agents]}
    )

    assert not Agent.objects.filter(is_available=True).exists()
