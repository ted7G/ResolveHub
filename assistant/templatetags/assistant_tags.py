from django import template
from django.urls import reverse

register = template.Library()


@register.inclusion_tag("assistant/widget.html", takes_context=True)
def assistant_widget(context):
    """Render the help widget on admin add/change pages only."""
    opts = context.get("opts")
    if opts is None or context.get("adminform") is None:
        return {"show": False}
    original = context.get("original")
    return {
        "show": True,
        "endpoint": reverse("assistant:ask"),
        "model": opts.label_lower,
        "model_name": opts.verbose_name,
        "object_id": original.pk if original is not None else "",
    }
