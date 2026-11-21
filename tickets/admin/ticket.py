import re

from django.contrib import admin
from django.db.models import Count, Q

from tickets import rules
from tickets.models import Agent, Ticket
from tickets.permissions import can_edit_ticket, readonly_reason
from tickets.rules import Status

from . import actions, display
from .enhancements import AdminEnhancementsMixin
from .filters import AssignmentFilter, DeadlineFilter
from .forms import TicketAdminForm
from .inlines import AddCommentInline, CommentHistoryInline

# Matches "RH-00042", "rh-42" or just "42" in the search box.
_REFERENCE_RE = re.compile(r"(?:rh-)?0*(\d{1,9})", re.IGNORECASE)


@admin.register(Ticket)
class TicketAdmin(AdminEnhancementsMixin, admin.ModelAdmin):
    form = TicketAdminForm

    list_display = [
        "reference",
        "subject",
        "customer_link",
        "status_badge",
        "priority_badge",
        "assignee",
        "deadline",
        "comment_count",
        "created",
    ]
    list_display_links = ["reference", "subject"]
    list_filter = [
        DeadlineFilter,
        "status",
        "priority",
        AssignmentFilter,
        "assignee__team",
        ("assignee", admin.RelatedOnlyFieldListFilter),
        "tags",
    ]
    search_fields = ["subject", "customer__name", "customer__email", "customer__company"]
    search_help_text = (
        "Search by subject, customer name, email or company, or a ticket number such as RH-00042."
    )
    date_hierarchy = "created_at"
    list_per_page = 50
    # Counting every row on each page load gets slow on large tables; the
    # filtered count is still shown.
    show_full_result_count = False

    autocomplete_fields = ["customer", "tags"]
    readonly_fields = [
        "reference",
        "created_at",
        "due_at",
        "resolved_at",
        "closed_at",
        "updated_at",
    ]
    fieldsets = [
        (None, {"fields": ["reference", "subject", "description", "customer"]}),
        # "rh-side" puts these in the right-hand column on wide screens.
        (
            "Handling",
            {"fields": ["status", "priority", "assignee", "tags"], "classes": ["rh-side"]},
        ),
        (
            "Timeline",
            {
                "fields": ["created_at", "due_at", "resolved_at", "closed_at", "updated_at"],
                "classes": ["collapse", "rh-side"],
            },
        ),
    ]

    inlines = [CommentHistoryInline, AddCommentInline]

    action_form = actions.TicketActionForm
    actions = [
        actions.assign_to_me,
        actions.assign_to_agent,
        actions.mark_open,
        actions.mark_pending,
        actions.mark_resolved,
        actions.mark_closed,
    ]

    def get_queryset(self, request):
        # Joined here rather than via list_select_related: the changelist skips
        # list_select_related when the queryset already selects related rows,
        # and the change view needs the assignee for the permission check.
        return (
            super()
            .get_queryset(request)
            .select_related("customer", "assignee__user")
            .annotate(comment_count=self._comment_count(request))
        )

    def _comment_count(self, request):
        # Without access to internal notes the count shouldn't reveal them.
        if request.user.has_perm("tickets.view_internal_note"):
            return Count("comments")
        return Count("comments", filter=Q(comments__is_internal=False))

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if self.has_manage_all_permission(request):
            return form

        class OwnTicketsForm(form):
            # Agents pick tickets up for themselves; handing one to a
            # colleague is a support admin's call, as with the bulk action.
            assignee_limit = Agent.objects.filter(user=request.user)

        return OwnTicketsForm

    def has_manage_all_permission(self, request):
        return request.user.has_perm("tickets.manage_all_tickets")

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        return obj is None or can_edit_ticket(request.user, obj)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj is not None:
            # The heading and strip describe the ticket as saved. After a
            # failed save `obj` already holds the user's edits, so re-read it.
            saved = obj
            if request.method == "POST":
                saved = Ticket.objects.select_related("customer").get(pk=obj.pk)
            context["ticket_summary"] = display.ticket_summary(saved)
            # The subject reads better than "Change ticket" as the page heading;
            # the reference and status are in the strip underneath.
            context["title"] = saved.subject
            context["subtitle"] = None
            if not self.has_change_permission(request, obj):
                context["readonly_reason"] = readonly_reason(request.user, obj)
        return super().render_change_form(request, context, add, change, form_url, obj)

    def assistant_notes(self, request, obj):
        """Ticket-specific limits for the form assistant (see assistant.context)."""
        user = request.user
        notes = []
        if obj is not None:
            current = Status(obj._loaded_status)
            following = [Status(s).label for s in rules.allowed_next_statuses(current)]
            notes.append(
                f"This ticket is currently {current.label}. "
                + (
                    f"From here its status can change to: {', '.join(following)}."
                    if following
                    else "Closed is final, so its status can't change any more."
                )
            )
        if obj is not None and not self.has_change_permission(request, obj):
            notes.append(f"Why: {readonly_reason(user, obj)}")
        if user.has_perm("tickets.change_ticket") and not self.has_manage_all_permission(request):
            notes.append(
                "They can assign tickets only to themselves (or leave them unassigned); "
                "giving a ticket to a colleague is done by a support admin."
            )
        if not user.has_perm("tickets.view_internal_note"):
            notes.append("They can't see or write internal notes.")
        if obj is None and hasattr(user, "agent_profile"):
            notes.append(
                'Their own tickets ("my tickets") are the Assignment filter set to '
                "Assigned to me; combine it with other filters, e.g. Deadline set to Overdue."
            )
        return notes

    def get_search_results(self, request, queryset, search_term):
        matches, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        reference = _REFERENCE_RE.fullmatch(search_term.strip())
        if reference:
            # Narrow the incoming queryset rather than OR-ing in a fresh one,
            # so the sidebar filters still apply and joins added by them
            # can't multiply the comment counts.
            matches = queryset.filter(
                Q(pk__in=matches.values("pk")) | Q(pk=int(reference.group(1)))
            )
        return matches, may_have_duplicates

    @admin.display(description="Ticket", ordering="pk")
    def reference(self, obj):
        return obj.reference

    @admin.display(description="Customer", ordering="customer__name")
    def customer_link(self, obj):
        return display.admin_link(obj.customer, obj.customer.name)

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return display.status_badge(obj)

    @admin.display(description="Priority", ordering="priority")
    def priority_badge(self, obj):
        return display.priority_badge(obj)

    @admin.display(description="Deadline", ordering="due_at")
    def deadline(self, obj):
        return display.deadline_label(obj)

    @admin.display(description="Created", ordering="created_at")
    def created(self, obj):
        return display.short_date(obj.created_at)

    @admin.display(description="Comments", ordering="comment_count")
    def comment_count(self, obj):
        return obj.comment_count
