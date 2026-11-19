"""Fixtures shared by every test package."""

import itertools

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.roles import AGENT, SUPPORT_ADMIN, sync_roles
from tickets.models import Agent, Customer, Ticket

_counter = itertools.count(1)


@pytest.fixture
def make_user(db):
    def make(**kwargs):
        n = next(_counter)
        kwargs.setdefault("username", f"user{n}")
        kwargs.setdefault("is_staff", True)
        return get_user_model().objects.create_user(password="pw-not-used-1", **kwargs)

    return make


@pytest.fixture
def make_agent(make_user):
    def make(user=None, **kwargs):
        return Agent.objects.create(user=user or make_user(), **kwargs)

    return make


@pytest.fixture
def superuser_client(client, django_user_model):
    user = django_user_model.objects.create_superuser("root", "root@example.com", "pw-not-used-1")
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def customer(db):
    return Customer.objects.create(name="Dana Reyes", email="dana@example.com")


@pytest.fixture
def make_ticket(customer):
    def make(**kwargs):
        kwargs.setdefault("subject", "Cannot log in")
        kwargs.setdefault("description", "Password reset email never arrives.")
        kwargs.setdefault("customer", customer)
        return Ticket.objects.create(**kwargs)

    return make


@pytest.fixture
def roles(db):
    sync_roles()


@pytest.fixture
def login_as(client, make_user, roles):
    """Log the test client in as a fresh staff user holding `role`."""

    def login(role, *, agent_profile=None):
        user = make_user()
        user.groups.add(Group.objects.get(name=role))
        # Agents and support admins work tickets, so they get an agent profile.
        if agent_profile is None:
            agent_profile = role in (AGENT, SUPPORT_ADMIN)
        if agent_profile:
            Agent.objects.create(user=user)
        client.force_login(user)
        client.user = user
        return client

    return login
