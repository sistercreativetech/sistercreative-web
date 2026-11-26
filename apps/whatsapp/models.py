from django.conf import settings
from django.db import models


class WhatsAppSession(models.Model):
    """Satu sesi WAHA per member. Nama sesi tetap: member-<id user>."""

    class Status(models.TextChoices):
        NOT_CREATED = "NOT_CREATED", "Belum dihubungkan"
        STOPPED = "STOPPED", "Berhenti"
        STARTING = "STARTING", "Menyiapkan"
        SCAN_QR_CODE = "SCAN_QR_CODE", "Menunggu scan QR"
        WORKING = "WORKING", "Terhubung"
        FAILED = "FAILED", "Gagal"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="whatsapp_session"
    )
    name = models.CharField("nama sesi WAHA", max_length=64, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_CREATED, db_index=True
    )
    connected_number = models.CharField("nomor terhubung", max_length=20, blank=True)
    connected_name = models.CharField("nama profil", max_length=120, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "sesi WhatsApp"
        verbose_name_plural = "sesi WhatsApp"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @staticmethod
    def name_for(user) -> str:
        return f"member-{user.pk}"

    @property
    def is_connected(self) -> bool:
        return self.status == self.Status.WORKING
