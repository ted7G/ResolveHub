"""Helpers for driving admin change forms from tests."""

from django import forms
from django.db.models.fields.files import FieldFile


def _post_value(value):
    if isinstance(value, list | tuple):
        return [_post_value(v) for v in value]
    if hasattr(value, "pk"):
        return value.pk
    return value


def admin_form_data(response):
    """
    Build the POST payload an admin change page would submit unchanged,
    including every inline formset, from the page's GET response.
    """
    data = {}

    def add_form(form):
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            value = value() if callable(value) else value
            if value is None or isinstance(value, FieldFile):
                continue
            if isinstance(field, forms.BooleanField):
                if value:
                    data[form.add_prefix(name)] = "on"
                continue
            data[form.add_prefix(name)] = _post_value(value)

    add_form(response.context["adminform"].form)
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        for key, value in formset.management_form.initial.items():
            data[f"{formset.prefix}-{key}"] = value
        for form in formset.forms:
            add_form(form)
    return data
