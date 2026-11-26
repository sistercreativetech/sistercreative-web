from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    path("", views.CampaignListView.as_view(), name="list"),
    path("baru/", views.CampaignCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CampaignDetailView.as_view(), name="detail"),
    path("<int:pk>/progres.json", views.CampaignProgressView.as_view(), name="progress"),
    path("<int:pk>/mulai/", views.CampaignStartView.as_view(), name="start"),
    path("<int:pk>/hentikan/", views.CampaignCancelView.as_view(), name="cancel"),
]
