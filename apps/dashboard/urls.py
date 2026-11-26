from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("member/", views.MemberListView.as_view(), name="member_list"),
    path("member/<int:pk>/", views.MemberDetailView.as_view(), name="member_detail"),
    path("member/<int:pk>/status/", views.MemberStatusView.as_view(), name="member_status"),
    path("portofolio/", views.ProjectListView.as_view(), name="project_list"),
    path("portofolio/baru/", views.ProjectCreateView.as_view(), name="project_create"),
    path("portofolio/<int:pk>/ubah/", views.ProjectUpdateView.as_view(), name="project_update"),
    path("portofolio/<int:pk>/hapus/", views.ProjectDeleteView.as_view(), name="project_delete"),
    path("kategori/", views.CategoryListView.as_view(), name="category_list"),
    path("kategori/baru/", views.CategoryCreateView.as_view(), name="category_create"),
    path("kategori/<int:pk>/ubah/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("kategori/<int:pk>/hapus/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("kampanye/", views.CampaignListView.as_view(), name="campaign_list"),
    path("kampanye/<int:pk>/hentikan/", views.CampaignCancelView.as_view(), name="campaign_cancel"),
]
