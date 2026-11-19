import itertools

import pytest
from django.contrib.auth import get_user_model

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
