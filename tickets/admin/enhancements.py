from django import forms
from django.conf import settings
from django.contrib.admin.options import IS_POPUP_VAR
from django.utils.text import capfirst


class AdminEnhancementsMixin:
    """
    Loads the theme's scripts on a model admin's pages:

    - static/resolvehub/searchable.js: long dropdowns become searchable and
      long filter lists get a search box;
    - static/resolvehub/filterbar.js: list filters move from the sidebar into
      a row of dropdown buttons above the table, giving the table full width;
    - static/resolvehub/listpage.js: search as you type, and a bulk-action
      button that is only active once there is something to apply.

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
                "resolvehub/listpage.js",
            ],
            css={
                "screen": [
                    f"admin/css/vendor/select2/select2{extra}.css",
                    "admin/css/autocomplete.css",
                ]
            },
        )
        return super().media + enhancements

    def get_action_choices(self, request, default_choices=None):
        # A readable prompt instead of Django's "---------".
        return super().get_action_choices(request, [("", "Choose an action…")])

    def changelist_view(self, request, extra_context=None):
        # "Tickets" reads better than Django's "Select ticket to change". Popup
        # lookups keep Django's "Select ticket" wording.
        if IS_POPUP_VAR not in request.GET:
            extra_context = {
                "title": capfirst(self.model._meta.verbose_name_plural),
                **(extra_context or {}),
            }
        return super().changelist_view(request, extra_context)
