from django.contrib import admin
from django.db.models import Count, Q
from django.db.models.functions import Now

from tickets import rules
from tickets.models import Agent, Customer, Tag

from . import actions
from .filters import HasActiveTicketsFilter
from .inlines import CustomerTicketInline
from .searchable import SearchableSelectsMixin

_ACTIVE = Q(tickets__status__in=rules.ACTIVE_STATUSES)


@admin.register(Customer)
class CustomerAdmin(SearchableSelectsMixin, admin.ModelAdmin):
    list_display = ["name", "email", "company", "active_tickets", "total_tickets", "created_at"]
    list_filter = [HasActiveTicketsFilter, "created_at"]
    search_fields = ["name", "email", "company"]
    list_per_page = 50
    show_full_result_count = False
    readonly_fields = ["created_at"]
    inlines = [CustomerTicketInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                active_count=Count("tickets", filter=_ACTIVE),
                total_count=Count("tickets"),
            )
        )

    @admin.display(description="Active tickets", ordering="active_count")
    def active_tickets(self, obj):
        return obj.active_count

    @admin.display(description="All tickets", ordering="total_count")
    def total_tickets(self, obj):
        return obj.total_count


@admin.register(Agent)
class AgentAdmin(SearchableSelectsMixin, admin.ModelAdmin):
    list_display = ["__str__", "username", "team", "is_available", "active_tickets", "overdue"]
    list_filter = ["team", "is_available"]
    list_editable = ["is_available"]
    search_fields = ["user__first_name", "user__last_name", "user__username", "user__email"]
    list_select_related = ["user"]
    autocomplete_fields = ["user"]
    actions = [actions.mark_agents_available, actions.mark_agents_away]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                active_count=Count("tickets", filter=_ACTIVE),
                overdue_count=Count("tickets", filter=_ACTIVE & Q(tickets__due_at__lt=Now())),
            )
        )

    @admin.display(description="Login", ordering="user__username")
    def username(self, obj):
        return obj.user.username

    @admin.display(description="Active tickets", ordering="active_count")
    def active_tickets(self, obj):
        return obj.active_count

    @admin.display(description="Overdue", ordering="overdue_count")
    def overdue(self, obj):
        return obj.overdue_count


@admin.register(Tag)
class TagAdmin(SearchableSelectsMixin, admin.ModelAdmin):
    list_display = ["name", "ticket_count"]
    search_fields = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(ticket_count=Count("tickets"))

    @admin.display(description="Tickets", ordering="ticket_count")
    def ticket_count(self, obj):
        return obj.ticket_count
