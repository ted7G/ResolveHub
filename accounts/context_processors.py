from django.conf import settings
from django.contrib import admin


def sign_in_options(request):
    return {
        "github_login_enabled": settings.GITHUB_LOGIN_ENABLED,
        # The admin sets these on its own pages; the sign-in pages from
        # django-allauth reuse the admin layout and need them too.
        "site_header": admin.site.site_header,
        "site_title": admin.site.site_title,
    }
