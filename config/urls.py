from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="admin:index", permanent=False)),
    path("healthz", views.healthz, name="healthz"),
    # Must come before the admin's catch-all patterns.
    path("admin/assistant/", include("assistant.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG and settings.STORAGE_BACKEND == "local":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
