import json

from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.campaigns import services as campaign_services
from apps.core import n8n
from apps.members.mixins import MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin

from . import selectors, services
from .forms import EnrollContactsForm, FollowUpSequenceForm, FollowUpStepForm
from .models import FollowUpEnrollment

ENROLLMENTS_SHOWN = 50


class SequenceListView(MemberAreaMixin, ListView):
    section = "followups"
    template_name = "pages/members/followups/list.html"
    context_object_name = "sequences"

    def get_queryset(self):
        return selectors.sequences_with_stats(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["remaining_quota"] = campaign_services.remaining_quota(self.request.user)
        return context


class SequenceCreateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, CreateView
):
    section = "followups"
    owned_selector = selectors.sequences_for
    form_class = FollowUpSequenceForm
    template_name = "pages/members/followups/sequence_form.html"
    success_message = "Urutan “%(name)s” dibuat. Sekarang tambahkan langkah follow-up."


class SequenceUpdateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, UpdateView
):
    section = "followups"
    owned_selector = selectors.sequences_for
    form_class = FollowUpSequenceForm
    template_name = "pages/members/followups/sequence_form.html"
    success_message = "Urutan “%(name)s” diperbarui."


class SequenceDetailView(MemberAreaMixin, OwnedQuerysetMixin, DetailView):
    section = "followups"
    owned_selector = selectors.sequences_for
    template_name = "pages/members/followups/detail.html"
    context_object_name = "sequence"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sequence = self.object
        enrollments = sequence.enrollments.select_related("next_step")
        context["steps"] = sequence.steps.all()
        context["enrollments"] = enrollments[:ENROLLMENTS_SHOWN]
        context["enrollment_total"] = enrollments.count()
        context["active_total"] = enrollments.filter(
            status=FollowUpEnrollment.Status.ACTIVE
        ).count()
        context["enroll_form"] = EnrollContactsForm(owner=self.request.user)
        context["max_steps"] = settings.FOLLOWUP_MAX_STEPS
        return context


class SequenceDeleteView(MemberAreaMixin, OwnedQuerysetMixin, DeleteView):
    section = "followups"
    owned_selector = selectors.sequences_for
    template_name = "pages/members/confirm_delete.html"
    success_url = reverse_lazy("followups:sequence_list")
    extra_context = {
        "object_type": "urutan follow-up",
        "delete_note": "Semua follow-up yang belum terkirim dari urutan ini ikut dibatalkan.",
        "cancel_url": reverse_lazy("followups:sequence_list"),
    }

    def form_valid(self, form):
        messages.success(self.request, f"Urutan “{self.object}” dihapus.")
        return super().form_valid(form)


class SequenceChildMixin(MemberAreaMixin):
    """View langkah: urutan induk wajib milik member (urutan member lain → 404)."""

    section = "followups"

    def get_sequence(self):
        if not hasattr(self, "_sequence"):
            self._sequence = get_object_or_404(
                selectors.sequences_for(self.request.user), pk=self.kwargs["sequence_pk"]
            )
        return self._sequence


class StepFormMixin:
    form_class = FollowUpStepForm
    template_name = "pages/members/followups/step_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sequence"] = self.get_sequence()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sequence"] = self.get_sequence()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        services.reschedule_sequence(self.get_sequence())
        messages.success(self.request, f"Langkah “{self.object.delay_label}” disimpan.")
        return response

    def get_success_url(self):
        return self.get_sequence().get_absolute_url()


class StepCreateView(SequenceChildMixin, StepFormMixin, CreateView):
    pass


class StepUpdateView(MemberAreaMixin, OwnedQuerysetMixin, StepFormMixin, UpdateView):
    section = "followups"
    owned_selector = selectors.steps_for

    def get_sequence(self):
        # UpdateView mengisi self.object (milik member) sebelum form dibuat.
        return self.object.sequence


class StepDeleteView(MemberAreaMixin, OwnedQuerysetMixin, DeleteView):
    section = "followups"
    owned_selector = selectors.steps_for
    template_name = "pages/members/confirm_delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object_type"] = "langkah"
        context["cancel_url"] = self.object.sequence.get_absolute_url()
        return context

    def get_success_url(self):
        return self.object.sequence.get_absolute_url()

    def form_valid(self, form):
        sequence = self.object.sequence
        label = self.object.delay_label
        response = super().form_valid(form)
        services.reschedule_sequence(sequence)
        messages.success(self.request, f"Langkah “{label}” dihapus.")
        return response


class EnrollContactsView(MemberAreaMixin, OwnedQuerysetMixin, View):
    """POST: daftarkan kontak/grup ke urutan secara manual."""

    owned_selector = selectors.sequences_for

    def post(self, request, pk):
        sequence = get_object_or_404(self.get_queryset(), pk=pk)
        form = EnrollContactsForm(request.POST, owner=request.user)
        if not form.is_valid():
            for error in form.non_field_errors() or ["Pilihan tidak valid."]:
                messages.error(request, error)
            return redirect(sequence)
        try:
            added, skipped = services.enroll_contacts(sequence, form.contacts())
        except services.FollowUpError as exc:
            messages.error(request, str(exc))
        else:
            note = f" {skipped} dilewati (sudah pernah ikut atau STOP)." if skipped else ""
            messages.success(request, f"{added} kontak didaftarkan.{note}")
        return redirect(sequence)


class EnrollmentActionView(MemberAreaMixin, OwnedQuerysetMixin, View):
    owned_selector = selectors.enrollments_for

    def post(self, request, pk):
        enrollment = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            self.act(enrollment)
        except services.FollowUpError as exc:
            messages.error(request, str(exc))
        return redirect(reverse("followups:sequence_detail", args=[enrollment.sequence_id]))


class EnrollmentStopView(EnrollmentActionView):
    def act(self, enrollment):
        services.stop_enrollment(enrollment, FollowUpEnrollment.StopReason.MANUAL)
        messages.success(self.request, f"Follow-up untuk {enrollment} dihentikan.")


class EnrollmentRestartView(EnrollmentActionView):
    def act(self, enrollment):
        services.restart_enrollment(enrollment)
        messages.success(self.request, f"Follow-up untuk {enrollment} dimulai ulang.")


# --- Dipanggil n8n (bukan browser) ---------------------------------------------------


@method_decorator(csrf_exempt, name="dispatch")
class FollowUpDispatchView(View):
    """Dipanggil workflow pemicu n8n berkala: kirim follow-up yang jatuh tempo."""

    def post(self, request):
        if not n8n.valid_callback_token(request):
            return HttpResponseForbidden("invalid token")
        return JsonResponse({"ok": True, **services.dispatch_due()})


@method_decorator(csrf_exempt, name="dispatch")
class FollowUpCallbackView(View):
    """Hasil per pesan dari workflow "Blast WA Member"."""

    def post(self, request):
        if not n8n.valid_callback_token(request):
            return HttpResponseForbidden("invalid token")
        try:
            payload = json.loads(request.body)
            if not isinstance(payload, dict):
                raise ValueError
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        try:
            result = services.record_result(payload)
        except services.FollowUpError as exc:
            return JsonResponse({"ok": False, "error": str(exc), "continue": False}, status=404)
        return JsonResponse({"ok": True, **result})
