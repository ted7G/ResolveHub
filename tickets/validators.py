"""
Validation for files attached to ticket comments.

The extension alone proves nothing, so the first bytes of each upload are
checked against the signature expected for that type. Anything that could be
rendered as active content in a browser (HTML, SVG, scripts) isn't on the
list at all.
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

# Extension -> accepted leading bytes. None marks plain-text formats, which
# have no signature and are checked for being valid UTF-8 instead.
ALLOWED_ATTACHMENT_TYPES: dict[str, tuple[bytes, ...] | None] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".txt": None,
    ".log": None,
    ".csv": None,
}

# For the file input's `accept` attribute, so the picker only offers these
# types. Only a hint: a user can still choose "All files", and
# validate_attachment below is what actually enforces the list.
ATTACHMENT_ACCEPT = ",".join(ALLOWED_ATTACHMENT_TYPES)

ATTACHMENT_HELP_TEXT = (
    "Optional screenshot, log or document. Allowed: "
    + ", ".join(ext.lstrip(".").upper() for ext in ALLOWED_ATTACHMENT_TYPES if ext != ".jpeg")
    + f", up to {filesizeformat(MAX_ATTACHMENT_BYTES)}."
)

_SNIFF_BYTES = 4096


def validate_attachment(file):
    # Files already in storage were validated when they were uploaded;
    # re-checking them would mean downloading from object storage on every save.
    if getattr(file, "_committed", False):
        return

    extension = Path(file.name).suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_TYPES:
        raise ValidationError(
            "Files of type %(ext)s aren't accepted.",
            code="attachment_type",
            params={"ext": extension or "(no extension)"},
        )

    if file.size > MAX_ATTACHMENT_BYTES:
        raise ValidationError(
            "This file is %(size)s; the limit is %(limit)s.",
            code="attachment_size",
            params={
                "size": filesizeformat(file.size),
                "limit": filesizeformat(MAX_ATTACHMENT_BYTES),
            },
        )

    file.seek(0)
    head = file.read(_SNIFF_BYTES)
    file.seek(0)

    signatures = ALLOWED_ATTACHMENT_TYPES[extension]
    if signatures is None:
        if not _looks_like_text(head):
            raise ValidationError(
                "This doesn't look like a plain text file.", code="attachment_content"
            )
    elif not head.startswith(signatures):
        raise ValidationError(
            "The file's contents don't match its %(ext)s extension.",
            code="attachment_content",
            params={"ext": extension},
        )


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # The sample may cut a multi-byte character in half at the end.
        return exc.start >= len(head) - 3
    return True
