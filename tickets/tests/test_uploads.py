"""Uploads are kept in memory and cut off just past the attachment limit."""

import pytest
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import RequestFactory
from django.urls import reverse

from tests.admin_forms import admin_form_data
from tickets.models import Comment
from tickets.rules import Status
from tickets.uploads import KEEP_BYTES
from tickets.validators import MAX_ATTACHMENT_BYTES

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def parsed_upload(content, name="shot.png"):
    request = RequestFactory().post("/", {"file": SimpleUploadedFile(name, content)})
    return request.FILES["file"]


def test_allowed_size_upload_arrives_intact_in_memory():
    content = PNG_HEADER + b"\x01" * 1000

    upload = parsed_upload(content)

    assert isinstance(upload, InMemoryUploadedFile)
    assert upload.size == len(content)
    assert upload.read() == content


def test_oversized_upload_reports_its_real_size_but_keeps_only_the_limit():
    size = MAX_ATTACHMENT_BYTES + 3 * 1024 * 1024

    upload = parsed_upload(PNG_HEADER + b"\x00" * (size - len(PNG_HEADER)))

    # In memory rather than a temporary file on disk, whatever the size.
    assert isinstance(upload, InMemoryUploadedFile)
    assert upload.size == size
    assert len(upload.read()) == KEEP_BYTES


@pytest.mark.django_db
def test_oversized_attachment_is_rejected_on_the_ticket_page(
    superuser_client, make_ticket, make_agent
):
    ticket = make_ticket(status=Status.OPEN, assignee=make_agent())
    url = reverse("admin:tickets_ticket_change", args=[ticket.pk])
    data = admin_form_data(superuser_client.get(url))
    data["comments-2-0-body"] = "Full-resolution screenshot attached."
    data["comments-2-0-attachment"] = SimpleUploadedFile(
        "screen.png", PNG_HEADER + b"\x00" * (6 * 1024 * 1024 - len(PNG_HEADER))
    )

    response = superuser_client.post(url, data)

    assert response.status_code == 200
    assert "This file is 6.0\xa0MB; the limit is 5.0\xa0MB." in response.content.decode()
    assert not Comment.objects.exists()
