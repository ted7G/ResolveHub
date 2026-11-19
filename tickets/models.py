from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="customer_email_unique_ci"),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def clean(self):
        self.email = self.email.strip().lower()


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
