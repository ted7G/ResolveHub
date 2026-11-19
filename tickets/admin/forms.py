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

    class Meta:
        model = Ticket
        fields = ["subject", "description", "customer", "status", "priority", "assignee", "tags"]

    def __init__(self, *args, **kwargs):
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
            self.fields["assignee"].queryset = Agent.objects.select_related("user").filter(
                Q(is_available=True) | Q(pk=ticket._loaded_assignee_id)
            )
