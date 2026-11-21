"""
Turns the admin page a user has open into a plain-text reference for the
language model: a form (its fields, options and rules), a list (its columns,
search, filters and bulk actions) or the desk in general (dashboard, roles,
workflow).

Each reference is built from the same ModelAdmin the user is looking at, for
their role and (when editing) for the specific record, so it describes
exactly what they can act on. Field values and record contents are never
included: the model learns how the page works, not what any customer wrote.
"""

from django import forms
from django.contrib import admin
from django.contrib.admin.utils import label_for_field
from django.core.exceptions import FieldDoesNotExist
from django.utils.html import strip_tags
from django.utils.text import capfirst

from tickets.models import Ticket

# Lists longer than this are summarised instead of spelled out.
MAX_LISTED_CHOICES = 12


def build_form_reference(model_admin, request, obj=None):
    """Return (reference_text, field_labels) for the admin form of `obj`."""
    model = model_admin.model
    opts = model._meta
    lines = [
        f"Form: {capfirst(opts.verbose_name)} "
        f"({'editing an existing record' if obj else 'creating a new record'})"
    ]
    labels = {}

    form_class = model_admin.get_form(request, obj, change=obj is not None)
    form = form_class(instance=obj) if obj is not None else form_class()
    if form.fields:
        lines.append("\nFields:")
        for name, field in form.fields.items():
            labels[name] = str(field.label or name)
            lines.append(_describe_field(name, field, current=_current_choice(form, name, obj)))
    else:
        lines.append("\nThis user can only view this record, so every field is read-only.")

    shown = model_admin.get_fields(request, obj) if not form.fields else []
    shown += [n for n in model_admin.get_readonly_fields(request, obj) if n not in shown]
    readonly = [_describe_readonly(model, name) for name in shown if name not in form.fields]
    readonly = [line for line in readonly if line]
    if readonly:
        lines.append("\nRead-only fields (filled in automatically or not editable here):")
        lines.extend(readonly)

    for inline in model_admin.get_inline_instances(request, obj):
        if not inline.has_add_permission(request, obj):
            continue
        inline_form = inline.get_formset(request, obj).form
        title = capfirst(str(inline.verbose_name_plural))
        lines.append(f'\nSection "{title}" (adds a {inline.verbose_name}):')
        for name, field in inline_form.base_fields.items():
            if isinstance(field.widget, forms.HiddenInput) or name in ("id", "DELETE"):
                continue
            labels.setdefault(name, str(field.label or name))
            lines.append(_describe_field(name, field))

    lines.append("\nAbout this person and record:")
    lines.extend(f"- {note}" for note in _access_notes(model_admin, request, obj))

    _append_rules(lines, model)
    return "\n".join(lines), labels


def build_list_reference(model_admin, request):
    """Return the reference for a model's list page: columns, search, filters, actions."""
    opts = model_admin.model._meta
    plural = str(opts.verbose_name_plural)
    lines = [f"Page: the {plural} list, a table of {plural} with search, filters and bulk actions."]

    columns = [
        str(label_for_field(name, model_admin.model, model_admin))
        for name in model_admin.get_list_display(request)
        if name != "action_checkbox"
    ]
    lines.append("\nColumns: " + ", ".join(capfirst(c) for c in columns) + ".")

    if model_admin.get_search_fields(request):
        help_text = model_admin.search_help_text or ""
        lines.append(f"\nSearch: the box above the table searches as you type. {help_text}")

    changelist = model_admin.get_changelist_instance(request)
    if changelist.filter_specs:
        lines.append(
            "\nFilters: there is one button per filter above the table, named after the "
            "filter (there is no single 'Filters' button). Clicking a button opens its "
            "options; picking one applies it straight away and the button then shows the "
            "value. Filters combine: a value in two filters shows records matching both. "
            "Clear all filters removes them. The filters are:"
        )
        for spec in changelist.filter_specs:
            choices = [str(c["display"]) for c in spec.choices(changelist)]
            choices = [c for c in choices if c != "All"]
            listed = ", ".join(choices[:MAX_LISTED_CHOICES])
            extra = len(choices) - MAX_LISTED_CHOICES
            more = f" and {extra} more" if extra > 0 else ""
            lines.append(f"- {capfirst(str(spec.title))}: {listed}{more}.")
    if model_admin.date_hierarchy:
        field = opts.get_field(model_admin.date_hierarchy)
        lines.append(
            "\nDate drill-down: the row of months above the table narrows the list by "
            f"{field.verbose_name}."
        )

    actions = model_admin.get_actions(request)
    if actions:
        lines.append(
            "\nBulk actions (tick rows, choose the action under the search box, then "
            "press Apply; actions apply the same rules as the edit form and report "
            "anything they skip):"
        )
        lines.extend(f"- {capfirst(str(description))}" for _, _, description in actions.values())
    else:
        lines.append("\nThis person has no bulk actions on this list.")

    if model_admin.has_add_permission(request):
        lines.append(f"\nThe Add button at the top right creates a new {opts.verbose_name}.")

    lines.append("\nAbout this person:")
    lines.extend(f"- {note}" for note in _access_notes(model_admin, request, None))
    lines.extend(f"- {line}" for line in _abilities(request.user))
    _append_rules(lines, model_admin.model)
    return "\n".join(lines)


def build_general_reference(request):
    """Return the reference for questions asked outside a form or list."""
    user = request.user
    lines = ["Page: the ResolveHub admin in general (the dashboard and navigation)."]

    sections = [
        str(model["name"]) for app in admin.site.get_app_list(request) for model in app["models"]
    ]
    if sections:
        lines.append(
            "\nSections this person can open (links in the header): " + ", ".join(sections) + "."
        )

    if user.has_perm("tickets.view_ticket"):
        lines.append(
            "\nDashboard, top to bottom:\n"
            "- Active tickets: New, Open and Waiting on customer together, with how many "
            "of each.\n"
            "- Overdue: active tickets past their response deadline.\n"
            "- Due in 24 hours: active tickets whose deadline falls within the next day.\n"
            "- Unassigned: active tickets nobody owns yet.\n"
            "- Assigned to you: shown to people who work tickets.\n"
            "- Ticket flow chart: tickets created and resolved per day over the last 14 days.\n"
            "- Active by priority and Team workload charts: active tickets split into on "
            "track and overdue; each row opens the matching ticket list.\n"
            "- Recent actions: this person's own latest changes.\n"
            "Every number and chart row links to the ticket list filtered to match."
        )

    lines.append(
        "\nAround the admin: the header has the section links, Ask AI, a light/dark theme "
        "switch and a menu under the person's name (change password, GitHub sign-in, log "
        "out). List pages search as you type and have filter buttons above the table. "
        "Ticket pages show the conversation as a thread with a reply box below it."
    )

    lines.append("\nAbout this person:")
    lines.append(f"- {_role_sentence(user)}")
    lines.extend(f"- {line}" for line in _abilities(user))
    _append_rules(lines, Ticket)
    return "\n".join(lines)


def _append_rules(lines, model):
    guidance = getattr(model, "form_guidance", None)
    if guidance:
        lines.append("\nRules:")
        lines.extend(f"- {rule}" for rule in guidance())


def _role_sentence(user):
    if user.is_superuser:
        return "They are a superuser (full access)."
    groups = ", ".join(user.groups.order_by("name").values_list("name", flat=True))
    return (
        f"They are in the {groups} role." if groups else "They are a staff member without a role."
    )


def _abilities(user):
    """What the person can do with tickets, in plain words, from their permissions."""
    if not user.has_perm("tickets.view_ticket"):
        return ["They can't see tickets."]
    if not user.has_perm("tickets.change_ticket"):
        return ["They can read tickets, customers, agents and tags but not change anything."]
    lines = []
    if user.has_perm("tickets.manage_all_tickets"):
        lines.append("They can edit any ticket that isn't closed and assign tickets to anyone.")
    else:
        lines.append(
            "They can edit tickets assigned to them and unassigned ones, and assign "
            "tickets only to themselves; colleagues' tickets open read-only."
        )
    if user.has_perm("tickets.delete_ticket"):
        lines.append("They can delete tickets, customers and tags.")
    else:
        lines.append(
            "They can't delete tickets, customers or tags; support admins can. "
            "Closing a ticket is the usual way to finish with it."
        )
    if user.has_perm("tickets.view_internal_note"):
        lines.append("They can read and write internal notes.")
    if user.has_perm("auth.change_user"):
        lines.append("They can manage staff accounts and roles (Users section).")
    return lines


def _access_notes(model_admin, request, obj):
    """
    What this person may do here, so "why can't I...?" gets the real reason.
    A model admin can add its own notes with an `assistant_notes` method.
    """
    notes = [_role_sentence(request.user)]
    if obj is not None and not model_admin.has_change_permission(request, obj):
        notes.append("They can view this record but not change it.")
    extra = getattr(model_admin, "assistant_notes", None)
    if extra:
        notes.extend(extra(request, obj))
    return notes


def _current_choice(form, name, obj):
    """
    The current value of a fixed-choice field such as status or priority.
    Only these are shared: they explain why options are limited and contain
    no customer data, unlike free text or related records.
    """
    field = form.fields[name]
    if obj is None or isinstance(field, forms.ModelChoiceField):
        return None
    if not isinstance(field, forms.TypedChoiceField | forms.ChoiceField):
        return None
    value = form.initial.get(name)
    return next((str(label) for v, label in field.choices if v == value), None)


def _describe_field(name, field, current=None):
    parts = [f"- {field.label or name}: {_kind(field)}"]
    parts.append("required" if field.required else "optional")
    max_length = getattr(field, "max_length", None)
    # A FileField's max_length is the stored filename's length, not user input.
    if max_length and not isinstance(field, forms.FileField):
        parts.append(f"max {max_length} characters")
    if current:
        parts.append(f"currently {current}")
    choices = _choices(field)
    if choices:
        parts.append(choices)
    text = ", ".join(parts) + "."
    if field.help_text:
        text += f" {strip_tags(str(field.help_text)).strip()}"
    return text


def _kind(field):
    widget = field.widget
    if isinstance(field, forms.FileField):
        return "file upload"
    if isinstance(field, forms.BooleanField):
        return "checkbox"
    if isinstance(field, forms.ModelMultipleChoiceField):
        return "pick one or more existing records"
    if isinstance(field, forms.ModelChoiceField):
        return "pick an existing record"
    if isinstance(field, forms.ChoiceField):
        return "dropdown"
    if isinstance(field, forms.EmailField):
        return "email address"
    if isinstance(field, forms.DateTimeField | forms.DateField):
        return "date"
    if isinstance(widget, forms.Textarea):
        return "long text"
    return "text"


def _choices(field):
    # Related records are counted, never listed: their labels are names and
    # email addresses, which don't belong in a prompt.
    if isinstance(field, forms.ModelChoiceField):
        return f"{field.queryset.count()} records to choose from"
    if not hasattr(field, "choices"):
        return ""
    labels = [str(label) for value, label in field.choices if value not in ("", None)]
    if not labels or len(labels) > MAX_LISTED_CHOICES:
        return f"{len(labels)} options" if labels else ""
    return "options: " + ", ".join(labels)


def _describe_readonly(model, name):
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return ""
    text = f"- {capfirst(field.verbose_name)}"
    details = []
    if field.choices and len(field.choices) <= MAX_LISTED_CHOICES:
        details.append("options: " + ", ".join(str(label) for _, label in field.choices))
    if field.help_text:
        details.append(str(field.help_text))
    return text + (": " + ". ".join(details) if details else "")
