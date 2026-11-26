import django_filters
from django import forms
from django.db.models import Q

from .models import Contact, ContactGroup


class ContactFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Cari kontak",
        max_length=100,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Nama atau nomor"}),
    )
    group = django_filters.ModelChoiceFilter(
        field_name="groups",
        queryset=ContactGroup.objects.none(),
        label="Grup",
        empty_label="Semua grup",
    )
    subscription = django_filters.ChoiceFilter(
        choices=[("active", "Bisa dikirimi"), ("opted_out", "Berhenti berlangganan")],
        label="Status",
        empty_label="Semua status",
        method="filter_subscription",
    )

    class Meta:
        model = Contact
        fields = ["q", "group", "subscription"]

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["group"].queryset = ContactGroup.objects.filter(owner=owner)

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        condition = Q(name__icontains=value)
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) >= 4:
            condition |= Q(phone__contains=digits.lstrip("0"))
        return queryset.filter(condition)

    def filter_subscription(self, queryset, name, value):
        return queryset.filter(is_opted_out=value == "opted_out")
