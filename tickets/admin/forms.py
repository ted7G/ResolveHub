from django import forms
from django.db.models import Q

from tickets import rules
from tickets.models import Agent, Ticket
from tickets.rules import Status


class TicketAdminForm(forms.ModelForm):
    """
    Narrows the status and assignee dropdowns to choices that would pass
    validation, so people aren't offered options that can only fail. The
    model still validates everything; this is about not wasting a click.
    """

    # Set by TicketAdmin for people who may only assign tickets to themselves.
    assignee_limit = None

    class Meta:
        model = Ticket
        fields = ["subject", "description", "customer", "status", "priority", "assignee", "tags"]

    def __init__(self, *args, agents=None, **kwargs):
        # `agents`: agents already loaded by an inline formset, so each row
        # doesn't query for the same dropdown again.
        super().__init__(*args, **kwargs)
        ticket = self.instance

        if "status" in self.fields:
            current = ticket._loaded_status
            allowed = (
                {current, *rules.allowed_next_statuses(current)}
                if current
                else {Status.NEW, Status.OPEN}
            )
            self.fields["status"].choices = [
                (value, label) for value, label in Status.choices if value in allowed
            ]

        if "assignee" in self.fields:
            field = self.fields["assignee"]
            field.queryset = Agent.objects.select_related("user").filter(
                Q(is_available=True) | Q(pk=ticket._loaded_assignee_id)
            )
            if self.assignee_limit is not None:
                field.queryset = field.queryset.filter(pk__in=self.assignee_limit.values("pk"))
            if agents is not None:
                offered = [
                    agent
                    for agent in agents
                    if agent.is_available or agent.pk == ticket._loaded_assignee_id
                ]
                empty = [("", field.empty_label)] if field.empty_label is not None else []
                field.choices = empty + [(agent.pk, str(agent)) for agent in offered]
