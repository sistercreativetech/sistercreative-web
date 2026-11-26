import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apps.members.mixins import MemberAreaMixin

from . import services, waha
from .models import WhatsAppSession

logger = logging.getLogger(__name__)


class SessionView(MemberAreaMixin, TemplateView):
    section = "whatsapp"
    template_name = "pages/members/whatsapp/session.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = services.get_or_init_session(self.request.user)
        context["waha_configured"] = waha.is_configured()
        context["blast_delay_min"] = settings.BLAST_DELAY_MIN
        context["blast_delay_max"] = settings.BLAST_DELAY_MAX
        if context["waha_configured"]:
            try:
                session = services.refresh_status(session)
            except waha.WahaError as exc:
                logger.warning("Status WAHA gagal untuk %s: %s", session.name, exc)
                context["waha_error"] = True
        context["wa_session"] = session
        return context


class SessionStatusView(MemberAreaMixin, View):
    """JSON kecil untuk polling halaman QR (static/js/app.js)."""

    def get(self, request):
        session = services.get_or_init_session(request.user)
        try:
            session = services.refresh_status(session)
        except waha.WahaError:
            return JsonResponse({"status": "ERROR"}, status=503)
        return JsonResponse({"status": session.status, "label": session.get_status_display()})


class SessionQrView(MemberAreaMixin, View):
    """Proksi gambar QR sesi milik member sendiri. Tidak pernah di-cache."""

    def get(self, request):
        session = services.get_or_init_session(request.user)
        try:
            image = waha.get_qr_png(session.name)
        except waha.WahaError:
            return HttpResponse(status=404)
        response = HttpResponse(image, content_type="image/png")
        response["Cache-Control"] = "no-store"
        return response


class SessionConnectView(MemberAreaMixin, View):
    def post(self, request):
        try:
            services.connect(request.user)
        except waha.WahaError as exc:
            logger.warning("Gagal menghubungkan sesi member %s: %s", request.user.pk, exc)
            messages.error(request, "Server WhatsApp sedang tidak bisa dihubungi. Coba lagi nanti.")
        return redirect("whatsapp:session")


class SessionDisconnectView(MemberAreaMixin, View):
    def post(self, request):
        try:
            services.disconnect(request.user)
            messages.success(request, "WhatsApp diputuskan dari akun ini.")
        except waha.WahaError:
            messages.error(request, "Gagal memutuskan sambungan. Coba lagi nanti.")
        return redirect("whatsapp:session")


class GroupListView(MemberAreaMixin, TemplateView):
    section = "whatsapp"
    template_name = "pages/members/whatsapp/groups.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = WhatsAppSession.objects.filter(owner=self.request.user).first()
        context["wa_session"] = session
        try:
            context["wa_groups"] = services.whatsapp_groups(
                self.request.user, refresh=self.request.GET.get("muat_ulang") == "1"
            )
        except waha.WahaError:
            context["wa_groups"] = []
            context["waha_error"] = True
        return context


@method_decorator(csrf_exempt, name="dispatch")
class WahaWebhookView(View):
    """Webhook WAHA (pesan masuk & status sesi). Dilindungi token di header X-SC-Token."""

    def post(self, request):
        expected = settings.WAHA_WEBHOOK_TOKEN
        received = request.headers.get("X-SC-Token", "")
        if not expected or not hmac.compare_digest(received, expected):
            return HttpResponseForbidden("invalid token")
        try:
            event = json.loads(request.body)
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        if not isinstance(event, dict):
            return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)
        result = services.handle_event(event)
        return JsonResponse({"ok": True, "result": result})
