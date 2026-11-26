from apps.accounts.mixins import ApprovedMemberRequiredMixin


class MemberAreaMixin(ApprovedMemberRequiredMixin):
    """Halaman area member: wajib member aktif + menandai menu aktif."""

    section = "home"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["member_section"] = self.section
        return context


class OwnedQuerysetMixin:
    """Batasi queryset ke data milik user yang login (data member lain → 404).

    Isi `owned_selector` dengan fungsi selector `owner -> QuerySet`.
    """

    owned_selector = None

    def get_queryset(self):
        return type(self).owned_selector(self.request.user)


class OwnerFormMixin:
    """Teruskan `owner` ke form (lihat apps.contacts.forms.OwnedFormMixin)."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs
