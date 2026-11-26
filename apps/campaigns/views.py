import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView

from apps.members.mixins import MemberAreaMixin, OwnedQuerysetMixin
from apps.whatsapp import services as wa_services
from apps.whatsapp import waha
from apps.whatsapp.models import WhatsAppSession

from . import selectors, services
from .forms import CampaignForm

logger = logging.getLogger(__name__)


class CampaignListView(MemberAreaMixin, ListView):
    section = "campaigns"
    template_name = "pages/members/campaigns/list.html"
    context_object_name = "campaigns"
    paginate_by = 20

    def get_queryset(self):
        return selectors.campaigns_with_counts(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["remaining_quota"] = services.remaining_quota(self.request.user)
        return context


class CampaignCreateView(MemberAreaMixin, FormView):
    section = "campaigns"
    form_class = CampaignForm
    template_name = "pages/members/campaigns/form.html"

    def get_wa_groups(self):
        try:
            return wa_services.whatsapp_groups(self.request.user)
        except waha.WahaError:
            self.wa_groups_error = True
            return []

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        kwargs["wa_groups"] = self.get_wa_groups()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = WhatsAppSession.objects.filter(owner=self.request.user).first()
        context["wa_session"] = session
        context["wa_groups_error"] = getattr(self, "wa_groups_error", False)
        context["remaining_quota"] = services.remaining_quota(self.request.user)
        return context

    def form_valid(self, form):
        data = form.cleaned_data
        campaign = services.create_campaign(
            self.request.user,
            name=data["name"],
            body=data["body"],
            all_contacts=data["send_to_all_contacts"],
            groups=data["contact_groups"],
            wa_groups=form.selected_wa_groups(),
        )
        messages.info(self.request, "Kampanye disimpan sebagai draf. Periksa lalu mulai kirim.")
        return redirect(campaign)


class CampaignDetailView(MemberAreaMixin, OwnedQuerysetMixin, DetailView):
    section = "campaigns"
    owned_selector = selectors.campaigns_for
    template_name = "pages/members/campaigns/detail.html"
    context_object_name = "campaign"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.object
        context["progress"] = services.progress(campaign)
        context["sample"] = campaign.recipients.first()
        context["recipients"] = campaign.recipients.select_related("contact")[:200]
        context["remaining_quota"] = services.remaining_quota(self.request.user)
        return context


class CampaignProgressView(MemberAreaMixin, OwnedQuerysetMixin, View):
    owned_selector = selectors.campaigns_for

    def get(self, request, pk):
        campaign = get_object_or_404(self.get_queryset(), pk=pk)
        return JsonResponse(services.progress(campaign))


class CampaignStartView(MemberAreaMixin, OwnedQuerysetMixin, View):
    owned_selector = selectors.campaigns_for

    def post(self, request, pk):
        campaign = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            services.start_campaign(campaign)
            messages.success(request, "Pengiriman dimulai. Pesan dikirim bertahap dengan jeda.")
        except services.CampaignError as exc:
            messages.error(request, str(exc))
        return redirect(campaign)


class CampaignCancelView(MemberAreaMixin, OwnedQuerysetMixin, View):
    owned_selector = selectors.campaigns_for

    def post(self, request, pk):
        campaign = get_object_or_404(self.get_queryset(), pk=pk)
        services.cancel_campaign(campaign, by=request.user)
        messages.success(request, "Kampanye dihentikan. Pesan yang belum terkirim dibatalkan.")
        return redirect(campaign)


@method_decorator(csrf_exempt, name="dispatch")
class CampaignCallbackView(View):
    """Callback n8n per penerima. Dilindungi token di header X-SC-Token."""

    def post(self, request):
        expected = settings.N8N_CALLBACK_TOKEN
        received = request.headers.get("X-SC-Token", "")
        if not expected or not hmac.compare_digest(received, expected):
            return HttpResponseForbidden("invalid token")
        try:
            payload = json.loads(request.body)
            if not isinstance(payload, dict):
                raise ValueError
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        try:
            result = services.record_result(payload)
        except services.CampaignError as exc:
            return JsonResponse({"ok": False, "error": str(exc), "continue": False}, status=404)
        return JsonResponse({"ok": True, **result})
