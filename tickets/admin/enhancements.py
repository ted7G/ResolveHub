from django import forms
from django.conf import settings


class AdminEnhancementsMixin:
    """
    Loads the theme's scripts on a model admin's pages:

    - static/resolvehub/searchable.js: long dropdowns become searchable and
      long filter lists get a search box;
    - static/resolvehub/filterbar.js: list filters move from the sidebar into
      a row of dropdown buttons above the table, giving the table full width.

    The jQuery and Select2 file names match the ones Django's own
    autocomplete widget uses, so on pages that already have them the assets
    are merged, not loaded twice.
    """

    @property
    def media(self):
        extra = "" if settings.DEBUG else ".min"
        enhancements = forms.Media(
            js=[
                f"admin/js/vendor/jquery/jquery{extra}.js",
                f"admin/js/vendor/select2/select2.full{extra}.js",
                "admin/js/jquery.init.js",
                "resolvehub/searchable.js",
                "resolvehub/filterbar.js",
            ],
            css={
                "screen": [
                    f"admin/css/vendor/select2/select2{extra}.css",
                    "admin/css/autocomplete.css",
                ]
            },
        )
        return super().media + enhancements
