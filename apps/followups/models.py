import uuid
from datetime import time, timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.contacts.models import Contact


def followup_image_path(instance, filename: str) -> str:
    # Nama acak tak tertebak; tidak memuat id member atau nama file asli.
    return f"followups/{uuid.uuid4().hex}.jpg"


class FollowUpSequence(models.Model):
    class Trigger(models.TextChoices):
        ANY_CHAT = "any_chat", "Setiap chat pribadi yang masuk"
        KEYWORD = "keyword", "Chat yang mengandung kata kunci"
        MANUAL = "manual", "Hanya didaftarkan manual"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="followup_sequences"
    )
    name = models.CharField("nama urutan", max_length=80)
    trigger = models.CharField(
        "pemicu", max_length=10, choices=Trigger.choices, default=Trigger.KEYWORD
    )
    keywords = models.CharField(
        "kata kunci",
        max_length=300,
        blank=True,
        help_text="Untuk pemicu kata kunci. Pisahkan dengan koma, contoh: harga, daftar, info.",
    )
    stop_on_reply = models.BooleanField(
        "berhenti bila customer membalas",
        default=True,
        help_text="Follow-up berikutnya batal bila customer membalas setelah follow-up terkirim.",
    )
    is_active = models.BooleanField("aktif", default=True)
    send_from = models.TimeField("kirim mulai", default=time(8))
    send_until = models.TimeField("kirim sampai", default=time(20))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "urutan follow-up"
        verbose_name_plural = "urutan follow-up"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("followups:sequence_detail", kwargs={"pk": self.pk})

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip() for k in self.keywords.split(",") if k.strip()]


class FollowUpStep(models.Model):
    class Unit(models.TextChoices):
        HOURS = "hours", "jam"
        DAYS = "days", "hari"

    UNIT_MINUTES = {Unit.HOURS: 60, Unit.DAYS: 60 * 24}

    sequence = models.ForeignKey(FollowUpSequence, on_delete=models.CASCADE, related_name="steps")
    delay_value = models.PositiveSmallIntegerField("dikirim setelah")
    delay_unit = models.CharField("satuan", max_length=5, choices=Unit.choices, default=Unit.DAYS)
    # Diisi otomatis dari delay_value × satuan; dipakai untuk urutan & jadwal.
    delay_minutes = models.PositiveIntegerField(editable=False, db_index=True)
    body = models.TextField("isi pesan", max_length=4000)
    image = models.ImageField("gambar", upload_to=followup_image_path, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["delay_minutes", "pk"]
        verbose_name = "langkah follow-up"
        verbose_name_plural = "langkah follow-up"

    def __str__(self):
        return f"{self.sequence}: {self.delay_label}"

    def save(self, *args, **kwargs):
        self.delay_minutes = self.delay_value * self.UNIT_MINUTES[self.delay_unit]
        super().save(*args, **kwargs)

    @property
    def delay(self) -> timedelta:
        return timedelta(minutes=self.delay_minutes)

    @property
    def delay_label(self) -> str:
        return f"{self.delay_value} {self.get_delay_unit_display()}"


class FollowUpEnrollment(models.Model):
    """Satu chat yang sedang/pernah mengikuti satu urutan follow-up."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Berjalan"
        COMPLETED = "completed", "Selesai"
        STOPPED = "stopped", "Dihentikan"

    class StopReason(models.TextChoices):
        REPLIED = "replied", "Customer membalas"
        OPTED_OUT = "opted_out", "Membalas STOP"
        MANUAL = "manual", "Dihentikan manual"

    sequence = models.ForeignKey(
        FollowUpSequence, on_delete=models.CASCADE, related_name="enrollments"
    )
    chat_id = models.CharField(max_length=64)
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    display_name = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    stop_reason = models.CharField(max_length=10, choices=StopReason.choices, blank=True)
    enrolled_at = models.DateTimeField(default=timezone.now)
    next_step = models.ForeignKey(
        FollowUpStep, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    next_due_at = models.DateTimeField(null=True, blank=True)
    # Jeda (menit) langkah terakhir yang sudah diantrekan; langkah berikutnya harus lebih besar.
    progress_minutes = models.PositiveIntegerField(default=0)
    last_step_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-enrolled_at", "-pk"]
        verbose_name = "peserta follow-up"
        verbose_name_plural = "peserta follow-up"
        constraints = [
            models.UniqueConstraint(fields=["sequence", "chat_id"], name="unique_chat_per_sequence")
        ]
        indexes = [models.Index(fields=["status", "next_due_at"])]

    def __str__(self):
        return self.display_name or self.phone_label

    @property
    def phone_label(self) -> str:
        number = self.chat_id.split("@")[0]
        return f"+{number}" if self.chat_id.endswith("@c.us") else number


class FollowUpMessage(models.Model):
    """Pesan follow-up yang dikirim ke n8n. Tetap disimpan agar dihitung kuota harian."""

    class Status(models.TextChoices):
        PENDING = "pending", "Dalam antrean"
        SENT = "sent", "Terkirim"
        FAILED = "failed", "Gagal"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    enrollment = models.ForeignKey(
        FollowUpEnrollment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messages",
    )
    step = models.ForeignKey(
        FollowUpStep, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    chat_id = models.CharField(max_length=64)
    text = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=300, blank=True)
    wa_message_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "pesan follow-up"
        verbose_name_plural = "pesan follow-up"
        indexes = [models.Index(fields=["owner", "status", "created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "step"], name="unique_step_per_enrollment"
            )
        ]

    def __str__(self):
        return f"{self.chat_id} ({self.get_status_display()})"
