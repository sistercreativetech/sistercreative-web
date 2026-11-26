from django.db import connection
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from apps.portfolio.selectors import featured_projects

from . import content


class HomeView(TemplateView):
    template_name = "pages/home.html"
    extra_context = {
        "trust_points": content.TRUST_POINTS,
        "hero_flow": content.HERO_FLOW,
        "services": content.SERVICES,
        "process_steps": content.PROCESS_STEPS,
        "wa_messages": content.WHATSAPP_MESSAGES,
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_projects"] = featured_projects()
        return context


class HealthView(View):
    """Cek kesehatan untuk monitoring/deploy: aplikasi hidup dan database terjangkau."""

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"ok": True})
