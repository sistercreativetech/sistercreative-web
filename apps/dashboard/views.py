from django.views.generic import TemplateView

from apps.accounts.mixins import StaffRequiredMixin

from . import selectors


class DashboardHomeView(StaffRequiredMixin, TemplateView):
    template_name = "pages/dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = selectors.overview_stats()
        return context
