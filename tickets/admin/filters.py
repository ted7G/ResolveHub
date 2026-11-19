from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from tickets import rules


class DeadlineFilter(admin.SimpleListFilter):
    title = "deadline"
    parameter_name = "deadline"

    def lookups(self, request, model_admin):
        return [
            ("overdue", "Overdue"),
            ("due_soon", "Due in the next 24 hours"),
            ("on_track", "On track"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        match self.value():
            case "overdue":
                return queryset.overdue(now)
            case "due_soon":
                return queryset.active().filter(
                    due_at__gte=now, due_at__lt=now + timedelta(hours=24)
                )
            case "on_track":
                return queryset.active().filter(due_at__gte=now)
        return queryset


class AssignmentFilter(admin.SimpleListFilter):
    title = "assignment"
    parameter_name = "assigned"

    def lookups(self, request, model_admin):
        options = [("unassigned", "Unassigned"), ("assigned", "Assigned")]
        if hasattr(request.user, "agent_profile"):
            options.insert(0, ("me", "Assigned to me"))
        return options

    def queryset(self, request, queryset):
        match self.value():
            case "me":
                return queryset.filter(assignee__user=request.user)
            case "unassigned":
                return queryset.filter(assignee__isnull=True)
            case "assigned":
                return queryset.filter(assignee__isnull=False)
        return queryset


class HasActiveTicketsFilter(admin.SimpleListFilter):
    title = "active tickets"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return [("yes", "Has active tickets"), ("no", "No active tickets")]

    def queryset(self, request, queryset):
        match self.value():
            case "yes":
                return queryset.filter(tickets__status__in=rules.ACTIVE_STATUSES).distinct()
            case "no":
                return queryset.exclude(tickets__status__in=rules.ACTIVE_STATUSES)
        return queryset
