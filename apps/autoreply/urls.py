from django.urls import path

from . import views

app_name = "autoreply"

urlpatterns = [
    path("", views.RuleListView.as_view(), name="rule_list"),
    path("baru/", views.RuleCreateView.as_view(), name="rule_create"),
    path("<int:pk>/ubah/", views.RuleUpdateView.as_view(), name="rule_update"),
    path("<int:pk>/hapus/", views.RuleDeleteView.as_view(), name="rule_delete"),
    path("riwayat/", views.LogListView.as_view(), name="log_list"),
]
