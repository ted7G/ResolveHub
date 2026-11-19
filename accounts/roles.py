"""
Roles, defined in code and synced to Django groups by `manage.py setup_roles`.

Keeping them here rather than clicking them together in the admin means the
permission set is reviewable, versioned and identical in every environment.
Syncing is exact: permissions removed from this file are removed from the
group too.
"""

from django.contrib.auth.models import Group, Permission
from django.db import transaction

SUPPORT_ADMIN = "Support admin"
AGENT = "Agent"
VIEWER = "Viewer"

_TICKET_MODELS = ["ticket", "comment", "customer", "agent", "tag"]


def _model_perms(actions, models=_TICKET_MODELS, app="tickets"):
    return [f"{app}.{action}_{model}" for model in models for action in actions]


ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Runs the desk: full control of help desk data, can manage staff
    # accounts, but can't touch superusers or grant raw permissions
    # (see accounts.admin).
    SUPPORT_ADMIN: [
        *_model_perms(["view", "add", "change", "delete"]),
        "tickets.manage_all_tickets",
        "tickets.view_internal_note",
        "auth.view_user",
        "auth.add_user",
        "auth.change_user",
        "auth.view_group",
    ],
    # Works tickets: sees everything on the desk, edits tickets that are
    # theirs or unassigned, can't delete anything or manage agents.
    AGENT: [
        *_model_perms(["view"]),
        "tickets.add_ticket",
        "tickets.change_ticket",
        "tickets.add_comment",
        "tickets.view_internal_note",
        "tickets.add_customer",
        "tickets.change_customer",
        "tickets.add_tag",
    ],
    # Read-only access for stakeholders, e.g. account managers. Internal
    # notes are hidden from them.
    VIEWER: [
        *_model_perms(["view"]),
    ],
}


def _resolve(codename_with_app):
    app_label, codename = codename_with_app.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@transaction.atomic
def sync_roles():
    """Create or update every role group to match ROLE_PERMISSIONS exactly."""
    for name, perm_names in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set([_resolve(p) for p in perm_names])
