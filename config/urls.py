from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("akun/", include("allauth.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("member/", include("apps.members.urls")),
    path("portofolio/", include("apps.portfolio.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
