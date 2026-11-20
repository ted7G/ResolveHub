from django import forms
from django.conf import settings


class SearchableSelectsMixin:
    """
    Loads static/resolvehub/searchable.js on a model admin's pages: long
    dropdowns become searchable and long filter lists get a search box.

    The file names match the ones Django's own autocomplete widget uses, so
    on pages that already have it the assets are merged, not loaded twice.
    """

    @property
    def media(self):
        extra = "" if settings.DEBUG else ".min"
        searchable = forms.Media(
            js=[
                f"admin/js/vendor/jquery/jquery{extra}.js",
                f"admin/js/vendor/select2/select2.full{extra}.js",
                "admin/js/jquery.init.js",
                "resolvehub/searchable.js",
            ],
            css={
                "screen": [
                    f"admin/css/vendor/select2/select2{extra}.css",
                    "admin/css/autocomplete.css",
                ]
            },
        )
        return super().media + searchable
