from io import StringIO

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.management import CommandError, call_command
from django.db.models import F
from django.utils import timezone

from accounts.roles import AGENT, SUPPORT_ADMIN, VIEWER
from tickets import rules
from tickets.models import Agent, Comment, Customer, Ticket
from tickets.rules import Status

pytestmark = pytest.mark.django_db

SMALL = {"customers": 30, "tickets": 120, "attachments": 3, "password": "seed-test-pass-1"}


def seed(**options):
    call_command("seed", **{**SMALL, **options}, stdout=StringIO())


def test_creates_the_requested_volume():
    seed()

    assert Customer.objects.count() == 30
    assert Ticket.objects.count() == 120
    assert Comment.objects.count() > 120
    assert Comment.objects.exclude(attachment="").count() == 3


def test_demo_accounts_can_log_in_with_their_roles():
    seed()

    for username, role in [
        ("admin", SUPPORT_ADMIN),
        ("agent", AGENT),
        ("viewer", VIEWER),
    ]:
        user = authenticate(username=username, password=SMALL["password"])
        assert user is not None and user.is_staff
        assert list(user.groups.values_list("name", flat=True)) == [role]


def test_seeded_colleagues_cannot_log_in():
    seed()

    colleague = Agent.objects.exclude(user__username__in=["admin", "agent"]).first().user

    assert not colleague.has_usable_password()


def test_data_respects_the_business_rules():
    seed()
    now = timezone.now()

    for ticket in Ticket.objects.all():
        assert ticket.due_at == rules.due_at_for(ticket.created_at, ticket.priority)
        if ticket.status in rules.REQUIRES_ASSIGNEE:
            assert ticket.assignee_id is not None
    assert not Ticket.objects.filter(resolved_at__gt=now).exists()
    assert not Ticket.objects.filter(closed_at__gt=now).exists()
    assert not Comment.objects.filter(created_at__gt=now).exists()
    assert not Comment.objects.filter(created_at__lt=F("ticket__created_at")).exists()
    assert Ticket.objects.filter(status=Status.CLOSED).exists()
    assert Ticket.objects.active().exists()


def test_refuses_to_seed_over_existing_data_without_reset():
    seed()

    with pytest.raises(CommandError, match="--reset"):
        seed()


def test_reset_replaces_demo_data_but_keeps_real_accounts(django_user_model):
    real = django_user_model.objects.create_user("real.person", "real@company.example")
    seed()

    seed(reset=True, tickets=50)

    assert Ticket.objects.count() == 50
    assert get_user_model().objects.filter(pk=real.pk).exists()
    assert get_user_model().objects.filter(username="admin").count() == 1


def test_same_seed_gives_the_same_data():
    seed()
    first = list(Ticket.objects.order_by("pk").values_list("subject", "status", "priority"))

    seed(reset=True)
    second = list(Ticket.objects.order_by("pk").values_list("subject", "status", "priority"))

    assert first == second


def test_reset_keeps_real_staff_agent_profiles(make_agent):
    real = make_agent()
    seed()

    seed(reset=True, tickets=50)

    assert Agent.objects.filter(pk=real.pk).exists()


def test_refuses_before_touching_data_if_a_real_account_uses_a_demo_name(django_user_model):
    seed()
    django_user_model.objects.filter(username="viewer").update(email="viewer@company.example")

    with pytest.raises(CommandError, match="viewer"):
        seed(reset=True)

    assert Ticket.objects.count() == SMALL["tickets"]
