"""Small HTML helpers shared by the admin list and detail views."""

from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.html import format_html
from django.utils.timesince import timesince, timeuntil

from tickets import rules

# Badge text where the full label is too long for a list column.
_SHORT_STATUS = {rules.Status.PENDING: "Waiting"}


def status_badge(ticket):
    label = ticket.get_status_display()
    return format_html(
        '<span class="rh-badge rh-status-{}" title="{}">{}</span>',
        ticket.status,
        label,
        _SHORT_STATUS.get(ticket.status, label),
    )


def priority_badge(ticket):
    return format_html(
        '<span class="rh-badge rh-priority-{}">{}</span>',
        ticket.priority,
        ticket.get_priority_display(),
    )


def deadline_label(ticket):
    if ticket.status not in rules.ACTIVE_STATUSES:
        return "-"
    if ticket.is_overdue:
        return format_html(
            '<span class="rh-deadline rh-overdue">Overdue by {}</span>',
            timesince(ticket.due_at, depth=1),
        )
    return format_html(
        '<span class="rh-deadline">Due in {}</span>', timeuntil(ticket.due_at, depth=1)
    )


def short_date(value):
    """'Nov 20, 2026' for list columns, with the exact time on hover."""
    local = timezone.localtime(value)
    return format_html(
        '<time datetime="{}" title="{}">{}</time>',
        local.isoformat(),
        date_format(local, "j M Y, H:i"),
        date_format(local, "M j, Y"),
    )


def admin_link(obj, label=None):
    if obj is None:
        return "-"
    url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
    return format_html('<a href="{}">{}</a>', url, label or obj)


def ticket_summary(ticket):
    """Facts for the strip above the ticket form."""
    return {
        "reference": ticket.reference,
        "status": rules.Status(ticket.status),
        "priority": rules.Priority(ticket.priority),
        "deadline": deadline_label(ticket),
        "customer": admin_link(ticket.customer, ticket.customer.name),
        "created_at": ticket.created_at,
    }
