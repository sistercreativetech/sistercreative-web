import json

from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from apps.accounts.mixins import StaffRequiredMixin
from apps.contacts.services import ImportFileError
from apps.core import n8n
from apps.dashboard.views import DashboardMixin

from . import selectors, services
from .forms import EmailCampaignForm, SubscriberForm, SubscriberImportForm, TestEmailForm
from .models import EmailCampaign, MailingList, Subscriber
from .rendering import VARIABLES, absolute, render_email

SAMPLE_NAME = "Rina Wulandari"


class MailingMixin(DashboardMixin):
    section = "mailing"


# --- Kampanye email -----------------------------------------------------------------


class EmailCampaignListView(MailingMixin, ListView):
    template_name = "pages/dashboard/mailing/campaign_list.html"
    context_object_name = "campaigns"
    paginate_by = 20

    def get_queryset(self):
        return selectors.campaigns_with_counts()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["remaining_today"] = services.remaining_today()
        context["daily_limit"] = settings.EMAIL_BLAST_DAILY_LIMIT
        context["subscribed_total"] = Subscriber.objects.filter(
            status=Subscriber.Status.SUBSCRIBED
        ).count()
        return context


class CampaignFormMixin(MailingMixin, SuccessMessageMixin):
    form_class = EmailCampaignForm
    template_name = "pages/dashboard/mailing/campaign_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["variables"] = VARIABLES
        return context


class EmailCampaignCreateView(CampaignFormMixin, CreateView):
    success_message = "Kampanye “%(name)s” disimpan sebagai draf. Periksa pratinjaunya."

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class EmailCampaignUpdateView(CampaignFormMixin, UpdateView):
    success_message = "Kampanye “%(name)s” diperbarui."

    def get_queryset(self):
        return EmailCampaign.objects.filter(status=EmailCampaign.Status.DRAFT)


class EmailCampaignDetailView(MailingMixin, DetailView):
    model = EmailCampaign
    template_name = "pages/dashboard/mailing/campaign_detail.html"
    context_object_name = "campaign"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.object
        context["counts"] = services.status_counts(campaign)
        context["recipients"] = campaign.recipients.order_by("-sent_at", "pk")[:100]
        context["remaining_today"] = services.remaining_today()
        context["daily_limit"] = settings.EMAIL_BLAST_DAILY_LIMIT
        context["test_form"] = TestEmailForm(initial={"email": self.request.user.email})
        if campaign.is_draft:
            context["target_count"] = selectors.target_subscribers(campaign).count()
        return context


@method_decorator(xframe_options_sameorigin, name="dispatch")
class EmailCampaignPreviewView(StaffRequiredMixin, View):
    """HTML email dengan nama contoh; ditampilkan dalam iframe sandbox di halaman detail."""

    def get(self, request, pk):
        campaign = get_object_or_404(EmailCampaign, pk=pk)
        rendered = render_email(campaign, name=SAMPLE_NAME, unsubscribe_url=absolute("/"))
        response = HttpResponse(rendered.html)
        response["Content-Security-Policy"] = (
            "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'"
        )
        return response


class CampaignActionView(StaffRequiredMixin, View):
    def get_campaign(self, pk):
        return get_object_or_404(EmailCampaign, pk=pk)


class EmailCampaignStartView(CampaignActionView):
    def post(self, request, pk):
        campaign = self.get_campaign(pk)
        try:
            total = services.start_campaign(campaign)
        except services.MailingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Pengiriman ke {total} pelanggan dimulai. Email dikirim bertahap "
                f"(maksimal {settings.EMAIL_BLAST_DAILY_LIMIT} per hari).",
            )
        return redirect(campaign)


class EmailCampaignCancelView(CampaignActionView):
    def post(self, request, pk):
        campaign = self.get_campaign(pk)
        try:
            services.cancel_campaign(campaign)
            messages.success(request, "Kampanye dihentikan. Email yang belum terkirim dibatalkan.")
        except services.MailingError as exc:
            messages.error(request, str(exc))
        return redirect(campaign)


class EmailCampaignTestView(CampaignActionView):
    def post(self, request, pk):
        campaign = self.get_campaign(pk)
        form = TestEmailForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Alamat email uji tidak valid.")
            return redirect(campaign)
        try:
            services.send_test(campaign, to=form.cleaned_data["email"], name=request.user.full_name)
        except services.MailingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request, f"Email uji dikirim ke {form.cleaned_data['email']}. Cek kotak masuk."
            )
        return redirect(campaign)


class EmailCampaignDeleteView(MailingMixin, DeleteView):
    model = EmailCampaign
    template_name = "pages/dashboard/confirm_delete.html"
    success_url = reverse_lazy("mailing:campaign_list")
    extra_context = {
        "object_type": "kampanye email",
        "cancel_url": reverse_lazy("mailing:campaign_list"),
    }

    def form_valid(self, form):
        name = self.object.name
        try:
            services.delete_campaign(self.object)
        except services.MailingError as exc:
            messages.error(self.request, str(exc))
            return redirect(self.object)
        messages.success(self.request, f"Kampanye “{name}” dihapus.")
        return redirect(self.success_url)


# --- Pelanggan ----------------------------------------------------------------------


class SubscriberListView(MailingMixin, ListView):
    template_name = "pages/dashboard/mailing/subscriber_list.html"
    context_object_name = "subscribers"
    paginate_by = 50

    def get_filters(self):
        params = self.request.GET
        list_id = params.get("daftar", "")
        mailing_list = MailingList.objects.filter(pk=list_id).first() if list_id.isdigit() else None
        return {
            "query": params.get("q", "").strip()[:100],
            "status": params.get("status", ""),
            "mailing_list": mailing_list,
        }

    def get_queryset(self):
        return selectors.subscribers(**self.get_filters())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = self.get_filters()
        params = self.request.GET.copy()
        params.pop("page", None)
        context.update(
            {
                "filters": filters,
                "filter_querystring": params.urlencode(),
                "is_filtered": any(filters.values()),
                "lists": selectors.lists_with_counts(),
                "status_choices": Subscriber.Status.choices,
            }
        )
        return context


class SubscriberCreateView(MailingMixin, SuccessMessageMixin, CreateView):
    form_class = SubscriberForm
    template_name = "pages/dashboard/mailing/subscriber_form.html"
    success_url = reverse_lazy("mailing:subscriber_list")
    success_message = "%(email)s ditambahkan."


class SubscriberImportView(MailingMixin, FormView):
    form_class = SubscriberImportForm
    template_name = "pages/dashboard/mailing/subscriber_import.html"

    def form_valid(self, form):
        try:
            result = services.import_subscribers(
                form.cleaned_data["file"].read(), mailing_list=form.target_list()
            )
        except ImportFileError as exc:
            form.add_error("file", str(exc))
            return self.form_invalid(form)
        summary = f"Impor selesai: {result.created} pelanggan baru, {result.existing} sudah ada."
        if result.duplicates_in_file:
            summary += f" {result.duplicates_in_file} baris ganda dilewati."
        messages.success(self.request, summary)
        if result.invalid_count:
            rows = ", ".join(f"baris {line}" for line, _ in result.invalid_rows)
            messages.warning(
                self.request, f"{result.invalid_count} email tidak valid dilewati ({rows})."
            )
        url = reverse("mailing:subscriber_list")
        if result.mailing_list:
            url += f"?daftar={result.mailing_list.pk}"
        return redirect(url)


class SubscriberSampleView(StaffRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(services.sample_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="contoh-pelanggan-email.csv"'
        return response


class SubscriberUnsubscribeView(StaffRequiredMixin, View):
    def post(self, request, pk):
        subscriber = get_object_or_404(Subscriber, pk=pk)
        services.unsubscribe(subscriber)
        messages.success(request, f"{subscriber.email} tidak akan dikirimi email lagi.")
        return redirect("mailing:subscriber_list")


class SubscriberDeleteView(MailingMixin, DeleteView):
    model = Subscriber
    template_name = "pages/dashboard/confirm_delete.html"
    success_url = reverse_lazy("mailing:subscriber_list")
    extra_context = {
        "object_type": "pelanggan",
        "cancel_url": reverse_lazy("mailing:subscriber_list"),
    }

    def form_valid(self, form):
        email = self.object.email
        response = super().form_valid(form)
        messages.success(self.request, f"{email} dihapus.")
        return response


# --- Halaman publik: berhenti berlangganan ------------------------------------------


class UnsubscribeView(View):
    template_name = "pages/mailing/unsubscribe.html"

    def get(self, request, token):
        subscriber = get_object_or_404(Subscriber, token=token)
        return render(request, self.template_name, {"subscriber": subscriber, "done": False})

    def post(self, request, token):
        subscriber = get_object_or_404(Subscriber, token=token)
        services.unsubscribe(subscriber)
        return render(request, self.template_name, {"subscriber": subscriber, "done": True})


# --- Dipanggil n8n ------------------------------------------------------------------


@method_decorator(csrf_exempt, name="dispatch")
class EmailDispatchView(View):
    """Dipanggil workflow pemicu n8n berkala: kirim batch email berikutnya."""

    def post(self, request):
        if not n8n.valid_callback_token(request):
            return HttpResponseForbidden("invalid token")
        return JsonResponse({"ok": True, **services.dispatch_due()})


@method_decorator(csrf_exempt, name="dispatch")
class EmailCallbackView(View):
    """Hasil per email dari workflow n8n "Blast Email"."""

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
        except services.MailingError as exc:
            return JsonResponse({"ok": False, "error": str(exc), "continue": False}, status=404)
        return JsonResponse({"ok": True, **result})
