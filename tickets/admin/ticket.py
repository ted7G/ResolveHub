import re

from django.contrib import admin
from django.db.models import Count

from tickets.models import Ticket
from tickets.rules import Status

from . import display
from .filters import AssignmentFilter, DeadlineFilter
from .forms import TicketAdminForm
from .inlines import AddCommentInline, CommentHistoryInline

# Matches "RH-00042", "rh-42" or just "42" in the search box.
_REFERENCE_RE = re.compile(r"(?:rh-)?0*(\d{1,9})", re.IGNORECASE)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
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
        "created_at",
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
    list_select_related = ["customer", "assignee__user"]
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
        ("Handling", {"fields": ["status", "priority", "assignee", "tags"]}),
        (
            "Timeline",
            {
                "fields": ["created_at", "due_at", "resolved_at", "closed_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    inlines = [CommentHistoryInline, AddCommentInline]

    class Media:
        css = {"all": ["tickets/admin.css"]}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(comment_count=Count("comments"))

    def has_change_permission(self, request, obj=None):
        # Closed is final, so a closed ticket is read-only for everyone.
        if obj is not None and obj.status == Status.CLOSED:
            return False
        return super().has_change_permission(request, obj)

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        match = _REFERENCE_RE.fullmatch(search_term.strip())
        if match:
            queryset |= self.get_queryset(request).filter(pk=int(match.group(1)))
        return queryset, may_have_duplicates

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

    @admin.display(description="Comments", ordering="comment_count")
    def comment_count(self, obj):
        return obj.comment_count
