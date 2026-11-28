from django.urls import path

from . import views

app_name = "followups"

urlpatterns = [
    path("", views.SequenceListView.as_view(), name="sequence_list"),
    path("baru/", views.SequenceCreateView.as_view(), name="sequence_create"),
    path("<int:pk>/", views.SequenceDetailView.as_view(), name="sequence_detail"),
    path("<int:pk>/ubah/", views.SequenceUpdateView.as_view(), name="sequence_update"),
    path("<int:pk>/hapus/", views.SequenceDeleteView.as_view(), name="sequence_delete"),
    path("<int:pk>/daftarkan/", views.EnrollContactsView.as_view(), name="enroll_contacts"),
    path("<int:sequence_pk>/langkah/baru/", views.StepCreateView.as_view(), name="step_create"),
    path("langkah/<int:pk>/ubah/", views.StepUpdateView.as_view(), name="step_update"),
    path("langkah/<int:pk>/hapus/", views.StepDeleteView.as_view(), name="step_delete"),
    path(
        "peserta/<int:pk>/hentikan/",
        views.EnrollmentStopView.as_view(),
        name="enrollment_stop",
    ),
    path(
        "peserta/<int:pk>/ulangi/",
        views.EnrollmentRestartView.as_view(),
        name="enrollment_restart",
    ),
]
