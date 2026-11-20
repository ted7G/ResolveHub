"""
Fill the database with a realistic help desk: staff, customers, a few
thousand tickets spread over the last six months and their conversations.

Rows are written with bulk_create for speed, which skips Model.save(). The
values that save() would normally derive (deadlines, resolution and closing
times) are computed here with the same rules module, and the database
constraints still apply, so the data stays consistent with the workflow.
"""

import os
import random
import secrets
import struct
import zlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from faker import Faker

from accounts.roles import AGENT, SUPPORT_ADMIN, VIEWER, sync_roles
from tickets import rules
from tickets.models import Agent, Comment, Customer, Tag, Ticket, attachment_upload_to
from tickets.rules import Priority, Status

from . import _seed_content as content

User = get_user_model()

# Seeded staff accounts use this reserved domain, so --reset can remove them
# without touching real accounts.
DEMO_EMAIL_DOMAIN = "staff.resolvehub.test"

DEMO_ACCOUNTS = [
    # username, first name, last name, role, agent team (None: not an agent)
    ("admin", "Alex", "Morgan", SUPPORT_ADMIN, Agent.Team.GENERAL),
    ("agent", "Sam", "Patel", AGENT, Agent.Team.TECHNICAL),
    ("viewer", "Jordan", "Lee", VIEWER, None),
]

AGENT_TEAMS = (
    [Agent.Team.TECHNICAL] * 5
    + [Agent.Team.BILLING] * 3
    + [Agent.Team.ACCOUNTS] * 3
    + [Agent.Team.GENERAL] * 3
)

PRIORITY_WEIGHTS = {Priority.LOW: 20, Priority.NORMAL: 50, Priority.HIGH: 22, Priority.URGENT: 8}


def _status_weights(age):
    """Older tickets are mostly finished; recent ones are mostly in progress."""
    if age < timedelta(hours=6):
        return {Status.NEW: 55, Status.OPEN: 35, Status.PENDING: 5, Status.RESOLVED: 5}
    if age < timedelta(days=3):
        return {Status.NEW: 15, Status.OPEN: 40, Status.PENDING: 25, Status.RESOLVED: 20}
    if age < timedelta(days=14):
        return {
            Status.NEW: 1,
            Status.OPEN: 6,
            Status.PENDING: 8,
            Status.RESOLVED: 45,
            Status.CLOSED: 40,
        }
    return {Status.OPEN: 0.5, Status.PENDING: 1, Status.RESOLVED: 8, Status.CLOSED: 90.5}


class Command(BaseCommand):
    help = "Fill the database with realistic demo data. Use --reset to replace existing data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all help desk data, stored attachments and seeded staff accounts first.",
        )
        parser.add_argument("--customers", type=int, default=400)
        parser.add_argument("--tickets", type=int, default=3000)
        parser.add_argument("--days", type=int, default=180, help="How far back tickets go.")
        parser.add_argument(
            "--attachments",
            type=int,
            default=30,
            help="Number of comments that get a small generated file, uploaded to the "
            "configured storage.",
        )
        parser.add_argument("--seed", type=int, default=2026, help="Random seed.")
        parser.add_argument(
            "--password",
            help="Password for the demo accounts. Defaults to $SEED_DEMO_PASSWORD, "
            "or a random one that is printed at the end.",
        )

    def handle(self, *args, **options):
        self.rng = random.Random(options["seed"])
        self.fake = Faker()
        self.fake.seed_instance(options["seed"])
        self.now = timezone.now()

        password = options["password"] or os.environ.get("SEED_DEMO_PASSWORD")
        generated_password = not password
        if generated_password:
            password = secrets.token_urlsafe(12)

        self._check_demo_usernames_are_free()
        if options["reset"]:
            self._reset()
        elif Ticket.objects.exists():
            raise CommandError("The database already has tickets. Use --reset to replace them.")

        with transaction.atomic():
            sync_roles()
            demo_users = self._create_demo_accounts(password)
            agents = self._create_agents(demo_users)
            tags = self._create_tags()
            customers = self._create_customers(options["customers"], options["days"])
            tickets = self._create_tickets(
                options["tickets"], options["days"], customers, agents, tags
            )
            comments = self._create_comments(tickets)

        attached = self._attach_files(comments, options["attachments"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {len(agents)} agents, {len(customers)} customers, "
                f"{len(tickets)} tickets, {len(comments)} comments ({attached} with attachments)."
            )
        )
        self.stdout.write("Demo logins:")
        for username, *_, role, _team in DEMO_ACCOUNTS:
            self.stdout.write(f"  {username:<12} {role}")
        if generated_password:
            self.stdout.write(f"Password for all three: {password}")

    # --- Reset ---------------------------------------------------------------

    def _reset(self):
        # Stored attachments are removed by the Comment delete signal.
        with transaction.atomic():
            Comment.objects.all().delete()
            Ticket.objects.all().delete()
            Customer.objects.all().delete()
            Tag.objects.all().delete()
            # Real staff keep their logins and their agent profiles.
            User.objects.filter(email__endswith=f"@{DEMO_EMAIL_DOMAIN}").delete()
        self.stdout.write("Removed existing help desk data.")

    # --- Staff ---------------------------------------------------------------

    def _check_demo_usernames_are_free(self):
        """Fail before touching any data if a real account uses a demo name."""
        names = [username for username, *_ in DEMO_ACCOUNTS]
        taken = (
            User.objects.filter(username__in=names)
            .exclude(email__endswith=f"@{DEMO_EMAIL_DOMAIN}")
            .values_list("username", flat=True)
        )
        if taken:
            raise CommandError(
                f"Real accounts already use the demo login names {', '.join(sorted(taken))}. "
                "Rename them first; the seed command never changes real accounts."
            )

    def _create_demo_accounts(self, password):
        users = {}
        for username, first, last, role, _team in DEMO_ACCOUNTS:
            user = User.objects.create_user(
                username=username,
                email=f"{username}@{DEMO_EMAIL_DOMAIN}",
                password=password,
                first_name=first,
                last_name=last,
                is_staff=True,
            )
            user.groups.add(Group.objects.get(name=role))
            users[username] = user
        return users

    def _create_agents(self, demo_users):
        agents = [
            Agent(user=demo_users[username], team=team)
            for username, *_, team in DEMO_ACCOUNTS
            if team is not None
        ]
        agent_group = Group.objects.get(name=AGENT)
        for index, team in enumerate(AGENT_TEAMS):
            first, last = self.fake.first_name(), self.fake.last_name()
            # Seeded colleagues exist to own tickets; they can't log in.
            user = User(
                username=f"{first}.{last}{index}".lower(),
                email=f"{first}.{last}{index}@{DEMO_EMAIL_DOMAIN}".lower(),
                first_name=first,
                last_name=last,
                is_staff=True,
            )
            user.set_unusable_password()
            user.save()
            user.groups.add(agent_group)
            agents.append(Agent(user=user, team=team, is_available=index not in (2, 9)))
        return Agent.objects.bulk_create(agents)

    # --- Customers and tags --------------------------------------------------

    def _create_tags(self):
        return {tag.name: tag for tag in Tag.objects.bulk_create(Tag(name=n) for n in content.TAGS)}

    def _create_customers(self, count, days):
        companies = [self.fake.unique.company() for _ in range(max(count // 6, 1))]
        seen_emails = set()
        customers = []
        for index in range(count):
            first, last = self.fake.first_name(), self.fake.last_name()
            company = self.rng.choice(companies) if self.rng.random() < 0.8 else ""
            domain = _domain_for(company) if company else self.fake.free_email_domain()
            email = f"{first}.{last}@{domain}".lower()
            if email in seen_emails:
                email = f"{first}.{last}{index}@{domain}".lower()
            seen_emails.add(email)
            customers.append(
                Customer(
                    name=f"{first} {last}",
                    email=email,
                    company=company,
                    phone=self.fake.phone_number() if self.rng.random() < 0.6 else "",
                    created_at=self.now - timedelta(days=days + self.rng.uniform(0, 400)),
                )
            )
        return Customer.objects.bulk_create(customers, batch_size=1000)

    # --- Tickets -------------------------------------------------------------

    def _create_tickets(self, count, days, customers, agents, tags):
        by_team = {}
        for agent in agents:
            by_team.setdefault(agent.team, []).append(agent)
        demo_agent = next(a for a in agents if a.user.username == "agent")
        # A few customers raise most tickets, like in real life.
        customer_weights = [1 / (rank + 1) ** 0.35 for rank in range(len(customers))]
        category_weights = [c["weight"] for c in content.CATEGORIES]

        tickets, ticket_tags = [], []
        for _ in range(count):
            category = self.rng.choices(content.CATEGORIES, weights=category_weights)[0]
            customer = self.rng.choices(customers, weights=customer_weights)[0]
            # Skewed towards recent days so the active queue looks busy.
            created = self.now - timedelta(days=days * self.rng.random() ** 1.6)
            created = max(created, customer.created_at + timedelta(hours=1))
            priority = _weighted(self.rng, PRIORITY_WEIGHTS)
            status = _weighted(self.rng, _status_weights(self.now - created))

            assignee = None
            if status != Status.NEW or self.rng.random() < 0.25:
                if category["team"] == Agent.Team.TECHNICAL and self.rng.random() < 0.3:
                    assignee = demo_agent
                else:
                    assignee = self.rng.choice(by_team.get(category["team"], agents))

            ticket = Ticket(
                subject=self._fill(self.rng.choice(category["subjects"]), customer),
                description=self._fill(self.rng.choice(category["descriptions"]), customer),
                customer=customer,
                assignee=assignee,
                priority=priority,
                created_at=created,
                due_at=rules.due_at_for(created, priority),
            )
            self._set_outcome(ticket, status)
            tickets.append(ticket)
            ticket_tags.append(self.rng.sample(category["tags"], k=self.rng.randint(1, 2)))

        tickets = Ticket.objects.bulk_create(tickets, batch_size=500)
        Ticket.tags.through.objects.bulk_create(
            [
                Ticket.tags.through(ticket_id=ticket.pk, tag_id=tags[name].pk)
                for ticket, names in zip(tickets, ticket_tags, strict=True)
                for name in names
            ],
            batch_size=2000,
        )
        return tickets

    def _set_outcome(self, ticket, status):
        """Set status and its timestamps so they are consistent with the ticket's age."""
        age = self.now - ticket.created_at
        ticket.status = status
        if status == Status.CLOSED and (ticket.assignee is None or self.rng.random() < 0.08):
            # Spam or duplicate, closed straight from New without a resolution.
            ticket.closed_at = ticket.created_at + age * self.rng.uniform(0.01, 0.1)
            return
        if status in (Status.RESOLVED, Status.CLOSED):
            work = min(age * 0.6, timedelta(days=6)) * self.rng.uniform(0.05, 1)
            ticket.resolved_at = ticket.created_at + max(work, timedelta(minutes=20))
        if status == Status.CLOSED:
            closed_at = ticket.resolved_at + timedelta(days=self.rng.uniform(1, 5))
            if closed_at < self.now:
                ticket.closed_at = closed_at
            else:
                ticket.status = Status.RESOLVED

    def _fill(self, template, customer):
        return template.format(
            date=(self.now - timedelta(days=self.rng.randint(1, 20))).strftime("%d %B"),
            browser=self.rng.choice(content.BROWSERS),
            device=self.rng.choice(content.DEVICES),
            dept=self.rng.choice(content.DEPARTMENTS),
            email_provider=self.rng.choice(content.EMAIL_PROVIDERS),
            error_code=self.rng.choice(content.ERROR_CODES),
            company=customer.company or "our company",
            colleague=self.fake.name(),
            invoice=f"INV-{self.rng.randint(10000, 99999)}",
            amount=f"${self.rng.choice([49, 99, 149, 299, 499])}.00",
            seats_before=self.rng.randint(12, 40),
            seats_after=self.rng.randint(5, 30),
            request_id=self.fake.uuid4()[:8],
        )

    # --- Conversations -------------------------------------------------------

    def _create_comments(self, tickets):
        comments = []
        for ticket in tickets:
            messages = self._conversation(ticket)
            end = ticket.closed_at or ticket.resolved_at or self.now
            if ticket.status == Status.CLOSED and ticket.resolved_at:
                end = ticket.resolved_at + timedelta(hours=6)
            # First reply ~10 minutes in, or sooner for tickets raised moments ago.
            start = ticket.created_at + min(
                timedelta(minutes=10), (self.now - ticket.created_at) / 2
            )
            span = max((min(end, self.now) - start).total_seconds(), 1)
            offsets = sorted(self.rng.uniform(0, span) for _ in messages)
            for (author, body, internal), offset in zip(messages, offsets, strict=True):
                comments.append(
                    Comment(
                        ticket=ticket,
                        author=author,
                        body=body,
                        is_internal=internal,
                        created_at=start + timedelta(seconds=offset),
                    )
                )
        return Comment.objects.bulk_create(comments, batch_size=2000)

    def _conversation(self, ticket):
        """Messages as (author, body, is_internal); author None means the customer."""
        pick = self.rng.choice
        first_name = ticket.customer.name.split()[0]
        if ticket.assignee is None:
            if self.now - ticket.created_at > timedelta(days=1):
                return [(None, "Any update on this?", False)]
            return []

        agent = ticket.assignee.user
        messages = [(agent, pick(content.AGENT_FIRST_REPLIES).format(first=first_name), False)]
        if self.rng.random() < 0.25:
            messages.append((agent, pick(content.INTERNAL_NOTES), True))
        if ticket.status == Status.PENDING:
            messages.append((agent, pick(content.AGENT_QUESTIONS), False))
            return messages
        if self.rng.random() < 0.6:
            messages.append((agent, pick(content.AGENT_QUESTIONS), False))
            messages.append((None, pick(content.CUSTOMER_REPLIES), False))
        if self.rng.random() < 0.5:
            messages.append((agent, pick(content.AGENT_PROGRESS), False))
        if ticket.resolved_at:
            messages.append((agent, pick(content.AGENT_RESOLUTIONS), False))
            if self.rng.random() < 0.6:
                messages.append((None, pick(content.CUSTOMER_THANKS), False))
        return messages

    # --- Attachments ---------------------------------------------------------

    def _attach_files(self, comments, count):
        if count <= 0:
            return 0
        screenshots = [c for c in comments if c.body == "Thanks, screenshot attached."]
        others = [c for c in comments if c.author_id and not c.is_internal]
        chosen = self.rng.sample(screenshots, k=min(count, len(screenshots)))
        if len(chosen) < count:
            chosen += self.rng.sample(others, k=min(count - len(chosen), len(others)))

        for comment in chosen:
            if comment.author_id is None:
                filename, data = "screenshot.png", _png(self.rng)
            elif self.rng.random() < 0.5:
                filename, data = "server-log.txt", _log(self.rng, comment.created_at)
            else:
                filename, data = "export-sample.csv", _csv(self.rng)
            key = default_storage.save(attachment_upload_to(comment, filename), ContentFile(data))
            comment.attachment = key
            comment.attachment_name = filename
        Comment.objects.bulk_update(chosen, ["attachment", "attachment_name"])
        return len(chosen)


def _weighted(rng, weights):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _domain_for(company):
    slug = "".join(ch for ch in company.lower() if ch.isalnum())[:20] or "example"
    return f"{slug}.example"


def _png(rng, width=320, height=200):
    """A small solid-colour PNG, built by hand so seeding doesn't need Pillow."""
    colour = bytes(rng.randrange(40, 230) for _ in range(3))
    raw = b"".join(b"\x00" + colour * width for _ in range(height))

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _log(rng, when):
    lines = []
    for i in range(rng.randint(5, 15)):
        stamp = (when - timedelta(seconds=30 * i)).strftime("%Y-%m-%d %H:%M:%S")
        level = rng.choice(["INFO", "INFO", "WARN", "ERROR"])
        lines.append(
            f"{stamp} {level} request_id={rng.getrandbits(32):08x} took {rng.randint(40, 9000)}ms"
        )
    return "\n".join(reversed(lines)).encode()


def _csv(rng):
    rows = ["order_id,status,total"]
    rows += [
        f"{rng.randint(100000, 999999)},{rng.choice(['paid', 'refunded', 'pending'])},{rng.randint(10, 900)}.00"
        for _ in range(10)
    ]
    return "\n".join(rows).encode()
