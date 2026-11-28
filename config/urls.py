from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.campaigns.views import CampaignCallbackView, ScheduledDispatchView
from apps.core.npl_proxy import NplAdminPageView, NplProxyView
from apps.followups.views import FollowUpCallbackView, FollowUpDispatchView
from apps.whatsapp.views import WahaWebhookView

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("akun/", include("allauth.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("member/whatsapp/", include("apps.whatsapp.urls")),
    path("member/kampanye/", include("apps.campaigns.urls")),
    path("member/balas-otomatis/", include("apps.autoreply.urls")),
    path("member/follow-up/", include("apps.followups.urls")),
    path("member/", include("apps.members.urls")),
    # Dipanggil server lain (bukan browser): dilindungi token header, tanpa CSRF.
    path("api/webhooks/waha/", WahaWebhookView.as_view(), name="waha_webhook"),
    path("api/n8n/kampanye/hasil/", CampaignCallbackView.as_view(), name="campaign_callback"),
    path("api/n8n/kampanye/jadwal/", ScheduledDispatchView.as_view(), name="campaign_dispatch"),
    path("api/n8n/follow-up/jalankan/", FollowUpDispatchView.as_view(), name="followup_dispatch"),
    path("api/n8n/follow-up/hasil/", FollowUpCallbackView.as_view(), name="followup_callback"),
    path("portofolio/", include("apps.portfolio.urls")),
    # Admin Ngaji Privat Lombok lama (halaman & API di n8n), path sama seperti Worker lama.
    path("admin", NplAdminPageView.as_view()),
    path("admin/", NplAdminPageView.as_view(), name="npl_admin"),
    path("npl-admin/", NplAdminPageView.as_view()),
    path("admin/api", NplProxyView.as_view()),
    path("admin/api/", NplProxyView.as_view(), name="npl_admin_api"),
    path("webhook/npl-admin-api", NplProxyView.as_view()),
    path("webhook/npl-admin-api/", NplProxyView.as_view()),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
