"""Object-level rules on top of Django's model permissions."""

from .models import Agent
from .rules import Status


def _stored_assignee(ticket):
    """The assignee as saved, not as edited in a form that hasn't saved yet."""
    if ticket._loaded_assignee_id is None:
        return None
    if ticket.assignee_id == ticket._loaded_assignee_id:
        return ticket.assignee
    return Agent.objects.get(pk=ticket._loaded_assignee_id)


def can_edit_ticket(user, ticket):
    """
    Model permissions say whether someone may edit tickets at all; this says
    whether they may edit this one. Agents work their own tickets and can
    pick up unassigned ones; editing a colleague's ticket needs the
    manage_all_tickets permission. Closed tickets are read-only for everyone.

    Judged on the saved ticket: a form that fails validation has already
    copied the user's edits onto the instance, and those shouldn't decide
    whether the page comes back editable.
    """
    if ticket._loaded_status == Status.CLOSED:
        return False
    if user.has_perm("tickets.manage_all_tickets"):
        return True
    assignee = _stored_assignee(ticket)
    return assignee is None or assignee.user_id == user.pk


def readonly_reason(user, ticket):
    """Explanation shown on a ticket the user can open but not edit."""
    if ticket._loaded_status == Status.CLOSED:
        return "This ticket is closed, so it can no longer be changed."
    if not user.has_perm("tickets.change_ticket"):
        return "Your role has read-only access to tickets."
    return (
        f"This ticket belongs to {_stored_assignee(ticket)}. You can read it, "
        "but only they or a support admin can make changes."
    )
