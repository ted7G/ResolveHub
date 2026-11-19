import itertools

import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.db.models.fields.files import FieldFile

from tickets.models import Agent, Customer, Ticket

_counter = itertools.count(1)


def _post_value(value):
    if isinstance(value, list | tuple):
        return [_post_value(v) for v in value]
    if hasattr(value, "pk"):
        return value.pk
    return value


def admin_form_data(response):
    """
    Build the POST payload an admin change page would submit unchanged,
    including every inline formset, from the page's GET response.
    """
    data = {}

    def add_form(form):
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            value = value() if callable(value) else value
            if value is None or isinstance(value, FieldFile):
                continue
            if isinstance(field, forms.BooleanField):
                if value:
                    data[form.add_prefix(name)] = "on"
                continue
            data[form.add_prefix(name)] = _post_value(value)

    add_form(response.context["adminform"].form)
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        for key, value in formset.management_form.initial.items():
            data[f"{formset.prefix}-{key}"] = value
        for form in formset.forms:
            add_form(form)
    return data


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
