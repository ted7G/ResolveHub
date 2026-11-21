"""
Upload handling that never writes to local disk and never buffers more than
the attachment limit.

Django's default handlers keep small uploads in memory but spool larger ones
to a temporary file, so an oversized attachment would land on the
container's disk before validation rejected it. This handler keeps at most
one byte past the limit for each file and only counts the rest. The file
still reports its real size, so validate_attachment rejects it with the
usual message. Only the 5 MB check ever sees an oversized file, and it
fails, so a cut-off file can't be saved.
"""

from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler

from .validators import MAX_ATTACHMENT_BYTES

KEEP_BYTES = MAX_ATTACHMENT_BYTES + 1


class CappedMemoryUploadHandler(FileUploadHandler):
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.file = BytesIO()

    def receive_data_chunk(self, raw_data, start):
        room = KEEP_BYTES - self.file.tell()
        if room > 0:
            self.file.write(raw_data[:room])
        # Returning nothing means no other handler receives the chunk.

    def file_complete(self, file_size):
        self.file.seek(0)
        return InMemoryUploadedFile(
            file=self.file,
            field_name=self.field_name,
            name=self.file_name,
            content_type=self.content_type,
            size=file_size,  # the full size received, not what was kept
            charset=self.charset,
            content_type_extra=self.content_type_extra,
        )
