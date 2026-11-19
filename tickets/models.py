import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from . import rules
from .rules import Priority, Status
from .validators import ATTACHMENT_HELP_TEXT, validate_attachment


class Customer(models.Model):
    name = models.CharField(
        max_length=120, help_text="Full name of the person who contacts support."
    )
    email = models.EmailField(
        help_text="Primary contact address. Each customer needs a unique email (case-insensitive)."
    )
    company = models.CharField(
        max_length=120, blank=True, help_text="Organisation the customer belongs to, if any."
    )
    phone = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional. Include the country code, e.g. +44 20 7946 0000.",
    )
    # A default rather than auto_now_add so imported or seeded customers can
    # keep their original sign-up date.
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="customer_email_unique_ci"),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def clean(self):
        self.email = self.email.strip().lower()


class AgentManager(models.Manager):
    def get_queryset(self):
        # An agent's display name lives on the user row, and agents are almost
        # always shown by name (dropdowns, filters, list columns).
        return super().get_queryset().select_related("user")


class Agent(models.Model):
    class Team(models.TextChoices):
        GENERAL = "general", "General support"
        BILLING = "billing", "Billing"
        TECHNICAL = "technical", "Technical"
        ACCOUNTS = "accounts", "Accounts"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_profile",
        help_text="Staff login this agent signs in with.",
    )
    team = models.CharField(
        max_length=20,
        choices=Team.choices,
        default=Team.GENERAL,
        help_text="Queue the agent mainly works on. Used for filtering and reporting.",
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Untick while the agent is away. Unavailable agents can't receive new assignments.",
    )

    objects = AgentManager()

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


class Tag(models.Model):
    name = models.CharField(
        max_length=40,
        help_text="Short lowercase label such as 'billing' or 'login-issue'. Must be unique.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="tag_name_unique_ci"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        self.name = self.name.strip().lower()


class TicketQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status__in=rules.ACTIVE_STATUSES)

    def overdue(self, now=None):
        return self.active().filter(due_at__lt=now or timezone.now())


class Ticket(models.Model):
    subject = models.CharField(
        max_length=200, help_text="One-line summary of the problem, as the customer would put it."
    )
    description = models.TextField(
        help_text="Full description of the issue: what happened, what was expected, any error messages."
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="tickets",
        help_text="Customer who reported the issue. Customers with tickets can't be deleted.",
    )
    assignee = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        help_text="Agent responsible for the ticket. Required before it can be opened.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        help_text=(
            "Where the ticket is in the workflow. Only valid next steps are offered; "
            "closed tickets can't be reopened."
        ),
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        help_text=f"Sets the response deadline from creation time: {rules.describe_sla()}.",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="tickets",
        help_text="Labels used to group similar tickets. Pick any that apply.",
    )
    # Not auto_now_add so the seed command can create historical tickets.
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    due_at = models.DateTimeField(
        editable=False, help_text="Response deadline, calculated from priority."
    )
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)
    closed_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = TicketQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "due_at"], name="ticket_status_due_idx"),
            models.Index(fields=["assignee", "status"], name="ticket_assignee_status_idx"),
            models.Index(fields=["-created_at"], name="ticket_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values), name="ticket_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(priority__in=Priority.values), name="ticket_priority_valid"
            ),
            models.CheckConstraint(
                condition=~models.Q(status=Status.RESOLVED) | models.Q(resolved_at__isnull=False),
                name="ticket_resolved_has_timestamp",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=Status.CLOSED) | models.Q(closed_at__isnull=False),
                name="ticket_closed_has_timestamp",
            ),
        ]
        permissions = [
            ("manage_all_tickets", "Can edit tickets assigned to other agents"),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remember what was loaded from the database so changes can be
        # checked against the workflow. Read from __dict__ to avoid triggering
        # a query when the field was deferred.
        self._loaded_status = self.__dict__.get("status") if self.pk else None
        self._loaded_priority = self.__dict__.get("priority") if self.pk else None
        self._loaded_assignee_id = self.__dict__.get("assignee_id") if self.pk else None

    def __str__(self):
        return f"{self.reference} {self.subject}"

    def save(self, *args, **kwargs):
        if self.due_at is None or self.priority != self._loaded_priority:
            self.due_at = rules.due_at_for(self.created_at, self.priority)
        self._sync_status_timestamps()
        super().save(*args, **kwargs)
        self._loaded_status = self.status
        self._loaded_priority = self.priority
        self._loaded_assignee_id = self.assignee_id

    def clean(self):
        if self.status not in Status.values:
            return  # field validation already reports this
        errors = {}
        previous = self._loaded_status

        if previous is None and self.status not in (Status.NEW, Status.OPEN):
            errors["status"] = "New tickets start as New or Open."
        elif previous is not None and not rules.can_transition(previous, self.status):
            allowed = [Status(s).label for s in rules.allowed_next_statuses(previous)]
            errors["status"] = (
                f"A ticket can't go from {Status(previous).label} to "
                f"{Status(self.status).label}. "
                + (f"Allowed next: {', '.join(allowed)}." if allowed else "Closed is final.")
            )

        if self.status in rules.REQUIRES_ASSIGNEE and self.assignee_id is None:
            errors["assignee"] = (
                f"Assign an agent before setting the status to {Status(self.status).label}."
            )
        elif (
            self.assignee_id is not None
            and self.assignee_id != self._loaded_assignee_id
            and not self.assignee.is_available
        ):
            errors["assignee"] = (
                f"{self.assignee} is marked unavailable and can't take new tickets."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def reference(self):
        return f"RH-{self.pk:05d}" if self.pk else "RH-new"

    @property
    def is_overdue(self):
        return (
            self.status in rules.ACTIVE_STATUSES
            and self.due_at is not None
            and self.due_at < timezone.now()
        )

    @classmethod
    def form_guidance(cls):
        """Plain-language rules for the form assistant, generated from tickets.rules."""
        return [
            "Status workflow, as 'from: allowed next': " + rules.describe_workflow() + ".",
            "Closed is final. If a customer comes back after closure, open a new ticket.",
            "New tickets start as New or Open.",
            "Open, Waiting on customer and Resolved tickets need an assignee.",
            "Only available agents can be given new tickets.",
            f"Response deadline counted from creation, by priority: {rules.describe_sla()}. "
            "Changing the priority recalculates the deadline.",
            "A ticket is overdue while it is New, Open or Waiting on customer past its deadline.",
            "Agents can edit tickets assigned to them and unassigned ones; "
            "support admins can edit any ticket.",
            "Replies are visible to the customer; internal notes are only for staff. "
            "Closed tickets can't take new replies.",
        ]

    def transition_to(self, status):
        """Move the ticket to `status` and save it, or raise ValidationError."""
        if status not in Status.values:
            raise ValidationError({"status": f"Unknown status {status!r}."})
        previous = self.status
        self.status = status
        try:
            self.clean()
        except ValidationError:
            self.status = previous
            raise
        self.save()

    def _sync_status_timestamps(self):
        now = timezone.now()
        if self.status == Status.RESOLVED:
            self.resolved_at = self.resolved_at or now
        elif self.status in rules.ACTIVE_STATUSES:
            # Reopened: the previous resolution no longer counts.
            self.resolved_at = None
        if self.status == Status.CLOSED:
            self.closed_at = self.closed_at or now


def attachment_upload_to(instance, filename):
    # A random object key: the original name is user-controlled, could collide
    # and would leak through the URL. It is kept in attachment_name instead.
    extension = PurePath(filename).suffix.lower()
    return f"attachments/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_comments",
        help_text="Staff member who wrote it. Empty means the message came from the customer.",
    )
    is_internal = models.BooleanField(
        "internal note",
        default=False,
        help_text="Internal notes are for the support team only and are never shown to the customer.",
    )
    body = models.TextField(
        max_length=10_000,
        help_text="The reply or note itself. Plain text, up to 10,000 characters.",
    )
    attachment = models.FileField(
        upload_to=attachment_upload_to,
        blank=True,
        validators=[validate_attachment],
        help_text=ATTACHMENT_HELP_TEXT,
    )
    attachment_name = models.CharField(max_length=255, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"], name="comment_ticket_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(author__isnull=True, is_internal=True),
                name="comment_customer_messages_are_public",
            ),
        ]
        permissions = [
            ("view_internal_note", "Can see internal notes"),
        ]

    def __str__(self):
        kind = "Internal note" if self.is_internal else "Reply"
        return f"{kind} on {self.ticket.reference}"

    def save(self, *args, **kwargs):
        if self.attachment and not self.attachment._committed:
            self.attachment_name = PurePath(self.attachment.name).name[:255]
        elif not self.attachment:
            self.attachment_name = ""
        super().save(*args, **kwargs)

    def clean(self):
        if self.pk is None and self.ticket_id and self.ticket.status == Status.CLOSED:
            raise ValidationError(
                "This ticket is closed, so it can't take new comments. Open a new ticket instead."
            )
        if self.is_internal and self.author_id is None:
            raise ValidationError({"is_internal": "Customer messages can't be internal notes."})
