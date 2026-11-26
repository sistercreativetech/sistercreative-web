from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.campaigns.views import CampaignCallbackView
from apps.whatsapp.views import WahaWebhookView

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("akun/", include("allauth.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("member/whatsapp/", include("apps.whatsapp.urls")),
    path("member/kampanye/", include("apps.campaigns.urls")),
    path("member/", include("apps.members.urls")),
    # Dipanggil server lain (bukan browser): dilindungi token header, tanpa CSRF.
    path("api/webhooks/waha/", WahaWebhookView.as_view(), name="waha_webhook"),
    path("api/n8n/kampanye/hasil/", CampaignCallbackView.as_view(), name="campaign_callback"),
    path("portofolio/", include("apps.portfolio.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
