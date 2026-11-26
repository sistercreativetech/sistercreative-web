from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
from django.core.exceptions import ValidationError

from apps.core.phone import normalize_whatsapp

from .models import User


class SignupForm(AllauthSignupForm):
    """Pendaftaran member: nama, email, nomor WhatsApp, kata sandi."""

    full_name = forms.CharField(
        label="Nama lengkap",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Siti Aminah"}),
    )
    whatsapp_number = forms.CharField(
        label="Nomor WhatsApp",
        max_length=20,
        help_text="Nomor yang nanti dipakai untuk mengirim pesan, contoh 0812-3456-7890.",
        widget=forms.TextInput(
            attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "0812-3456-7890"}
        ),
    )

    field_order = ["full_name", "email", "whatsapp_number", "password1", "password2"]

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if len(name) < 3:
            raise ValidationError("Nama lengkap minimal 3 huruf.")
        return name

    def clean_whatsapp_number(self):
        number = normalize_whatsapp(self.cleaned_data["whatsapp_number"])
        if User.objects.filter(whatsapp_number=number).exists():
            raise ValidationError("Nomor WhatsApp ini sudah terdaftar.")
        return number

    def save(self, request):
        user = super().save(request)
        user.full_name = self.cleaned_data["full_name"]
        user.whatsapp_number = self.cleaned_data["whatsapp_number"]
        user.status = User.Status.PENDING
        user.save(update_fields=["full_name", "whatsapp_number", "status"])
        return user
