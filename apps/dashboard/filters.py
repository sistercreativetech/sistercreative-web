import django_filters
from django import forms
from django.db.models import Q

from apps.accounts.models import User
from apps.portfolio.models import Category, Project


class MemberFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Cari member",
        max_length=100,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Nama, email, atau nomor"}),
    )
    status = django_filters.ChoiceFilter(
        choices=User.Status.choices, label="Status", empty_label="Semua status"
    )

    class Meta:
        model = User
        fields = ["q", "status"]

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        digits = "".join(ch for ch in value if ch.isdigit())
        condition = Q(full_name__icontains=value) | Q(email__icontains=value)
        if len(digits) >= 4:
            condition |= Q(whatsapp_number__contains=digits.lstrip("0"))
        return queryset.filter(condition)


class DashboardProjectFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        field_name="title",
        lookup_expr="icontains",
        label="Cari judul",
        max_length=100,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Judul proyek"}),
    )
    is_published = django_filters.ChoiceFilter(
        choices=[("1", "Terbit"), ("0", "Draf")],
        label="Status",
        empty_label="Semua status",
        method="filter_published",
    )
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.all(), label="Kategori", empty_label="Semua kategori"
    )

    class Meta:
        model = Project
        fields = ["q", "is_published", "category"]

    def filter_published(self, queryset, name, value):
        return queryset.filter(is_published=value == "1")
