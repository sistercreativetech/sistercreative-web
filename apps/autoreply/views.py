from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.members.mixins import MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin

from . import selectors, services
from .forms import AutoReplyRuleForm, AutoReplyTestForm


class RuleListView(MemberAreaMixin, ListView):
    """Daftar aturan + form "coba pesan" (GET, tanpa mengirim apa pun)."""

    section = "autoreply"
    template_name = "pages/members/autoreply/list.html"
    context_object_name = "rules"

    def get_queryset(self):
        return selectors.rules_with_stats(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        test_form = AutoReplyTestForm(self.request.GET or None)
        context["test_form"] = test_form
        if test_form.is_bound and test_form.is_valid():
            rule, reply = services.preview(
                self.request.user,
                test_form.cleaned_data["message"],
                name=test_form.cleaned_data["name"],
            )
            context["test_result"] = {"rule": rule, "reply": reply}
        context["hourly_used"] = services.hourly_count(self.request.user)
        context["autoreply_limit"] = settings.AUTO_REPLY_MAX_PER_HOUR
        return context


class RuleCreateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, CreateView
):
    section = "autoreply"
    owned_selector = selectors.rules_for
    form_class = AutoReplyRuleForm
    template_name = "pages/members/autoreply/form.html"
    success_url = reverse_lazy("autoreply:rule_list")
    success_message = "Aturan “%(name)s” disimpan."


class RuleUpdateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, UpdateView
):
    section = "autoreply"
    owned_selector = selectors.rules_for
    form_class = AutoReplyRuleForm
    template_name = "pages/members/autoreply/form.html"
    success_url = reverse_lazy("autoreply:rule_list")
    success_message = "Aturan “%(name)s” diperbarui."


class RuleDeleteView(MemberAreaMixin, OwnedQuerysetMixin, DeleteView):
    section = "autoreply"
    owned_selector = selectors.rules_for
    template_name = "pages/members/confirm_delete.html"
    success_url = reverse_lazy("autoreply:rule_list")
    extra_context = {
        "object_type": "aturan balas otomatis",
        "cancel_url": reverse_lazy("autoreply:rule_list"),
    }

    def form_valid(self, form):
        messages.success(self.request, f"Aturan “{self.object}” dihapus.")
        return super().form_valid(form)


class LogListView(MemberAreaMixin, ListView):
    section = "autoreply"
    template_name = "pages/members/autoreply/logs.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        return selectors.logs_for(self.request.user)
