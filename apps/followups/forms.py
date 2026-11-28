from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import FileExtensionValidator

from apps.campaigns.forms import validate_campaign_image
from apps.campaigns.images import prepare_image
from apps.contacts import messages as message_vars
from apps.contacts.forms import OwnedFormMixin
from apps.contacts.models import Contact, ContactGroup
from apps.core.validators import ALLOWED_IMAGE_EXTENSIONS

from .models import FollowUpSequence, FollowUpStep

RESERVED_WORDS = {"STOP", "BERHENTI", "UNSUBSCRIBE", "UNREG"}
MAX_DELAY = {FollowUpStep.Unit.HOURS: 720, FollowUpStep.Unit.DAYS: 90}


class FollowUpSequenceForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = FollowUpSequence
        fields = [
            "name",
            "trigger",
            "keywords",
            "stop_on_reply",
            "is_active",
            "send_from",
            "send_until",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Calon pembeli paket website"}),
            "trigger": forms.RadioSelect,
            "keywords": forms.TextInput(attrs={"placeholder": "harga, paket, daftar"}),
            "send_from": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "send_until": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_keywords(self):
        words = []
        for raw in self.cleaned_data["keywords"].split(","):
            word = " ".join(raw.split())
            if word and word.lower() not in {w.lower() for w in words}:
                words.append(word)
        if any(word.upper() in RESERVED_WORDS for word in words):
            raise ValidationError(
                "STOP/BERHENTI dipakai untuk berhenti berlangganan dan tidak bisa dipakai."
            )
        return ", ".join(words)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("trigger") == FollowUpSequence.Trigger.KEYWORD and not cleaned.get(
            "keywords"
        ):
            self.add_error("keywords", "Isi minimal satu kata kunci untuk pemicu ini.")
        start, end = cleaned.get("send_from"), cleaned.get("send_until")
        if start and end and start >= end:
            self.add_error("send_until", "Jam selesai harus setelah jam mulai (di hari yang sama).")
        return cleaned


class FollowUpStepForm(forms.ModelForm):
    image = forms.ImageField(
        label="Gambar",
        required=False,
        validators=[FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS), validate_campaign_image],
        help_text="JPG, PNG, atau WebP, maks 5 MB. Isi pesan menjadi keterangan gambar.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )

    class Meta:
        model = FollowUpStep
        fields = ["delay_value", "delay_unit", "body", "image"]
        widgets = {
            "delay_value": forms.NumberInput(attrs={"min": 1, "max": 720}),
            "body": forms.Textarea(
                attrs={
                    "rows": 7,
                    "placeholder": (
                        "Halo {nama_depan}, kemarin sempat tanya soal paket website. "
                        "Masih ada yang bisa kami bantu jelaskan?"
                    ),
                }
            ),
        }
        help_texts = {"body": "Variabel: {nama}, {nama_depan}, {nomor}."}

    def __init__(self, *args, sequence, **kwargs):
        self.sequence = sequence
        super().__init__(*args, **kwargs)
        self.fields["delay_value"].label = "Dikirim setelah"
        self.fields["delay_unit"].label = "Satuan"

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        unknown = message_vars.unknown_variables(body)
        if unknown:
            raise ValidationError(
                "Variabel tidak dikenal: " + ", ".join("{" + n + "}" for n in unknown)
            )
        return body

    def clean(self):
        cleaned = super().clean()
        siblings = self.sequence.steps.all()
        if self.instance.pk:
            siblings = siblings.exclude(pk=self.instance.pk)
        elif siblings.count() >= settings.FOLLOWUP_MAX_STEPS:
            raise ValidationError(
                f"Satu urutan maksimal {settings.FOLLOWUP_MAX_STEPS} langkah follow-up."
            )

        value, unit = cleaned.get("delay_value"), cleaned.get("delay_unit")
        if value is not None and unit:
            if not 1 <= value <= MAX_DELAY[unit]:
                self.add_error(
                    "delay_value", f"Isi antara 1 dan {MAX_DELAY[unit]} {unit_label(unit)}."
                )
            else:
                minutes = value * FollowUpStep.UNIT_MINUTES[unit]
                if siblings.filter(delay_minutes=minutes).exists():
                    self.add_error("delay_value", "Sudah ada langkah dengan waktu yang sama.")

        body = cleaned.get("body") or ""
        has_image = cleaned.get("image") or (
            self.instance.image and cleaned.get("image") is not False
        )
        if has_image and len(body) > settings.CAMPAIGN_CAPTION_MAX_CHARS:
            self.add_error(
                "body",
                f"Dengan gambar, isi pesan maksimal {settings.CAMPAIGN_CAPTION_MAX_CHARS} karakter "
                f"(sekarang {len(body)}).",
            )
        return cleaned

    def save(self, commit=True):
        self.instance.sequence = self.sequence
        upload = self.cleaned_data.get("image")
        if isinstance(upload, UploadedFile):
            self.instance.image = prepare_image(upload)
        return super().save(commit=commit)


def unit_label(unit: str) -> str:
    return FollowUpStep.Unit(unit).label


class EnrollContactsForm(forms.Form):
    all_contacts = forms.BooleanField(label="Semua kontak saya", required=False)
    groups = forms.ModelMultipleChoiceField(
        label="Grup kontak",
        queryset=ContactGroup.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.fields["groups"].queryset = ContactGroup.objects.filter(owner=owner)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("all_contacts") and not cleaned.get("groups"):
            raise ValidationError("Pilih semua kontak atau minimal satu grup.")
        return cleaned

    def contacts(self):
        queryset = Contact.objects.filter(owner=self.owner)
        if not self.cleaned_data["all_contacts"]:
            queryset = queryset.filter(groups__in=self.cleaned_data["groups"]).distinct()
        return queryset.order_by("pk")
