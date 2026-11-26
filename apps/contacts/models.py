from django.conf import settings
from django.db import models


class ContactGroup(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_groups"
    )
    name = models.CharField("nama grup", max_length=80)
    description = models.CharField("keterangan", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "grup kontak"
        verbose_name_plural = "grup kontak"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_group_name_per_owner")
        ]

    def __str__(self):
        return self.name


class Contact(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField("nama", max_length=120, blank=True)
    phone = models.CharField("nomor WhatsApp", max_length=15, help_text="Format 62xxxxxxxxxx.")
    groups = models.ManyToManyField(
        ContactGroup, verbose_name="grup", blank=True, related_name="contacts"
    )
    is_opted_out = models.BooleanField(
        "berhenti berlangganan",
        default=False,
        help_text="Kontak yang membalas STOP tidak akan dikirimi pesan.",
    )
    opted_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "phone"]
        verbose_name = "kontak"
        verbose_name_plural = "kontak"
        constraints = [
            models.UniqueConstraint(fields=["owner", "phone"], name="unique_phone_per_owner")
        ]

    def __str__(self):
        return self.name or f"+{self.phone}"

    @property
    def first_name(self) -> str:
        return self.name.split(" ")[0] if self.name else ""


class MessageTemplate(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="message_templates"
    )
    name = models.CharField("nama template", max_length=80)
    body = models.TextField(
        "isi pesan",
        max_length=4000,
        help_text="Gunakan {nama} atau {nama_depan} untuk menyapa kontak secara personal.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "template pesan"
        verbose_name_plural = "template pesan"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_template_name_per_owner")
        ]

    def __str__(self):
        return self.name
