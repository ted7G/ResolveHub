from django.core.management.base import BaseCommand

from accounts.roles import ROLE_PERMISSIONS, sync_roles


class Command(BaseCommand):
    help = "Create or update the role groups (Support admin, Agent, Viewer) and their permissions."

    def handle(self, *args, **options):
        sync_roles()
        for name, perms in ROLE_PERMISSIONS.items():
            self.stdout.write(f"{name}: {len(perms)} permissions")
        self.stdout.write(self.style.SUCCESS("Roles are up to date."))
