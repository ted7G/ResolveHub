"""Object-level rules on top of Django's model permissions."""

from .rules import Status


def can_edit_ticket(user, ticket):
    """
    Model permissions say whether someone may edit tickets at all; this says
    whether they may edit this one. Agents work their own tickets and can
    pick up unassigned ones; editing a colleague's ticket needs the
    manage_all_tickets permission. Closed tickets are read-only for everyone.
    """
    if ticket.status == Status.CLOSED:
        return False
    if user.has_perm("tickets.manage_all_tickets"):
        return True
    return ticket.assignee_id is None or ticket.assignee.user_id == user.pk


def readonly_reason(user, ticket):
    """Explanation shown on a ticket the user can open but not edit."""
    if ticket.status == Status.CLOSED:
        return "This ticket is closed, so it can no longer be changed."
    if not user.has_perm("tickets.change_ticket"):
        return "Your role has read-only access to tickets."
    return f"This ticket belongs to {ticket.assignee}. You can read it, but only they or a support admin can make changes."
