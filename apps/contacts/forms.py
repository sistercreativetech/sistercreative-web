from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from apps.core.phone import normalize_whatsapp

from . import messages as message_vars
from .models import Contact, ContactGroup, MessageTemplate


class OwnedFormMixin:
    """Form yang datanya milik satu member: terima `owner` dan batasi pilihan grup."""

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        if "groups" in self.fields:
            self.fields["groups"].queryset = ContactGroup.objects.filter(owner=owner)

    def owned_queryset(self, model):
        queryset = model.objects.filter(owner=self.owner)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        return queryset

    def save(self, commit=True):
        self.instance.owner = self.owner
        return super().save(commit=commit)


class ContactForm(OwnedFormMixin, forms.ModelForm):
    phone = forms.CharField(
        label="Nomor WhatsApp",
        max_length=20,
        widget=forms.TextInput(attrs={"inputmode": "tel", "placeholder": "0812-3456-7890"}),
    )

    class Meta:
        model = Contact
        fields = ["name", "phone", "groups", "is_opted_out"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Siti Aminah"}),
            "groups": forms.CheckboxSelectMultiple,
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_phone(self):
        phone = normalize_whatsapp(self.cleaned_data["phone"])
        if self.owned_queryset(Contact).filter(phone=phone).exists():
            raise ValidationError("Nomor ini sudah ada di daftar kontak Anda.")
        return phone

    def save(self, commit=True):
        if "is_opted_out" in self.changed_data:
            self.instance.opted_out_at = timezone.now() if self.instance.is_opted_out else None
        return super().save(commit=commit)

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk:
            count = Contact.objects.filter(owner=self.owner).count()
            if count >= settings.MAX_CONTACTS_PER_MEMBER:
                raise ValidationError(
                    f"Batas {settings.MAX_CONTACTS_PER_MEMBER} kontak per member sudah tercapai."
                )
        return cleaned


class ContactGroupForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = ContactGroup
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Wali murid kelas 5"}),
            "description": forms.TextInput(attrs={"placeholder": "Opsional"}),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if self.owned_queryset(ContactGroup).filter(name__iexact=name).exists():
            raise ValidationError("Anda sudah punya grup dengan nama ini.")
        return name


class MessageTemplateForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = MessageTemplate
        fields = ["name", "body"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Pengingat jadwal ngaji"}),
            "body": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": (
                        "Assalamu'alaikum {nama_depan}, mengingatkan jadwal ngaji "
                        "besok pukul 16.00. Terima kasih."
                    ),
                }
            ),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if self.owned_queryset(MessageTemplate).filter(name__iexact=name).exists():
            raise ValidationError("Anda sudah punya template dengan nama ini.")
        return name

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        unknown = message_vars.unknown_variables(body)
        if unknown:
            allowed = ", ".join(f"{{{name}}}" for name in message_vars.VARIABLES)
            raise ValidationError(
                f"Variabel tidak dikenal: {', '.join('{' + n + '}' for n in unknown)}. "
                f"Yang tersedia: {allowed}."
            )
        return body


class ContactImportForm(forms.Form):
    file = forms.FileField(
        label="File CSV",
        validators=[FileExtensionValidator(["csv", "txt"])],
        help_text="Kolom: nama, nomor. Bisa dipisah koma atau titik koma (format Excel).",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )
    group = forms.ModelChoiceField(
        label="Masukkan ke grup",
        queryset=ContactGroup.objects.none(),
        required=False,
        empty_label="Tanpa grup",
    )
    new_group_name = forms.CharField(
        label="Atau buat grup baru",
        max_length=80,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Contoh: Pelanggan November"}),
    )

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = ContactGroup.objects.filter(owner=owner)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        limit = settings.CONTACT_IMPORT_MAX_BYTES
        if upload.size > limit:
            raise ValidationError(f"Ukuran file maksimal {filesizeformat(limit)}.")
        return upload

    def clean_new_group_name(self):
        return " ".join(self.cleaned_data["new_group_name"].split())

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("group") and cleaned.get("new_group_name"):
            raise ValidationError("Pilih grup yang ada atau buat grup baru, jangan keduanya.")
        return cleaned

    def target_group(self) -> ContactGroup | None:
        name = self.cleaned_data.get("new_group_name")
        if name:
            group, _ = ContactGroup.objects.get_or_create(owner=self.owner, name=name)
            return group
        return self.cleaned_data.get("group")


class TemplatePreviewForm(forms.Form):
    """Nama contoh untuk pratinjau template."""

    sample_name = forms.CharField(max_length=120, required=False)
