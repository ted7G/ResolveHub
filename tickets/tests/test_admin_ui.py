"""The admin's own pages: dashboard numbers, header navigation, the ticket page."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.roles import AGENT, SUPPORT_ADMIN, VIEWER
from tests.admin_forms import admin_form_data
from tickets.admin import display
from tickets.models import Comment, Customer
from tickets.rules import Status
from tickets.templatetags.desk_tags import desk_summary

pytestmark = pytest.mark.django_db

INDEX = reverse("admin:index")


# --- Dashboard -----------------------------------------------------------------


@pytest.fixture
def desk(make_ticket, make_agent):
    """A small desk: two new tickets (one overdue), one open, one closed."""

    def build(me):
        make_ticket()
        make_ticket(created_at=timezone.now() - timedelta(days=5))
        make_ticket(status=Status.OPEN, assignee=me)
        make_ticket(status=Status.CLOSED, assignee=make_agent())

    return build


def test_dashboard_numbers_match_the_lists_they_link_to(login_as, desk):
    client = login_as(AGENT)
    desk(client.user.agent_profile)

    page = client.get(INDEX)
    counts, links = page.context["counts"], page.context["links"]

    assert counts["active"] == 3
    assert (counts["new"], counts["open"], counts["pending"]) == (2, 1, 0)
    assert counts["overdue"] == 1
    assert counts["unassigned"] == 2
    assert counts["mine"] == 1
    for key in ("active", "overdue", "due_soon", "unassigned", "mine"):
        listed = client.get(links[key]).context["cl"].result_count
        assert listed == counts[key], key


def test_dashboard_numbers_cost_one_query(make_user, roles, desk, make_agent):
    user = make_user(is_superuser=True)
    desk(make_agent(user=user))
    request = RequestFactory().get(INDEX)
    request.user = user

    with CaptureQueriesContext(connection) as queries:
        desk_summary({"request": request})

    assert len(queries) == 1


def test_viewers_see_the_numbers_but_no_personal_queue(login_as, make_ticket):
    client = login_as(VIEWER)
    make_ticket()

    page = client.get(INDEX)

    assert page.context["counts"]["active"] == 1
    assert "Assigned to you" not in page.content.decode()


def test_dashboard_without_ticket_access_shows_no_numbers(make_user):
    request = RequestFactory().get(INDEX)
    request.user = AnonymousUser()

    assert "counts" not in desk_summary({"request": request})


# --- Header navigation -----------------------------------------------------------


def test_navigation_follows_permissions(login_as, client):
    users = reverse("admin:auth_user_changelist")

    viewer_page = login_as(VIEWER).get(INDEX)
    assert len(viewer_page.context["entries"]) == 4
    entries = [entry["name"] for entry in viewer_page.context["entries"]]
    assert entries[0] == "Tickets"
    assert users not in viewer_page.content.decode()

    client.logout()
    admin_page = login_as(SUPPORT_ADMIN).get(users)
    current = [e["name"] for e in admin_page.context["entries"] if e["current"]]
    assert current == ["Users"]


# --- Ticket page -----------------------------------------------------------------


def test_conversation_marks_who_wrote_what(login_as, make_ticket, make_user):
    client = login_as(AGENT)
    ticket = make_ticket()
    Comment.objects.create(ticket=ticket, body="It still fails.")
    Comment.objects.create(ticket=ticket, author=make_user(), body="On it.")
    Comment.objects.create(ticket=ticket, author=make_user(), body="Billing bug.", is_internal=True)

    page = client.get(reverse("admin:tickets_ticket_change", args=[ticket.pk])).content.decode()

    assert page.count('class="rh-msg is-customer"') == 1
    assert page.count('class="rh-msg is-staff"') == 1
    assert page.count('class="rh-msg is-staff is-internal"') == 1
    assert "3 messages" in page
    # Read-only rows still submit their ids, or every save of this ticket fails.
    assert 'name="comments-TOTAL_FORMS"' in page
    assert 'name="comments-0-id"' in page


def test_admin_enhancement_assets_load_once(superuser_client, make_ticket):
    ticket = make_ticket()

    for url in (
        reverse("admin:tickets_ticket_changelist"),
        reverse("admin:tickets_ticket_change", args=[ticket.pk]),
    ):
        page = superuser_client.get(url).content.decode()
        assert page.count("vendor/jquery/jquery") == 1, url
        assert page.count("select2/select2.full") == 1, url
        assert page.count("resolvehub/searchable") == 1, url
        assert page.count("resolvehub/filterbar") == 1, url


def test_heading_and_strip_show_the_saved_ticket_after_a_failed_save(login_as, make_ticket):
    client = login_as(SUPPORT_ADMIN)
    ticket = make_ticket(status=Status.NEW)
    other = Customer.objects.create(name="Lee Park", email="lee@example.com")
    url = reverse("admin:tickets_ticket_change", args=[ticket.pk])
    data = admin_form_data(client.get(url))
    # Every field is valid on its own; the model rejects Open without an
    # assignee, after the edits have been copied onto the instance.
    data.update(subject="Refund request", status=Status.OPEN, customer=other.pk)

    response = client.post(url, data)

    assert response.status_code == 200
    assert "assignee" in response.context["adminform"].form.errors
    summary = response.context["ticket_summary"]
    assert response.context["title"] == "Cannot log in"
    assert summary["status"] == Status.NEW
    assert "Dana Reyes" in summary["customer"]


def test_customer_page_rows_have_no_related_object_icons(superuser_client, customer, make_ticket):
    make_ticket()

    page = superuser_client.get(reverse("admin:tickets_customer_change", args=[customer.pk]))
    widget = page.context["inline_admin_formsets"][0].formset.forms[0].fields["assignee"].widget

    assert not (widget.can_add_related or widget.can_change_related)
    assert not (widget.can_delete_related or widget.can_view_related)


def test_long_status_is_shortened_in_list_badges(make_ticket, make_agent):
    ticket = make_ticket(status=Status.PENDING, assignee=make_agent())

    badge = display.status_badge(ticket)

    assert ">Waiting<" in badge
    assert 'title="Waiting on customer"' in badge


# --- Error pages -----------------------------------------------------------------


def test_missing_pages_use_the_branded_404(client):
    response = client.get("/no-such-page/")

    assert response.status_code == 404
    assert b"Page not found" in response.content
    assert b"Back to the desk" in response.content
