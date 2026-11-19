"""
What each role can see and do in the admin, checked through real requests
rather than by inspecting group permissions.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.roles import AGENT, ROLE_PERMISSIONS, SUPPORT_ADMIN, VIEWER, sync_roles
from tests.admin_forms import admin_form_data
from tickets.models import Comment, Ticket
from tickets.rules import Status

pytestmark = pytest.mark.django_db

TICKETS = reverse("admin:tickets_ticket_changelist")
USERS = reverse("admin:auth_user_changelist")


def ticket_url(ticket):
    return reverse("admin:tickets_ticket_change", args=[ticket.pk])


def visible_models(response):
    return {m["object_name"] for app in response.context["app_list"] for m in app["models"]}


# --- Role definitions ----------------------------------------------------------


def test_sync_is_idempotent_and_exact(roles):
    viewer = Group.objects.get(name=VIEWER)
    viewer.permissions.add(Group.objects.get(name=SUPPORT_ADMIN).permissions.first())

    sync_roles()
    sync_roles()

    assert Group.objects.filter(name__in=ROLE_PERMISSIONS).count() == 3
    assert viewer.permissions.count() == len(ROLE_PERMISSIONS[VIEWER])


# --- What each role sees -------------------------------------------------------


def test_admin_requires_login(client):
    response = client.get(TICKETS)

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("admin:login"))


def test_support_admin_sees_user_management(login_as):
    client = login_as(SUPPORT_ADMIN)

    models = visible_models(client.get(reverse("admin:index")))

    assert {"Ticket", "Customer", "Agent", "Tag", "User"} <= models


@pytest.mark.parametrize("role", [AGENT, VIEWER])
def test_other_roles_do_not_see_user_management(login_as, role):
    client = login_as(role)

    models = visible_models(client.get(reverse("admin:index")))

    assert "User" not in models
    assert "Group" not in models
    assert client.get(USERS).status_code == 403


def test_viewer_gets_a_read_only_desk(login_as, make_ticket):
    client = login_as(VIEWER)
    ticket = make_ticket()

    changelist = client.get(TICKETS)
    detail = client.get(ticket_url(ticket))

    assert changelist.context["has_add_permission"] is False
    assert changelist.context["action_form"] is None  # no bulk actions at all
    assert detail.context["has_change_permission"] is False
    assert "read-only access" in detail.context["readonly_reason"]
    assert client.get(reverse("admin:tickets_ticket_add")).status_code == 403


def test_agent_actions_exclude_reassigning_and_deleting(login_as):
    client = login_as(AGENT)

    choices = dict(client.get(TICKETS).context["action_form"].fields["action"].choices)

    assert "assign_to_me" in choices
    assert "mark_resolved" in choices
    assert "assign_to_agent" not in choices
    assert "delete_selected" not in choices


def test_internal_notes_are_hidden_from_viewers(login_as, make_ticket, make_user):
    ticket = make_ticket()
    author = make_user()
    Comment.objects.create(
        ticket=ticket, author=author, body="Customer is on the free plan.", is_internal=True
    )
    Comment.objects.create(ticket=ticket, author=author, body="We're looking into it.")

    agent_page = login_as(AGENT).get(ticket_url(ticket)).content.decode()
    viewer_page = login_as(VIEWER).get(ticket_url(ticket)).content.decode()

    assert "free plan" in agent_page
    assert "free plan" not in viewer_page
    assert "looking into it" in viewer_page


# --- Ticket ownership ----------------------------------------------------------


def test_agent_can_edit_own_and_unassigned_tickets(login_as, make_ticket):
    client = login_as(AGENT)
    mine = make_ticket(assignee=client.user.agent_profile)
    unassigned = make_ticket()

    for ticket in (mine, unassigned):
        assert client.get(ticket_url(ticket)).context["has_change_permission"] is True


def test_agent_cannot_edit_a_colleagues_ticket(login_as, make_ticket, make_agent):
    client = login_as(AGENT)
    colleague = make_agent()
    ticket = make_ticket(status=Status.OPEN, assignee=colleague)

    page = client.get(ticket_url(ticket))
    assert page.context["has_change_permission"] is False
    assert str(colleague) in page.context["readonly_reason"]

    # Posting directly is refused too, not just hidden in the UI.
    data = admin_form_data(page)
    data.update(subject="Hijacked", description="x", status=Status.OPEN, priority="normal")
    data.update(customer=ticket.customer_id, assignee=colleague.pk)
    response = client.post(ticket_url(ticket), data)

    assert response.status_code == 403
    ticket.refresh_from_db()
    assert ticket.subject != "Hijacked"


def test_bulk_actions_skip_tickets_the_agent_does_not_own(login_as, make_ticket, make_agent):
    client = login_as(AGENT)
    mine = make_ticket(status=Status.OPEN, assignee=client.user.agent_profile)
    theirs = make_ticket(status=Status.OPEN, assignee=make_agent())

    client.post(TICKETS, {"action": "mark_resolved", "_selected_action": [mine.pk, theirs.pk]})

    assert Ticket.objects.get(pk=mine.pk).status == Status.RESOLVED
    assert Ticket.objects.get(pk=theirs.pk).status == Status.OPEN


def test_support_admin_can_edit_any_ticket(login_as, make_ticket, make_agent):
    client = login_as(SUPPORT_ADMIN)
    ticket = make_ticket(status=Status.OPEN, assignee=make_agent())

    assert client.get(ticket_url(ticket)).context["has_change_permission"] is True


# --- Privilege escalation ------------------------------------------------------


def test_support_admin_cannot_grant_superuser_or_raw_permissions(login_as, make_user):
    client = login_as(SUPPORT_ADMIN)
    staff = make_user()

    form = client.get(reverse("admin:auth_user_change", args=[staff.pk])).context["adminform"].form

    assert "is_superuser" not in form.fields
    assert "user_permissions" not in form.fields
    assert "groups" in form.fields


def test_support_admin_cannot_edit_a_superuser(login_as, django_user_model):
    client = login_as(SUPPORT_ADMIN)
    root = django_user_model.objects.create_superuser("root", "root@example.com", "pw-not-used-1")

    page = client.get(reverse("admin:auth_user_change", args=[root.pk]))
    password_page = client.get(reverse("admin:auth_user_password_change", args=[root.pk]))

    assert page.context["has_change_permission"] is False
    assert password_page.status_code == 403
