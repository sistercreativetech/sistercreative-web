from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView
from django_filters.views import FilterView

from apps.members.mixins import MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin

from . import messages as message_vars
from . import selectors, services
from .filters import ContactFilter
from .forms import ContactForm, ContactGroupForm, ContactImportForm, MessageTemplateForm
from .messages import render_message

# --- Kontak -------------------------------------------------------------------


class ContactListView(MemberAreaMixin, FilterView):
    section = "contacts"
    filterset_class = ContactFilter
    template_name = "pages/members/contacts/list.html"
    context_object_name = "contacts"
    paginate_by = 25

    def get_queryset(self):
        return selectors.contacts_for(self.request.user)

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super().get_filterset_kwargs(filterset_class)
        kwargs["owner"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_querystring"] = params.urlencode()
        context["is_filtered"] = any(params.values())
        context["total_contacts"] = selectors.contacts_for(self.request.user).count()
        return context


class ContactCreateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, CreateView
):
    section = "contacts"
    owned_selector = selectors.contacts_for
    form_class = ContactForm
    template_name = "pages/members/contacts/form.html"
    success_url = reverse_lazy("members:contact_list")
    success_message = "Kontak disimpan."


class ContactUpdateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, UpdateView
):
    section = "contacts"
    owned_selector = selectors.contacts_for
    form_class = ContactForm
    template_name = "pages/members/contacts/form.html"
    success_url = reverse_lazy("members:contact_list")
    success_message = "Kontak diperbarui."


class ContactDeleteView(MemberAreaMixin, OwnedQuerysetMixin, DeleteView):
    section = "contacts"
    owned_selector = selectors.contacts_for
    template_name = "pages/members/confirm_delete.html"
    success_url = reverse_lazy("members:contact_list")
    extra_context = {"object_type": "kontak", "cancel_url": reverse_lazy("members:contact_list")}

    def form_valid(self, form):
        messages.success(self.request, f"Kontak {self.object} dihapus.")
        return super().form_valid(form)


class ContactImportView(MemberAreaMixin, OwnerFormMixin, FormView):
    section = "contacts"
    form_class = ContactImportForm
    template_name = "pages/members/contacts/import.html"

    def form_valid(self, form):
        raw = form.cleaned_data["file"].read()
        try:
            result = services.import_contacts(self.request.user, raw, form.target_group())
        except services.ImportFileError as exc:
            form.add_error("file", str(exc))
            return self.form_invalid(form)
        if result.total_valid:
            messages.success(self.request, f"{result.created} kontak baru ditambahkan.")
        # Tampilkan ringkasan di halaman yang sama (bukan redirect) agar baris error terlihat.
        return self.render_to_response(
            self.get_context_data(
                form=self.get_form_class()(owner=self.request.user), result=result
            )
        )


class ContactSampleCsvView(MemberAreaMixin, View):
    def get(self, request):
        response = HttpResponse(services.sample_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="contoh-kontak.csv"'
        return response


# --- Grup ---------------------------------------------------------------------


class GroupListView(MemberAreaMixin, ListView):
    section = "groups"
    template_name = "pages/members/groups/list.html"
    context_object_name = "groups"

    def get_queryset(self):
        return selectors.groups_for(self.request.user)


class GroupCreateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, CreateView
):
    section = "groups"
    owned_selector = selectors.groups_for
    form_class = ContactGroupForm
    template_name = "pages/members/groups/form.html"
    success_url = reverse_lazy("members:group_list")
    success_message = "Grup “%(name)s” dibuat."


class GroupUpdateView(
    MemberAreaMixin, OwnedQuerysetMixin, OwnerFormMixin, SuccessMessageMixin, UpdateView
):
    section = "groups"
    owned_selector = selectors.groups_for
    form_class = ContactGroupForm
    template_name = "pages/members/groups/form.html"
    success_url = reverse_lazy("members:group_list")
    success_message = "Grup “%(name)s” diperbarui."


class GroupDeleteView(MemberAreaMixin, OwnedQuerysetMixin, DeleteView):
    section = "groups"
    owned_selector = selectors.groups_for
    template_name = "pages/members/confirm_delete.html"
    success_url = reverse_lazy("members:group_list")
    extra_context = {
        "object_type": "grup",
        "cancel_url": reverse_lazy("members:group_list"),
        "delete_note": "Kontak di dalam grup tidak ikut terhapus.",
    }

    def form_valid(self, form):
        messages.success(self.request, f"Grup “{self.object}” dihapus.")
        return super().form_valid(form)


# --- Template pesan -----------------------------------------------------------


class TemplatePreviewMixin:
    """Tombol "Pratinjau" (name=action value=preview) merender ulang form beserta contoh pesan."""

    preview_name = "Siti Aminah"
    preview_phone = "6281234567890"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["variables"] = message_vars.VARIABLES
        return context

    def form_valid(self, form):
        if self.request.POST.get("action") == "preview":
            preview = render_message(
                form.cleaned_data["body"], name=self.preview_name, phone=self.preview_phone
            )
            return self.render_to_response(
                self.get_context_data(form=form, preview=preview, preview_name=self.preview_name)
            )
        return super().form_valid(form)


class TemplateListView(MemberAreaMixin, ListView):
    section = "templates"
    template_name = "pages/members/templates/list.html"
    context_object_name = "message_templates"

    def get_queryset(self):
        return selectors.templates_for(self.request.user)


class TemplateCreateView(
    MemberAreaMixin,
    OwnedQuerysetMixin,
    OwnerFormMixin,
    TemplatePreviewMixin,
    SuccessMessageMixin,
    CreateView,
):
    section = "templates"
    owned_selector = selectors.templates_for
    form_class = MessageTemplateForm
    template_name = "pages/members/templates/form.html"
    success_url = reverse_lazy("members:template_list")
    success_message = "Template “%(name)s” disimpan."


class TemplateUpdateView(
    MemberAreaMixin,
    OwnedQuerysetMixin,
    OwnerFormMixin,
    TemplatePreviewMixin,
    SuccessMessageMixin,
    UpdateView,
):
    section = "templates"
    owned_selector = selectors.templates_for
    form_class = MessageTemplateForm
    template_name = "pages/members/templates/form.html"
    success_url = reverse_lazy("members:template_list")
    success_message = "Template “%(name)s” diperbarui."


class TemplateDeleteView(MemberAreaMixin, OwnedQuerysetMixin, DeleteView):
    section = "templates"
    owned_selector = selectors.templates_for
    template_name = "pages/members/confirm_delete.html"
    success_url = reverse_lazy("members:template_list")
    extra_context = {
        "object_type": "template",
        "cancel_url": reverse_lazy("members:template_list"),
    }

    def form_valid(self, form):
        messages.success(self.request, f"Template “{self.object}” dihapus.")
        return super().form_valid(form)
