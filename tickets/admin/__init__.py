from django.contrib import admin

from .people import AgentAdmin, CustomerAdmin, TagAdmin
from .ticket import TicketAdmin

admin.site.site_header = "ResolveHub"
admin.site.site_title = "ResolveHub"
admin.site.index_title = "Support desk"

__all__ = ["AgentAdmin", "CustomerAdmin", "TagAdmin", "TicketAdmin"]
