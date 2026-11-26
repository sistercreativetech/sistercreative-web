from django import forms
from django.core.exceptions import ValidationError

from apps.contacts import messages as message_vars
from apps.contacts.models import ContactGroup, MessageTemplate


class CampaignForm(forms.Form):
    name = forms.CharField(
        label="Nama kampanye",
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Pengingat jadwal ngaji Desember"}),
    )
    template = forms.ModelChoiceField(
        label="Pakai template",
        queryset=MessageTemplate.objects.none(),
        required=False,
        empty_label="Tulis pesan sendiri",
        help_text="Bila dipilih dan isi pesan dikosongkan, isi template yang dipakai.",
    )
    body = forms.CharField(
        label="Isi pesan",
        required=False,
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 7}),
        help_text=(
            "Variabel: {nama}, {nama_depan}, {nomor}. Untuk grup WA, {nama} berisi nama grup."
        ),
    )
    send_to_all_contacts = forms.BooleanField(label="Kirim ke semua kontak saya", required=False)
    contact_groups = forms.ModelMultipleChoiceField(
        label="Grup kontak",
        queryset=ContactGroup.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    wa_groups = forms.MultipleChoiceField(
        label="Grup WhatsApp",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, owner, wa_groups=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.wa_group_map = {group["id"]: group for group in wa_groups}
        self.fields["template"].queryset = MessageTemplate.objects.filter(owner=owner)
        self.fields["contact_groups"].queryset = ContactGroup.objects.filter(owner=owner)
        self.fields["wa_groups"].choices = [(g["id"], g["name"]) for g in wa_groups]

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean(self):
        cleaned = super().clean()
        body = (cleaned.get("body") or "").strip()
        template = cleaned.get("template")
        if not body and template:
            body = template.body
        if not body:
            self.add_error("body", "Tulis isi pesan atau pilih template.")
        else:
            unknown = message_vars.unknown_variables(body)
            if unknown:
                self.add_error(
                    "body",
                    "Variabel tidak dikenal: " + ", ".join("{" + n + "}" for n in unknown),
                )
        cleaned["body"] = body

        if not (
            cleaned.get("send_to_all_contacts")
            or cleaned.get("contact_groups")
            or cleaned.get("wa_groups")
        ):
            raise ValidationError(
                "Pilih minimal satu tujuan: semua kontak, grup kontak, atau grup WA."
            )
        return cleaned

    def selected_wa_groups(self) -> list[dict]:
        return [self.wa_group_map[gid] for gid in self.cleaned_data.get("wa_groups", [])]
