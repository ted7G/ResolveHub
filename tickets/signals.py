from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Comment


@receiver(post_delete, sender=Comment)
def delete_stored_attachment(sender, instance, **kwargs):
    """
    Remove a deleted message's file from object storage, including when a
    whole ticket is deleted. Done after commit, so a rolled-back delete
    doesn't lose the file.
    """
    if instance.attachment:
        name, storage = instance.attachment.name, instance.attachment.storage
        transaction.on_commit(lambda: storage.delete(name))
