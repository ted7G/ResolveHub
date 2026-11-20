"""
Bulk actions for the ticket list.

Each action runs every selected ticket through the same model methods the
edit form uses, one ticket per transaction. Tickets that can't be changed
are skipped and reported with the reason, so a partial success is visible
instead of silently ignored.
"""

from collections import Counter

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.core.exceptions import ValidationError
from django.db import transaction

from tickets.models import Agent
from tickets.rules import Status


class TicketActionForm(ActionForm):
    """Adds an agent picker next to the action dropdown for bulk assignment."""

    agent = forms.ModelChoiceField(
        queryset=Agent.objects.none(), required=False, label="Agent", empty_label="(agent)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agent"].queryset = Agent.objects.filter(is_available=True).select_related(
            "user"
        )


def _plural(count):
    return "ticket" if count == 1 else "tickets"


def _apply(modeladmin, request, queryset, change, *, done_message, log_message):
    changed = 0
    skipped = Counter()

    for ticket in queryset.select_related("assignee__user", "customer"):
        if not modeladmin.has_change_permission(request, ticket):
            if ticket.status == Status.CLOSED:
                skipped["closed tickets can't be changed"] += 1
            else:
                skipped["you don't have permission to edit them"] += 1
            continue
        try:
            with transaction.atomic():
                change(ticket)
        except ValidationError as exc:
            skipped[exc.messages[0]] += 1
            continue
        modeladmin.log_change(request, ticket, log_message)
        changed += 1

    if changed:
        modeladmin.message_user(
            request, f"{changed} {_plural(changed)} {done_message}.", messages.SUCCESS
        )
    for reason, count in skipped.most_common():
        modeladmin.message_user(
            request, f"{count} {_plural(count)} skipped: {reason}", messages.WARNING
        )


def _status_action(status):
    label = Status(status).label

    def action(modeladmin, request, queryset):
        _apply(
            modeladmin,
            request,
            queryset,
            lambda ticket: ticket.transition_to(status),
            done_message=f"moved to {label}",
            log_message=f"Changed status to {label} (bulk action).",
        )

    action.__name__ = f"mark_{status}"
    return admin.action(description=f"Move selected tickets to {label}", permissions=["change"])(
        action
    )


mark_open = _status_action(Status.OPEN)
mark_pending = _status_action(Status.PENDING)
mark_resolved = _status_action(Status.RESOLVED)
mark_closed = _status_action(Status.CLOSED)


def _assign(ticket, agent):
    ticket.assignee = agent
    ticket.clean()
    ticket.save()


@admin.action(description="Assign selected tickets to me", permissions=["change"])
def assign_to_me(modeladmin, request, queryset):
    agent = getattr(request.user, "agent_profile", None)
    if agent is None:
        modeladmin.message_user(
            request, "Your login isn't linked to an agent profile.", messages.ERROR
        )
        return
    _apply(
        modeladmin,
        request,
        queryset,
        lambda ticket: _assign(ticket, agent),
        done_message="assigned to you",
        log_message="Assigned to self (bulk action).",
    )


@admin.action(
    description="Assign selected tickets to the agent picked below", permissions=["manage_all"]
)
def assign_to_agent(modeladmin, request, queryset):
    try:
        agent = Agent.objects.select_related("user").get(pk=int(request.POST.get("agent", "")))
    except (ValueError, Agent.DoesNotExist):
        modeladmin.message_user(
            request, "Pick an agent in the box next to the action menu first.", messages.ERROR
        )
        return
    _apply(
        modeladmin,
        request,
        queryset,
        lambda ticket: _assign(ticket, agent),
        done_message=f"assigned to {agent}",
        log_message=f"Assigned to {agent} (bulk action).",
    )


@admin.action(description="Mark selected agents as available", permissions=["change"])
def mark_agents_available(modeladmin, request, queryset):
    updated = queryset.update(is_available=True)
    modeladmin.message_user(request, f"{updated} marked available.", messages.SUCCESS)


@admin.action(description="Mark selected agents as away", permissions=["change"])
def mark_agents_away(modeladmin, request, queryset):
    updated = queryset.update(is_available=False)
    modeladmin.message_user(
        request,
        f"{updated} marked away. Their current tickets stay assigned.",
        messages.SUCCESS,
    )
