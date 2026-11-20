import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Comment

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Comment)
def delete_stored_attachment(sender, instance, **kwargs):
    """
    Remove a deleted message's file from object storage, including when a
    whole ticket is deleted. Done after commit, so a rolled-back delete
    doesn't lose the file.
    """
    if not instance.attachment:
        return
    name, storage = instance.attachment.name, instance.attachment.storage

    def remove():
        # The database delete has already succeeded; a storage outage should
        # leave an orphaned file in the log, not turn it into an error page.
        try:
            storage.delete(name)
        except Exception:
            logger.exception("Could not delete attachment %s from storage", name)

    transaction.on_commit(remove)
