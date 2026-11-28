from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.template.defaultfilters import filesizeformat

from .models import EmailCampaign, MailingList, Subscriber
from .rendering import VARIABLES, unknown_variables
from .services import normalize_email

MAX_SKIP_DAYS = 365


class EmailCampaignForm(forms.ModelForm):
    class Meta:
        model = EmailCampaign
        fields = [
            "name",
            "subject",
            "body",
            "button_label",
            "button_url",
            "send_to_all",
            "lists",
            "skip_recent_days",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Contoh: Follow-up Remote Journal"}),
            "subject": forms.TextInput(attrs={"placeholder": "Halo {nama_depan}, ada kabar baru"}),
            "body": forms.Textarea(attrs={"rows": 14}),
            "button_label": forms.TextInput(attrs={"placeholder": "Gabung grup sekarang"}),
            "button_url": forms.URLInput(attrs={"placeholder": "https://chat.whatsapp.com/..."}),
            "lists": forms.CheckboxSelectMultiple,
            "skip_recent_days": forms.NumberInput(attrs={"min": 0, "max": MAX_SKIP_DAYS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lists"].queryset = MailingList.objects.all()
        self.fields["lists"].required = False

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_skip_recent_days(self):
        days = self.cleaned_data["skip_recent_days"]
        if days > MAX_SKIP_DAYS:
            raise ValidationError(f"Maksimal {MAX_SKIP_DAYS} hari.")
        return days

    def clean(self):
        cleaned = super().clean()
        unknown = unknown_variables(cleaned.get("subject", ""), cleaned.get("body", ""))
        if unknown:
            allowed = ", ".join(f"{{{name}}}" for name in VARIABLES)
            names = ", ".join(f"{{{name}}}" for name in unknown)
            raise ValidationError(f"Variabel {names} tidak dikenal. Yang tersedia: {allowed}.")
        if bool(cleaned.get("button_label")) != bool(cleaned.get("button_url")):
            raise ValidationError(
                "Isi teks tombol dan link tombol bersamaan, atau kosongkan keduanya."
            )
        if not cleaned.get("send_to_all") and not cleaned.get("lists"):
            raise ValidationError("Pilih “semua pelanggan” atau minimal satu daftar.")
        if cleaned.get("send_to_all"):
            cleaned["lists"] = MailingList.objects.none()
        return cleaned


class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ["email", "name", "lists"]
        widgets = {"lists": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lists"].queryset = MailingList.objects.all()
        self.fields["lists"].required = False

    def clean_email(self):
        email = normalize_email(self.cleaned_data["email"])
        if Subscriber.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Email ini sudah terdaftar.")
        return email

    def save(self, commit=True):
        self.instance.source = self.instance.source or "Ditambah admin"
        return super().save(commit)


class SubscriberImportForm(forms.Form):
    file = forms.FileField(
        label="File CSV",
        validators=[FileExtensionValidator(["csv", "txt"])],
        help_text=(
            "Wajib ada kolom “email”; kolom “nama” dan “updated” (tanggal terakhir dikirimi) "
            "opsional. Dari Google Sheets: File → Download → CSV."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )
    mailing_list = forms.ModelChoiceField(
        label="Masukkan ke daftar",
        queryset=MailingList.objects.none(),
        required=False,
        empty_label="Tanpa daftar",
    )
    new_list_name = forms.CharField(
        label="Atau buat daftar baru",
        max_length=80,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Contoh: Pendaftar Remote Journal"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mailing_list"].queryset = MailingList.objects.all()

    def clean_file(self):
        upload = self.cleaned_data["file"]
        limit = settings.CONTACT_IMPORT_MAX_BYTES
        if upload.size > limit:
            raise ValidationError(f"Ukuran file maksimal {filesizeformat(limit)}.")
        return upload

    def clean_new_list_name(self):
        return " ".join(self.cleaned_data["new_list_name"].split())

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("mailing_list") and cleaned.get("new_list_name"):
            raise ValidationError("Pilih daftar yang ada atau buat daftar baru, jangan keduanya.")
        return cleaned

    def target_list(self) -> MailingList | None:
        name = self.cleaned_data.get("new_list_name")
        if name:
            mailing_list, _ = MailingList.objects.get_or_create(name=name)
            return mailing_list
        return self.cleaned_data.get("mailing_list")


class TestEmailForm(forms.Form):
    email = forms.EmailField(label="Kirim email uji ke")
