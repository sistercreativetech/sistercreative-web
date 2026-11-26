from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView
from django_filters.views import FilterView

from apps.accounts import services as account_services
from apps.accounts.mixins import StaffRequiredMixin
from apps.portfolio.models import Category, Project

from . import selectors
from .filters import DashboardProjectFilter, MemberFilter
from .forms import CategoryForm, MemberQuotaForm, MemberStatusForm, ProjectForm


class DashboardMixin(StaffRequiredMixin):
    """Semua halaman dashboard: wajib staff + menandai menu aktif."""

    section = "home"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dashboard_section"] = self.section
        context["pending_count"] = selectors.pending_members().count()
        return context


class FilterQuerystringMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_querystring"] = params.urlencode()
        context["is_filtered"] = any(value for key, value in params.items())
        return context


# --- Ringkasan ----------------------------------------------------------------


class DashboardHomeView(DashboardMixin, TemplateView):
    template_name = "pages/dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = selectors.overview_stats()
        context["pending_preview"] = selectors.pending_members(limit=5)
        return context


# --- Member -------------------------------------------------------------------


class MemberListView(DashboardMixin, FilterQuerystringMixin, FilterView):
    section = "members"
    filterset_class = MemberFilter
    template_name = "pages/dashboard/members/list.html"
    context_object_name = "members"
    paginate_by = 20

    def get_queryset(self):
        return selectors.members().order_by("-date_joined")


class MemberDetailView(DashboardMixin, SuccessMessageMixin, UpdateView):
    """Detail member + ubah kuota. Ubah status lewat MemberStatusView."""

    section = "members"
    form_class = MemberQuotaForm
    template_name = "pages/dashboard/members/detail.html"
    context_object_name = "member"
    success_message = "Kuota pesan %(full_name)s disimpan."

    def get_queryset(self):
        return selectors.members()

    def get_success_url(self):
        return reverse("dashboard:member_detail", kwargs={"pk": self.object.pk})

    def get_success_message(self, cleaned_data):
        return self.success_message % {"full_name": self.object.full_name}


class MemberStatusView(StaffRequiredMixin, View):
    """POST status baru (setujui/tolak/nonaktifkan) untuk satu member."""

    messages_by_status = {
        "active": "%s disetujui dan sekarang aktif.",
        "rejected": "Pendaftaran %s ditolak.",
        "suspended": "Akun %s dinonaktifkan.",
        "pending": "%s dikembalikan ke status menunggu.",
    }

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        member = get_object_or_404(selectors.members(), pk=pk)
        form = MemberStatusForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Status tidak valid.")
        else:
            status = form.cleaned_data["status"]
            account_services.set_member_status(member, status, by=request.user)
            messages.success(request, self.messages_by_status[status] % member.full_name)
        next_url = request.POST.get("next")
        if next_url == "list":
            return redirect("dashboard:member_list")
        return redirect("dashboard:member_detail", pk=member.pk)


# --- Portofolio ---------------------------------------------------------------


class ProjectListView(DashboardMixin, FilterQuerystringMixin, FilterView):
    section = "projects"
    filterset_class = DashboardProjectFilter
    template_name = "pages/dashboard/projects/list.html"
    context_object_name = "projects"
    paginate_by = 20

    def get_queryset(self):
        return selectors.all_projects()


class ProjectCreateView(DashboardMixin, SuccessMessageMixin, CreateView):
    section = "projects"
    model = Project
    form_class = ProjectForm
    template_name = "pages/dashboard/projects/form.html"
    success_url = reverse_lazy("dashboard:project_list")
    success_message = "Proyek “%(title)s” ditambahkan."


class ProjectUpdateView(DashboardMixin, SuccessMessageMixin, UpdateView):
    section = "projects"
    model = Project
    form_class = ProjectForm
    template_name = "pages/dashboard/projects/form.html"
    success_url = reverse_lazy("dashboard:project_list")
    success_message = "Proyek “%(title)s” diperbarui."

    def form_valid(self, form):
        old_image = Project.objects.get(pk=self.object.pk).cover_image
        response = super().form_valid(form)
        if old_image and old_image.name != self.object.cover_image.name:
            old_image.delete(save=False)
        return response


class ProjectDeleteView(DashboardMixin, DeleteView):
    section = "projects"
    model = Project
    template_name = "pages/dashboard/confirm_delete.html"
    success_url = reverse_lazy("dashboard:project_list")
    extra_context = {"object_type": "proyek", "cancel_url": reverse_lazy("dashboard:project_list")}

    def form_valid(self, form):
        image = self.object.cover_image
        title = self.object.title
        response = super().form_valid(form)
        if image:
            image.delete(save=False)
        messages.success(self.request, f"Proyek “{title}” dihapus.")
        return response


# --- Kategori -----------------------------------------------------------------


class CategoryListView(DashboardMixin, ListView):
    section = "categories"
    template_name = "pages/dashboard/categories/list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return selectors.categories_with_counts()


class CategoryCreateView(DashboardMixin, SuccessMessageMixin, CreateView):
    section = "categories"
    model = Category
    form_class = CategoryForm
    template_name = "pages/dashboard/categories/form.html"
    success_url = reverse_lazy("dashboard:category_list")
    success_message = "Kategori “%(name)s” ditambahkan."


class CategoryUpdateView(DashboardMixin, SuccessMessageMixin, UpdateView):
    section = "categories"
    model = Category
    form_class = CategoryForm
    template_name = "pages/dashboard/categories/form.html"
    success_url = reverse_lazy("dashboard:category_list")
    success_message = "Kategori “%(name)s” diperbarui."


class CategoryDeleteView(DashboardMixin, DeleteView):
    section = "categories"
    model = Category
    template_name = "pages/dashboard/confirm_delete.html"
    success_url = reverse_lazy("dashboard:category_list")
    extra_context = {
        "object_type": "kategori",
        "cancel_url": reverse_lazy("dashboard:category_list"),
    }

    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"Kategori “{name}” masih dipakai proyek. Pindahkan proyeknya dulu.",
            )
            return redirect("dashboard:category_list")
        messages.success(self.request, f"Kategori “{name}” dihapus.")
        return response
