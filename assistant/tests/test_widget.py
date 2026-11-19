import pytest
from django.urls import reverse

from accounts.roles import AGENT

pytestmark = pytest.mark.django_db


def test_widget_appears_on_change_forms_only(login_as, make_ticket):
    client = login_as(AGENT)
    ticket = make_ticket()

    change_page = client.get(reverse("admin:tickets_ticket_change", args=[ticket.pk]))
    list_page = client.get(reverse("admin:tickets_ticket_changelist"))

    assert (
        f'data-model="tickets.ticket" data-object-id="{ticket.pk}"' in change_page.content.decode()
    )
    assert "rh-assistant" not in list_page.content.decode()
