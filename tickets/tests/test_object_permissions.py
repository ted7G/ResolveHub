"""
Per-ticket rules in the places they're easiest to get around: inlines on
other pages, forms that fail validation, search, and counts.
"""

import pytest
from django.urls import reverse

from accounts.roles import AGENT, SUPPORT_ADMIN, VIEWER
from tests.admin_forms import admin_form_data
from tickets.models import Comment, Tag
from tickets.rules import Priority, Status

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:tickets_ticket_changelist")


def change_url(ticket):
    return reverse("admin:tickets_ticket_change", args=[ticket.pk])


def test_closed_ticket_stays_locked_on_the_customer_page(login_as, customer, make_ticket):
    client = login_as(SUPPORT_ADMIN)
    closed = make_ticket(status=Status.CLOSED, assignee=client.user.agent_profile)
    open_ = make_ticket(status=Status.OPEN, assignee=client.user.agent_profile)
    url = reverse("admin:tickets_customer_change", args=[customer.pk])
    response = client.get(url)
    data = admin_form_data(response)
    rows = response.context["inline_admin_formsets"][0].formset.forms
    for index, form in enumerate(rows):
        data[f"tickets-{index}-subject"] = f"Edited {form.instance.pk}"
        data[f"tickets-{index}-priority"] = Priority.URGENT

    response = client.post(url, data)

    assert response.status_code == 302
    closed.refresh_from_db()
    open_.refresh_from_db()
    assert (closed.subject, closed.priority) == ("Cannot log in", Priority.NORMAL)
    assert (open_.subject, open_.priority) == (f"Edited {open_.pk}", Priority.URGENT)


def test_messages_cannot_be_deleted_from_the_conversation(login_as, make_ticket):
    client = login_as(SUPPORT_ADMIN)
    ticket = make_ticket(status=Status.OPEN, assignee=client.user.agent_profile)
    reply = Comment.objects.create(ticket=ticket, author=client.user, body="Looking into it.")
    data = admin_form_data(client.get(change_url(ticket)))
    data["comments-0-DELETE"] = "on"

    client.post(change_url(ticket), data)

    assert Comment.objects.filter(pk=reply.pk).exists()


def test_failed_submit_is_judged_on_the_saved_ticket(login_as, make_ticket):
    # Closing the ticket and replying in the same submit fails (closed
    # tickets take no new messages). The page must come back editable so
    # the agent can fix it, not locked as if the close had been saved.
    client = login_as(AGENT)
    ticket = make_ticket(status=Status.RESOLVED, assignee=client.user.agent_profile)
    data = admin_form_data(client.get(change_url(ticket)))
    data["status"] = Status.CLOSED
    data["comments-2-0-body"] = "Closing this now."

    response = client.post(change_url(ticket), data)

    assert response.status_code == 200
    assert response.context["has_change_permission"]
    assert not response.context.get("readonly_reason")
    ticket.refresh_from_db()
    assert ticket.status == Status.RESOLVED


def test_agent_can_take_a_ticket_but_not_hand_it_to_a_colleague(login_as, make_ticket, make_agent):
    client = login_as(AGENT)
    me, colleague = client.user.agent_profile, make_agent()
    ticket = make_ticket()
    response = client.get(change_url(ticket))
    offered = [v for v, _ in response.context["adminform"].form.fields["assignee"].choices if v]
    assert offered == [me.pk]

    data = admin_form_data(response)
    data["status"] = Status.OPEN
    data["assignee"] = colleague.pk
    assert client.post(change_url(ticket), data).status_code == 200
    ticket.refresh_from_db()
    assert ticket.assignee_id is None

    data["assignee"] = me.pk
    assert client.post(change_url(ticket), data).status_code == 302
    ticket.refresh_from_db()
    assert ticket.assignee_id == me.pk


def test_comment_count_does_not_reveal_internal_notes_to_viewers(
    login_as, client, make_ticket, make_user
):
    ticket = make_ticket()
    Comment.objects.create(ticket=ticket, author=make_user(), body="VIP", is_internal=True)

    viewer = login_as(VIEWER)
    assert viewer.get(CHANGELIST).context["cl"].result_list[0].comment_count == 0

    admin_client = login_as(SUPPORT_ADMIN)
    assert admin_client.get(CHANGELIST).context["cl"].result_list[0].comment_count == 1


def test_searching_a_ticket_number_keeps_the_sidebar_filters(superuser_client, make_ticket):
    new = make_ticket()

    response = superuser_client.get(CHANGELIST, {"status__exact": Status.CLOSED, "q": new.pk})

    assert list(response.context["cl"].result_list) == []


def test_searching_a_ticket_number_does_not_inflate_comment_counts(superuser_client, make_ticket):
    ticket = make_ticket()
    billing, urgent = Tag.objects.create(name="billing"), Tag.objects.create(name="vip")
    ticket.tags.add(billing, urgent)
    for body in ("one", "two", "three"):
        Comment.objects.create(ticket=ticket, body=body)

    response = superuser_client.get(CHANGELIST, {"tags__id__exact": billing.pk, "q": ticket.pk})

    [row] = response.context["cl"].result_list
    assert row.comment_count == 3
