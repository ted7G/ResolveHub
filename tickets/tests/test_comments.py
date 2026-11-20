import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from tickets.models import Comment
from tickets.rules import Status
from tickets.validators import MAX_ATTACHMENT_BYTES, validate_attachment

PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# --- Attachment validation ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("screenshot.png", PNG_HEADER),
        ("Invoice.PDF", b"%PDF-1.7\n..."),
        ("photo.jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 16),
        ("server.log", b"2026-03-02 09:00:01 ERROR timeout\n"),
        ("export.csv", "name,city\nZoë,Kraków\n".encode()),
    ],
)
def test_accepts_allowed_files(name, content):
    validate_attachment(SimpleUploadedFile(name, content))


@pytest.mark.parametrize("name", ["payload.exe", "page.html", "image.svg", "script.js", "README"])
def test_rejects_disallowed_types(name):
    with pytest.raises(ValidationError) as exc:
        validate_attachment(SimpleUploadedFile(name, b"anything"))

    assert exc.value.code == "attachment_type"


def test_rejects_file_whose_content_does_not_match_extension():
    renamed_executable = SimpleUploadedFile("cat.png", b"MZ\x90\x00" + b"\x00" * 64)

    with pytest.raises(ValidationError) as exc:
        validate_attachment(renamed_executable)

    assert exc.value.code == "attachment_content"


def test_rejects_binary_disguised_as_text():
    with pytest.raises(ValidationError) as exc:
        validate_attachment(SimpleUploadedFile("notes.txt", b"\x00\x01\x02binary"))

    assert exc.value.code == "attachment_content"


def test_rejects_oversized_files():
    big = SimpleUploadedFile("big.png", PNG_HEADER + b"\x00" * MAX_ATTACHMENT_BYTES)

    with pytest.raises(ValidationError) as exc:
        validate_attachment(big)

    assert exc.value.code == "attachment_size"


def test_text_check_tolerates_a_multibyte_character_cut_at_the_sample_edge():
    content = b"a" * 4095 + "é".encode()  # é is two bytes; the sample ends between them

    validate_attachment(SimpleUploadedFile("long.txt", content))


# --- Comment rules -----------------------------------------------------------


@pytest.mark.django_db
def test_upload_gets_random_key_and_keeps_original_name(make_ticket, make_user):
    comment = Comment.objects.create(
        ticket=make_ticket(),
        author=make_user(),
        body="Screenshot attached.",
        attachment=SimpleUploadedFile("My Screenshot.png", PNG_HEADER),
    )

    assert comment.attachment_name == "My Screenshot.png"
    assert comment.attachment.name.startswith("attachments/")
    assert "Screenshot" not in comment.attachment.name
    assert comment.attachment.name.endswith(".png")


@pytest.mark.django_db
def test_closed_ticket_does_not_accept_new_comments(make_ticket, make_user):
    ticket = make_ticket()
    ticket.transition_to(Status.CLOSED)
    comment = Comment(ticket=ticket, author=make_user(), body="One more thing...")

    with pytest.raises(ValidationError, match="closed"):
        comment.full_clean()


@pytest.mark.django_db
def test_customer_messages_cannot_be_internal(make_ticket):
    comment = Comment(ticket=make_ticket(), author=None, is_internal=True, body="Hi")

    with pytest.raises(ValidationError) as exc:
        comment.full_clean()
    assert "is_internal" in exc.value.message_dict

    with pytest.raises(IntegrityError):
        comment.save()


@pytest.mark.django_db
def test_deleting_a_ticket_removes_its_stored_attachments(
    make_ticket, django_capture_on_commit_callbacks
):
    comment = Comment(ticket=make_ticket(), body="Log attached")
    comment.attachment.save("app.log", ContentFile(b"started\n"))
    stored = comment.attachment.name
    assert default_storage.exists(stored)

    with django_capture_on_commit_callbacks(execute=True):
        comment.ticket.delete()

    assert not default_storage.exists(stored)


@pytest.mark.django_db
def test_storage_outage_while_deleting_files_does_not_fail_the_delete(
    superuser_client, make_ticket, monkeypatch, django_capture_on_commit_callbacks
):
    from django.urls import reverse

    ticket = make_ticket()
    for name in ("one.log", "two.log"):
        comment = Comment(ticket=ticket, body=name)
        comment.attachment.save(name, ContentFile(b"started\n"))
    attempted = []

    def unavailable(name):
        attempted.append(name)
        raise ConnectionError("storage is down")

    monkeypatch.setattr(default_storage, "delete", unavailable)
    url = reverse("admin:tickets_ticket_delete", args=[ticket.pk])

    with django_capture_on_commit_callbacks(execute=True):
        response = superuser_client.post(url, {"post": "yes"})

    assert response.status_code == 302
    assert len(attempted) == 2
