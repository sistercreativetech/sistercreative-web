from django.urls import path

from apps.contacts import views as contact_views

from .views import MemberHomeView, PendingApprovalView

app_name = "members"

urlpatterns = [
    path("", MemberHomeView.as_view(), name="home"),
    path("menunggu-persetujuan/", PendingApprovalView.as_view(), name="pending"),
    # Kontak
    path("kontak/", contact_views.ContactListView.as_view(), name="contact_list"),
    path("kontak/baru/", contact_views.ContactCreateView.as_view(), name="contact_create"),
    path("kontak/impor/", contact_views.ContactImportView.as_view(), name="contact_import"),
    path("kontak/contoh.csv", contact_views.ContactSampleCsvView.as_view(), name="contact_sample"),
    path("kontak/<int:pk>/ubah/", contact_views.ContactUpdateView.as_view(), name="contact_update"),
    path(
        "kontak/<int:pk>/hapus/", contact_views.ContactDeleteView.as_view(), name="contact_delete"
    ),
    # Grup
    path("grup/", contact_views.GroupListView.as_view(), name="group_list"),
    path("grup/baru/", contact_views.GroupCreateView.as_view(), name="group_create"),
    path("grup/<int:pk>/ubah/", contact_views.GroupUpdateView.as_view(), name="group_update"),
    path("grup/<int:pk>/hapus/", contact_views.GroupDeleteView.as_view(), name="group_delete"),
    # Template pesan
    path("template/", contact_views.TemplateListView.as_view(), name="template_list"),
    path("template/baru/", contact_views.TemplateCreateView.as_view(), name="template_create"),
    path(
        "template/<int:pk>/ubah/",
        contact_views.TemplateUpdateView.as_view(),
        name="template_update",
    ),
    path(
        "template/<int:pk>/hapus/",
        contact_views.TemplateDeleteView.as_view(),
        name="template_delete",
    ),
]
