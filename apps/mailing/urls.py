from django.urls import path

from . import views

app_name = "mailing"

urlpatterns = [
    path("", views.EmailCampaignListView.as_view(), name="campaign_list"),
    path("baru/", views.EmailCampaignCreateView.as_view(), name="campaign_create"),
    path("<int:pk>/", views.EmailCampaignDetailView.as_view(), name="campaign_detail"),
    path("<int:pk>/ubah/", views.EmailCampaignUpdateView.as_view(), name="campaign_update"),
    path("<int:pk>/hapus/", views.EmailCampaignDeleteView.as_view(), name="campaign_delete"),
    path("<int:pk>/pratinjau/", views.EmailCampaignPreviewView.as_view(), name="campaign_preview"),
    path("<int:pk>/mulai/", views.EmailCampaignStartView.as_view(), name="campaign_start"),
    path("<int:pk>/hentikan/", views.EmailCampaignCancelView.as_view(), name="campaign_cancel"),
    path("<int:pk>/uji/", views.EmailCampaignTestView.as_view(), name="campaign_test"),
    path("pelanggan/", views.SubscriberListView.as_view(), name="subscriber_list"),
    path("pelanggan/baru/", views.SubscriberCreateView.as_view(), name="subscriber_create"),
    path("pelanggan/impor/", views.SubscriberImportView.as_view(), name="subscriber_import"),
    path("pelanggan/contoh.csv", views.SubscriberSampleView.as_view(), name="subscriber_sample"),
    path(
        "pelanggan/<int:pk>/berhenti/",
        views.SubscriberUnsubscribeView.as_view(),
        name="subscriber_unsubscribe",
    ),
    path(
        "pelanggan/<int:pk>/hapus/", views.SubscriberDeleteView.as_view(), name="subscriber_delete"
    ),
]
