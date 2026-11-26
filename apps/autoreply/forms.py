from django import forms
from django.core.exceptions import ValidationError

from apps.contacts import messages as message_vars
from apps.contacts.forms import OwnedFormMixin

from .models import AutoReplyRule


class AutoReplyRuleForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = AutoReplyRule
        fields = [
            "name",
            "keywords",
            "match_type",
            "reply",
            "is_active",
            "priority",
            "cooldown_minutes",
            "active_from",
            "active_until",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Info harga paket"}),
            "keywords": forms.TextInput(attrs={"placeholder": "harga, price, berapa, biaya"}),
            "reply": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": (
                        "Halo {nama_depan}, terima kasih sudah bertanya. "
                        "Paket website mulai Rp1,5 juta. Admin kami akan segera menghubungi."
                    ),
                }
            ),
            "active_from": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "active_until": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "priority": forms.NumberInput(attrs={"min": 0, "max": 999}),
            "cooldown_minutes": forms.NumberInput(attrs={"min": 0, "max": 1440}),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_keywords(self):
        words = []
        for raw in self.cleaned_data["keywords"].split(","):
            word = " ".join(raw.split())
            if word and word.lower() not in {w.lower() for w in words}:
                words.append(word)
        if not words:
            raise ValidationError("Isi minimal satu kata kunci.")
        if any(word.upper() in {"STOP", "BERHENTI", "UNSUBSCRIBE", "UNREG"} for word in words):
            raise ValidationError(
                "STOP/BERHENTI dipakai untuk berhenti berlangganan dan tidak bisa dipakai."
            )
        return ", ".join(words)

    def clean_reply(self):
        reply = self.cleaned_data["reply"].strip()
        unknown = message_vars.unknown_variables(reply)
        if unknown:
            raise ValidationError(
                "Variabel tidak dikenal: " + ", ".join("{" + n + "}" for n in unknown)
            )
        return reply

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("active_from"), cleaned.get("active_until")
        if (start is None) != (end is None):
            raise ValidationError("Isi jam mulai dan jam selesai, atau kosongkan keduanya.")
        return cleaned


class AutoReplyTestForm(forms.Form):
    message = forms.CharField(
        label="Contoh pesan masuk",
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Kak, harga paket website berapa ya?"}),
    )
    name = forms.CharField(
        label="Nama pengirim (opsional)",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Siti Aminah"}),
    )
