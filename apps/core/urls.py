from django.urls import path

from .views import HealthView, HomeView

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("healthz/", HealthView.as_view(), name="health"),
]
