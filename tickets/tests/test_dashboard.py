"""The numbers behind the dashboard charts."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.roles import SUPPORT_ADMIN
from tickets import dashboard
from tickets.rules import Priority, Status

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 4), (3, 4), (5, 8), (23, 24), (37, 40), (120, 120), (350, 400)],
)
def test_axis_maximum_is_round_and_covers_the_data(value, expected):
    assert dashboard.nice_ceiling(value) == expected


def test_flow_counts_created_and_resolved_per_day(make_ticket, make_agent):
    today = timezone.now()
    make_ticket(created_at=today)
    make_ticket(created_at=today - timedelta(days=2))
    resolved = make_ticket(status=Status.OPEN, assignee=make_agent())
    resolved.transition_to(Status.RESOLVED)
    make_ticket(created_at=today - timedelta(days=30))  # outside the window

    flow = dashboard.ticket_flow(days=14)

    assert len(flow["points"]) == 14
    assert flow["created_total"] == 3
    assert flow["resolved_total"] == 1
    last = flow["points"][-1]
    assert last["is_today"] and (last["created"], last["resolved"]) == (2, 1)
    assert flow["points"][-3]["created"] == 1
    assert min(p["created_y"] for p in flow["points"]) >= 0


def test_priority_load_splits_on_track_and_overdue(make_ticket):
    now = timezone.now()
    make_ticket(priority=Priority.URGENT)
    make_ticket(priority=Priority.URGENT, created_at=now - timedelta(days=1))
    make_ticket(priority=Priority.LOW, status=Status.CLOSED)

    rows = {row["label"]: row for row in dashboard.priority_load(now)["rows"]}

    assert (rows["Urgent"]["active"], rows["Urgent"]["overdue"]) == (2, 1)
    assert rows["Urgent"]["on_track"] == 1
    assert rows["Low"]["active"] == 0
    assert "priority__exact=urgent" in rows["Urgent"]["url"]


def test_workload_ranks_agents_and_links_to_their_tickets(make_ticket, make_agent):
    busy, quiet, idle = make_agent(), make_agent(), make_agent()
    for _ in range(3):
        make_ticket(status=Status.OPEN, assignee=busy)
    make_ticket(status=Status.OPEN, assignee=quiet)
    make_ticket(status=Status.CLOSED, assignee=idle)

    rows = dashboard.agent_workload(timezone.now())["rows"]

    assert [row["active"] for row in rows] == [3, 1]
    assert f"assignee__id__exact={busy.pk}" in rows[0]["url"]


def test_dashboard_page_stays_within_a_query_budget(login_as, make_ticket):
    client = login_as(SUPPORT_ADMIN)
    for _ in range(5):
        make_ticket()

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    assert "Ticket flow" in response.content.decode()
    # Session, user, summary, 2 flow, priority, workload, admin log, groups...
    assert len(queries) <= 16
