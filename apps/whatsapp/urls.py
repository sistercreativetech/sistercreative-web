from django.urls import path

from . import views

app_name = "whatsapp"

urlpatterns = [
    path("", views.SessionView.as_view(), name="session"),
    path("status.json", views.SessionStatusView.as_view(), name="session_status"),
    path("qr.png", views.SessionQrView.as_view(), name="session_qr"),
    path("hubungkan/", views.SessionConnectView.as_view(), name="session_connect"),
    path("putuskan/", views.SessionDisconnectView.as_view(), name="session_disconnect"),
    path("grup/", views.GroupListView.as_view(), name="group_list"),
]
