"""Smoke tests: every customised admin page renders, with filters and search applied."""

import pytest
from django.urls import reverse

from tickets.models import Comment, Tag
from tickets.rules import Status

pytestmark = pytest.mark.django_db


@pytest.fixture
def ticket(make_ticket, make_agent, make_user):
    ticket = make_ticket(assignee=make_agent(), status=Status.OPEN)
    ticket.tags.add(Tag.objects.create(name="login"))
    Comment.objects.create(ticket=ticket, author=make_user(), body="Looking into it.")
    return ticket


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?deadline=overdue",
        "?deadline=due_soon",
        "?deadline=on_track",
        "?assigned=unassigned",
        "?assigned=me",
        "?status__exact=open&priority__exact=normal",
        "?q=log",
        "?q=RH-00001",
        "?o=-7",
    ],
)
def test_ticket_changelist(superuser_client, ticket, query):
    response = superuser_client.get(reverse("admin:tickets_ticket_changelist") + query)

    assert response.status_code == 200


def test_search_by_ticket_reference_finds_the_ticket(superuser_client, ticket, make_ticket):
    other = make_ticket(subject="Unrelated")
    url = reverse("admin:tickets_ticket_changelist")

    response = superuser_client.get(url, {"q": ticket.reference})

    assert ticket in response.context["cl"].result_list
    assert other not in response.context["cl"].result_list


@pytest.mark.parametrize(
    ("url_name", "query"),
    [
        ("tickets_customer", {}),
        ("tickets_customer", {"q": "dana"}),
        ("tickets_customer", {"active": "yes"}),
        ("tickets_customer", {"active": "no"}),
        ("tickets_agent", {"q": "user"}),
        ("tickets_agent", {"team__exact": "billing"}),
        ("tickets_tag", {"q": "log"}),
    ],
)
def test_other_changelists(superuser_client, ticket, url_name, query):
    response = superuser_client.get(reverse(f"admin:{url_name}_changelist"), query)

    assert response.status_code == 200


def test_ticket_change_page(superuser_client, ticket):
    response = superuser_client.get(reverse("admin:tickets_ticket_change", args=[ticket.pk]))

    assert response.status_code == 200
    status_choices = [
        value for value, _ in response.context["adminform"].form.fields["status"].choices
    ]
    assert status_choices == [Status.OPEN, Status.PENDING, Status.RESOLVED]


def test_customer_change_page(superuser_client, ticket):
    url = reverse("admin:tickets_customer_change", args=[ticket.customer.pk])

    assert superuser_client.get(url).status_code == 200


def test_ticket_add_page_only_offers_starting_statuses(superuser_client):
    response = superuser_client.get(reverse("admin:tickets_ticket_add"))

    status_choices = [
        value for value, _ in response.context["adminform"].form.fields["status"].choices
    ]
    assert status_choices == [Status.NEW, Status.OPEN]
