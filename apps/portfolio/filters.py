import django_filters
from django import forms
from django.db.models import Q

from . import selectors
from .models import Project


class ProjectFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Cari proyek",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Contoh: WhatsApp, laporan",
                "type": "search",
            }
        ),
    )
    category = django_filters.ModelChoiceFilter(
        field_name="category",
        to_field_name="slug",
        queryset=lambda request: selectors.categories_with_projects(),
        label="Kategori",
        empty_label="Semua kategori",
    )
    tag = django_filters.ModelChoiceFilter(
        field_name="tags",
        to_field_name="slug",
        queryset=lambda request: selectors.tags_with_projects(),
        label="Teknologi",
        empty_label="Semua teknologi",
    )

    class Meta:
        model = Project
        fields = ["q", "category", "tag"]

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value)
            | Q(summary__icontains=value)
            | Q(client_name__icontains=value)
            | Q(tags__name__icontains=value)
        ).distinct()
