from django.contrib import admin
from django.utils.html import format_html

from tickets.models import Comment, Ticket
from tickets.rules import Status

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

    @admin.display(description="From")
    def author_label(self, obj):
        if obj.author is None:
            return f"{obj.ticket.customer.name} (customer)"
        return obj.author.get_full_name() or obj.author.get_username()

    @admin.display(description="Visibility")
    def visibility(self, obj):
        if obj.is_internal:
            return format_html('<span class="rh-internal-note">Internal note</span>')
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
    can_delete = False

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

    class Media:
        css = {"all": ["tickets/admin.css"]}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("assignee__user")

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
