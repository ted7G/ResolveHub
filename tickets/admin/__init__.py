from django.contrib import admin

from .people import AgentAdmin, CustomerAdmin, TagAdmin
from .ticket import TicketAdmin

admin.site.site_header = "ResolveHub"
admin.site.site_title = "ResolveHub"
admin.site.index_title = "Support desk"
# Navigation lives in the header (templates/admin/base_site.html), which
# leaves the full page width for the ticket list.
admin.site.enable_nav_sidebar = False
# "View site" would only lead back here: the admin is the whole site.
admin.site.site_url = None

__all__ = ["AgentAdmin", "CustomerAdmin", "TagAdmin", "TicketAdmin"]
