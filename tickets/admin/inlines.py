from django.contrib import admin
from django.db.models import Q
from django.utils.html import format_html

from tickets.models import Agent, Comment, Ticket
from tickets.permissions import can_edit_ticket
from tickets.rules import Status
from tickets.validators import ATTACHMENT_ACCEPT

from . import display
from .forms import TicketAdminForm


def can_see_internal_notes(user):
    return user.has_perm("tickets.view_internal_note")


class CommentHistoryInline(admin.StackedInline):
    """
    The conversation so far. Read-only: what was said to a customer
    shouldn't be rewritten after the fact.
    """

    model = Comment
    verbose_name = "message"
    verbose_name_plural = "Conversation"
    # Shown as a chat thread instead of a stack of read-only forms.
    template = "admin/tickets/ticket/conversation.html"
    extra = 0
    fields = ["created_at", "author_label", "visibility", "body", "attachment_link"]
    readonly_fields = fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("author", "ticket__customer")
        if not can_see_internal_notes(request.user):
            queryset = queryset.filter(is_internal=False)
        return queryset

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Deleting a message rewrites the conversation just as editing would.
        return False

    @admin.display(description="From")
    def author_label(self, obj):
        if obj.author is None:
            return f"{obj.ticket.customer.name} (customer)"
        return obj.author.get_full_name() or obj.author.get_username()

    @admin.display(description="Visibility")
    def visibility(self, obj):
        if obj.is_internal:
            return format_html('<span class="rh-internal-note">{}</span>', "Internal note")
        return "Visible to customer"

    @admin.display(description="Attachment")
    def attachment_link(self, obj):
        if not obj.attachment:
            return "-"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
            obj.attachment.url,
            obj.attachment_name or "Download",
        )


class AddCommentInline(admin.StackedInline):
    """A blank form for adding a reply or note; the author is the logged-in user."""

    model = Comment
    verbose_name = "reply or internal note"
    verbose_name_plural = "Add a reply"
    extra = 1
    max_num = 1
    can_delete = False

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "body":
            placeholder = "Write a reply to the customer"
            if can_see_internal_notes(request.user):
                placeholder += ", or an internal note for the team"
            field.widget.attrs.update(rows=5, placeholder=placeholder)
        elif db_field.name == "attachment":
            field.widget.attrs["accept"] = ATTACHMENT_ACCEPT
        return field

    def get_fields(self, request, obj=None):
        if can_see_internal_notes(request.user):
            return ["body", "is_internal", "attachment"]
        return ["body", "attachment"]

    def get_queryset(self, request):
        return super().get_queryset(request).none()

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        # Otherwise Django still renders an empty "Add a reply" block on pages
        # where replying isn't allowed.
        return self.has_add_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj is not None:
            if obj.status == Status.CLOSED:
                return False
            ticket_admin = self.admin_site.get_model_admin(Ticket)
            if not ticket_admin.has_change_permission(request, obj):
                return False
        return super().has_add_permission(request, obj)

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        author = request.user

        class AuthoredFormSet(formset_class):
            # Set the author before validation so model rules that depend on
            # it (customer messages can't be internal) see the real value.
            def _construct_form(self, i, **form_kwargs):
                form = super()._construct_form(i, **form_kwargs)
                if form.instance.author_id is None:
                    form.instance.author = author
                return form

        return AuthoredFormSet


class CustomerTicketInline(admin.TabularInline):
    """
    Quick triage of all of a customer's tickets from the customer page. Only
    people allowed to edit any ticket get editable rows; everyone else sees
    the same list read-only and can click through.
    """

    model = Ticket
    form = TicketAdminForm
    fields = ["reference", "subject", "status", "priority", "assignee", "deadline"]
    readonly_fields = ["reference", "deadline"]
    ordering = ["-created_at"]
    extra = 0
    can_delete = False
    show_change_link = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("assignee__user")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "assignee":
            # A row per ticket: the edit/add/delete/view icons next to every
            # assignee box would be noise. Agents are managed on their own page.
            widget = field.widget
            widget.can_add_related = widget.can_change_related = False
            widget.can_delete_related = widget.can_view_related = False
        return field

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        user = request.user

        class SharedAgentsFormSet(formset_class):
            # The page-level check says the user may edit tickets; each row
            # still follows the per-ticket rule, so a closed ticket stays
            # locked here too. Disabled fields ignore submitted values.
            def _construct_form(self, i, **kwargs):
                form = super()._construct_form(i, **kwargs)
                if form.instance.pk and not can_edit_ticket(user, form.instance):
                    for name in form._meta.fields:
                        if name in form.fields:
                            form.fields[name].disabled = True
                return form

            # Every row offers the same agents; load them once for the page
            # instead of once per ticket.
            def get_form_kwargs(self, index):
                kwargs = super().get_form_kwargs(index)
                if not hasattr(self, "_agents"):
                    assigned = {t.assignee_id for t in self.get_queryset() if t.assignee_id}
                    self._agents = list(
                        Agent.objects.select_related("user").filter(
                            Q(is_available=True) | Q(pk__in=assigned)
                        )
                    )
                kwargs["agents"] = self._agents
                return kwargs

        return SharedAgentsFormSet

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and request.user.has_perm(
            "tickets.manage_all_tickets"
        )

    @admin.display(description="Ticket")
    def reference(self, obj):
        return obj.reference

    @admin.display(description="Deadline")
    def deadline(self, obj):
        return display.deadline_label(obj)
