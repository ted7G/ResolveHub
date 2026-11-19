"""Round trips through the real admin forms, including the inline formsets."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from tickets.models import Comment
from tickets.rules import Status

from .conftest import admin_form_data

pytestmark = pytest.mark.django_db


def change_url(ticket):
    return reverse("admin:tickets_ticket_change", args=[ticket.pk])


@pytest.fixture
def open_ticket(make_ticket, make_agent):
    return make_ticket(status=Status.OPEN, assignee=make_agent())


def test_reply_added_from_ticket_page_is_authored_by_the_current_user(
    superuser_client, open_ticket
):
    data = admin_form_data(superuser_client.get(change_url(open_ticket)))
    data["comments-2-0-body"] = "Could you send a screenshot of the error?"

    response = superuser_client.post(change_url(open_ticket), data)

    assert response.status_code == 302, response.context["errors"]
    comment = open_ticket.comments.get()
    assert comment.author == superuser_client.user
    assert not comment.is_internal


def test_internal_note_with_attachment(superuser_client, open_ticket):
    data = admin_form_data(superuser_client.get(change_url(open_ticket)))
    data["comments-2-0-body"] = "Log from the customer's device."
    data["comments-2-0-is_internal"] = "on"
    data["comments-2-0-attachment"] = SimpleUploadedFile("device.log", b"E/Auth: token expired\n")

    response = superuser_client.post(change_url(open_ticket), data)

    assert response.status_code == 302
    comment = open_ticket.comments.get()
    assert comment.is_internal
    assert comment.attachment_name == "device.log"


def test_rejected_attachment_shows_an_error_and_saves_nothing(superuser_client, open_ticket):
    data = admin_form_data(superuser_client.get(change_url(open_ticket)))
    data["comments-2-0-body"] = "See attached"
    data["comments-2-0-attachment"] = SimpleUploadedFile("invoice.pdf", b"<html>not a pdf</html>")

    response = superuser_client.post(change_url(open_ticket), data)

    assert response.status_code == 200
    assert "don&#x27;t match its .pdf extension" in response.content.decode()
    assert not Comment.objects.exists()


def test_invalid_status_change_is_reported_on_the_form(superuser_client, open_ticket):
    data = admin_form_data(superuser_client.get(change_url(open_ticket)))
    data["status"] = Status.CLOSED  # not offered in the dropdown, but posted anyway

    response = superuser_client.post(change_url(open_ticket), data)

    assert response.status_code == 200
    assert "status" in response.context["adminform"].form.errors
    open_ticket.refresh_from_db()
    assert open_ticket.status == Status.OPEN


def test_existing_conversation_is_read_only(superuser_client, open_ticket, make_user):
    Comment.objects.create(ticket=open_ticket, author=make_user(), body="Original wording")
    data = admin_form_data(superuser_client.get(change_url(open_ticket)))
    data["comments-0-body"] = "Rewritten history"

    superuser_client.post(change_url(open_ticket), data)

    assert open_ticket.comments.get().body == "Original wording"


def test_closed_ticket_is_read_only_and_takes_no_replies(superuser_client, make_ticket):
    ticket = make_ticket()
    ticket.transition_to(Status.CLOSED)

    response = superuser_client.get(change_url(ticket))

    assert response.status_code == 200
    assert response.context["has_change_permission"] is False
    prefixes = [inline.formset.prefix for inline in response.context["inline_admin_formsets"]]
    assert "comments-2" not in prefixes


def test_ticket_status_can_be_changed_from_the_customer_page(superuser_client, open_ticket):
    url = reverse("admin:tickets_customer_change", args=[open_ticket.customer.pk])
    data = admin_form_data(superuser_client.get(url))
    data["tickets-0-status"] = Status.PENDING

    response = superuser_client.post(url, data)

    assert response.status_code == 302
    open_ticket.refresh_from_db()
    assert open_ticket.status == Status.PENDING


def test_customer_page_inline_still_enforces_the_workflow(superuser_client, open_ticket):
    url = reverse("admin:tickets_customer_change", args=[open_ticket.customer.pk])
    data = admin_form_data(superuser_client.get(url))
    data["tickets-0-status"] = Status.NEW

    response = superuser_client.post(url, data)

    assert response.status_code == 200
    open_ticket.refresh_from_db()
    assert open_ticket.status == Status.OPEN
