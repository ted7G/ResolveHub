import pytest
from django.urls import reverse

from accounts.roles import AGENT

pytestmark = pytest.mark.django_db


def test_widget_knows_which_page_it_is_on(login_as, make_ticket):
    client = login_as(AGENT)
    ticket = make_ticket()

    change_page = client.get(reverse("admin:tickets_ticket_change", args=[ticket.pk]))
    list_page = client.get(reverse("admin:tickets_ticket_changelist"))
    dashboard = client.get(reverse("admin:index"))

    assert (
        f'data-page="form" data-model="tickets.ticket" data-object-id="{ticket.pk}"'
        in change_page.content.decode()
    )
    assert 'data-page="list" data-model="tickets.ticket" data-object-id=""' in (
        list_page.content.decode()
    )
    assert 'data-page="general" data-model=""' in dashboard.content.decode()
    assert "data-rh-open-assistant" in dashboard.content.decode()


def test_widget_is_not_on_the_login_page(client):
    page = client.get(reverse("admin:login")).content.decode()

    assert "rh-assistant" not in page
