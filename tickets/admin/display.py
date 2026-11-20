"""Small HTML helpers shared by the admin list and detail views."""

from django.urls import reverse
from django.utils.html import format_html
from django.utils.timesince import timesince, timeuntil

from tickets import rules


def status_badge(ticket):
    return format_html(
        '<span class="rh-badge rh-status-{}">{}</span>', ticket.status, ticket.get_status_display()
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


def admin_link(obj, label=None):
    if obj is None:
        return "-"
    url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
    return format_html('<a href="{}">{}</a>', url, label or obj)
