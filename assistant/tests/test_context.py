import pytest
from django.contrib import admin
from django.test import RequestFactory

from accounts.roles import AGENT, VIEWER
from assistant.context import build_form_reference
from tickets.models import Customer, Ticket
from tickets.rules import Status

pytestmark = pytest.mark.django_db


@pytest.fixture
def request_as(make_user, roles):
    from django.contrib.auth.models import Group

    def build(role):
        user = make_user()
        user.groups.add(Group.objects.get(name=role))
        request = RequestFactory().get("/")
        request.user = user
        return request

    return build


def reference_for(request, model, obj=None):
    return build_form_reference(admin.site.get_model_admin(model), request, obj)


def test_ticket_reference_is_built_from_the_real_form(request_as, make_ticket, make_agent):
    request = request_as(AGENT)
    ticket = make_ticket(status=Status.OPEN, assignee=make_agent(user=request.user))

    text, labels = reference_for(request, Ticket, ticket)

    assert "Form: Ticket (editing an existing record)" in text
    assert Ticket._meta.get_field("priority").help_text in text
    # Only the statuses this ticket can move to, with its current one.
    assert "currently Open, options: Open, Waiting on customer, Resolved." in text
    # Rules come from tickets.rules, so they can't drift from what the model enforces.
    assert "Closed: nothing (final)" in text
    assert "urgent 4h, high 8h, normal 24h, low 72h" in text
    # The add-reply inline is described too.
    assert 'Section "Add a reply"' in text
    assert labels["is_internal"] == "Internal note"


def test_reference_never_contains_record_content(request_as, make_ticket):
    ticket = make_ticket(subject="Refund for ACME Corp", description="Card ending 4242")

    text, _ = reference_for(request_as(AGENT), Ticket, ticket)

    assert "ACME" not in text
    assert "4242" not in text
    assert ticket.customer.email not in text


def test_new_ticket_form_offers_only_starting_statuses(request_as):
    text, _ = reference_for(request_as(AGENT), Ticket)

    assert "creating a new record" in text
    assert "options: New, Open." in text


def test_view_only_users_get_field_meanings_without_editable_fields(request_as, make_ticket):
    text, labels = reference_for(request_as(VIEWER), Ticket, make_ticket())

    assert "every field is read-only" in text
    assert "Fields:" not in text
    assert "- Priority [priority]: options: Low, Normal, High, Urgent." in text
    assert 'Section "Add a reply"' not in text
    assert labels == {}


def test_customer_form_reference(request_as):
    text, _ = reference_for(request_as(AGENT), Customer)

    assert "- Email [email]: email address, required" in text
    assert "unique email" in text
    assert "Rules:" not in text  # customers have no extra rules
