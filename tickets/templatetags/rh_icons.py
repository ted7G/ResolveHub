"""
The theme's line icons: `{% icon "ticket" %}` renders an inline SVG drawn
with currentColor, so an icon takes the colour of the text it sits in.
One 24px grid, 1.8px rounded strokes, decorative (hidden from screen
readers; the text next to an icon carries the meaning).
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

ICONS = {
    # Sections
    "dashboard": '<rect x="3" y="3" width="7.5" height="9" rx="1.8"/><rect x="13.5" y="3" width="7.5" height="5" rx="1.8"/><rect x="13.5" y="11" width="7.5" height="10" rx="1.8"/><rect x="3" y="15" width="7.5" height="6" rx="1.8"/>',
    "ticket": '<path d="M4 6h16a1 1 0 0 1 1 1v3a2 2 0 0 0 0 4v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a2 2 0 0 0 0-4V7a1 1 0 0 1 1-1z"/><path d="M14.5 6v2.5m0 3v1m0 3V18"/>',
    "customer": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.7c2 .7 3.2 2.6 3.5 5.3"/>',
    "agent": '<path d="M4 13.5V12a8 8 0 0 1 16 0v1.5"/><rect x="2.5" y="13" width="4" height="6" rx="1.6"/><rect x="17.5" y="13" width="4" height="6" rx="1.6"/><path d="M19.5 19c0 1.6-1.6 2.5-4 2.5H13"/>',
    "tag": '<path d="M3 12.6V4a1 1 0 0 1 1-1h8.6a1 1 0 0 1 .7.3l7.4 7.4a1 1 0 0 1 0 1.4l-8.6 8.6a1 1 0 0 1-1.4 0l-7.4-7.4a1 1 0 0 1-.3-.7z"/><circle cx="7.6" cy="7.6" r="1.4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4.2 4-6.5 8-6.5s7.2 2.3 8 6.5"/>',
    "group": '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    # Account menu
    "key": '<circle cx="8" cy="15.5" r="4"/><path d="m10.9 12.6 8.6-8.6M15.5 8l2.5 2.5M13.5 10l2 2"/>',
    "logout": '<path d="M9.5 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3.5"/><path d="m15.5 16.5 4.5-4.5-4.5-4.5M20 12H9"/>',
    # Desk numbers and charts
    "inbox": '<path d="M3 13.5h5l1.5 2.5h5l1.5-2.5h5"/><path d="M5.6 5h12.8a1 1 0 0 1 .95.7L21 13.5V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4.5l1.65-7.8a1 1 0 0 1 .95-.7z"/>',
    "alarm": '<circle cx="12" cy="13" r="7.5"/><path d="M12 9.5V13l2.5 2M4.5 3.5 2 6M19.5 3.5 22 6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    "user-x": '<circle cx="10" cy="8" r="4"/><path d="M3 21c.7-4 3.4-6.5 7-6.5 1.3 0 2.5.3 3.5.9"/><path d="m16.5 15.5 4.5 4.5m0-4.5-4.5 4.5"/>',
    "user-check": '<circle cx="10" cy="8" r="4"/><path d="M3 21c.7-4 3.4-6.5 7-6.5 1.3 0 2.5.3 3.5.9"/><path d="m15.5 18 2.2 2.2 4.3-4.4"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "bars": '<path d="M5 20V11M11 20V5M17 20v-6M3 20h18"/>',
    "activity": '<path d="M3 12h4l2.5-7 5 14 2.5-7h4"/>',
    # Ticket page
    "flag": '<path d="M5 21V4"/><path d="M5 4h12.5l-2.5 4.5 2.5 4.5H5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "history": '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5"/><path d="M3.5 3.5v5h5M12 7.5V12l3 2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
}

# The GitHub mark is a filled shape rather than a line drawing.
GITHUB = (
    '<svg class="rh-icon{}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17'
    ".55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68"
    "-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64"
    "-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27"
    " 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15"
    " 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013"
    ' 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
)

# Admin model names (as in the app list) to their icon.
MODEL_ICONS = {
    "Ticket": "ticket",
    "Customer": "customer",
    "Agent": "agent",
    "Tag": "tag",
    "User": "user",
    "Group": "group",
}


@register.simple_tag
def icon(name, extra_class=""):
    css = f" {extra_class}" if extra_class else ""
    if name == "github":
        return mark_safe(GITHUB.format(css))
    paths = ICONS.get(name)
    if paths is None:
        return ""
    return format_html(
        '<svg class="rh-icon{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        'focusable="false">{}</svg>',
        css,
        mark_safe(paths),
    )


@register.simple_tag
def model_icon(object_name, extra_class=""):
    """The icon for an admin model, by its object name ("Ticket", "User"...)."""
    return icon(MODEL_ICONS.get(object_name, "dashboard"), extra_class)
