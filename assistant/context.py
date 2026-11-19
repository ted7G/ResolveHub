"""
Turns an admin form into a plain-text reference for the language model.

The reference is built from the same ModelAdmin and form the user is looking
at, for their role and (when editing) for the specific object, so it lists
exactly the fields, options and rules they can act on. Field values are
never included: the model learns what the form expects, not what any
customer wrote.
"""

from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.utils.html import strip_tags
from django.utils.text import capfirst

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

    guidance = getattr(model, "form_guidance", None)
    if guidance:
        lines.append("\nRules:")
        lines.extend(f"- {rule}" for rule in guidance())

    return "\n".join(lines), labels


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
    parts = [f"- {field.label or name} [{name}]: {_kind(field)}"]
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
    text = f"- {capfirst(field.verbose_name)} [{name}]"
    details = []
    if field.choices and len(field.choices) <= MAX_LISTED_CHOICES:
        details.append("options: " + ", ".join(str(label) for _, label in field.choices))
    if field.help_text:
        details.append(str(field.help_text))
    return text + (": " + ". ".join(details) if details else "")
