from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.contacts.selectors import member_overview

from .mixins import MemberAreaMixin


class MemberHomeView(MemberAreaMixin, TemplateView):
    section = "home"
    template_name = "pages/members/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["overview"] = member_overview(self.request.user)
        return context


class PendingApprovalView(LoginRequiredMixin, TemplateView):
    """Halaman status untuk member yang belum disetujui."""

    template_name = "pages/members/pending.html"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and (user.is_staff or user.is_approved_member):
            return redirect("members:home")
        return super().dispatch(request, *args, **kwargs)
