from django.urls import path

from .views import MemberHomeView, PendingApprovalView

app_name = "members"

urlpatterns = [
    path("", MemberHomeView.as_view(), name="home"),
    path("menunggu-persetujuan/", PendingApprovalView.as_view(), name="pending"),
]
