import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class MailingList(models.Model):
    """Kelompok pelanggan email, misalnya pendaftar satu program."""

    name = models.CharField("nama daftar", max_length=80, unique=True)
    description = models.CharField("keterangan", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "daftar email"
        verbose_name_plural = "daftar email"

    def __str__(self):
        return self.name


class Subscriber(models.Model):
    class Status(models.TextChoices):
        SUBSCRIBED = "subscribed", "Berlangganan"
        UNSUBSCRIBED = "unsubscribed", "Berhenti"

    email = models.EmailField("email", unique=True)
    name = models.CharField("nama", max_length=120, blank=True)
    lists = models.ManyToManyField(
        MailingList, verbose_name="daftar", blank=True, related_name="subscribers"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.SUBSCRIBED, db_index=True
    )
    # Dipakai di link berhenti langganan; tidak bisa ditebak dari email.
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source = models.CharField("sumber", max_length=60, blank=True)
    last_emailed_at = models.DateTimeField("terakhir dikirimi", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "pelanggan email"
        verbose_name_plural = "pelanggan email"

    def __str__(self):
        return self.name or self.email

    @property
    def is_subscribed(self) -> bool:
        return self.status == self.Status.SUBSCRIBED

    def get_unsubscribe_url(self) -> str:
        return reverse("mailing_unsubscribe", kwargs={"token": self.token})


class EmailCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draf"
        SENDING = "sending", "Sedang mengirim"
        COMPLETED = "completed", "Selesai"
        CANCELLED = "cancelled", "Dihentikan"

    name = models.CharField("nama kampanye", max_length=120)
    subject = models.CharField(
        "subjek", max_length=150, help_text="Bisa memakai {nama} atau {nama_depan}."
    )
    body = models.TextField(
        "isi email",
        max_length=10000,
        help_text=(
            "Tulis seperti biasa. Baris kosong memisahkan paragraf, link otomatis bisa diklik. "
            "Bisa memakai {nama} atau {nama_depan}."
        ),
    )
    button_label = models.CharField("teks tombol", max_length=60, blank=True)
    button_url = models.URLField("link tombol", blank=True)
    send_to_all = models.BooleanField("semua pelanggan", default=False)
    lists = models.ManyToManyField(
        MailingList, verbose_name="daftar", blank=True, related_name="campaigns"
    )
    skip_recent_days = models.PositiveSmallIntegerField(
        "lewati yang baru dikirimi (hari)",
        default=0,
        help_text="0 = kirim ke semua. Contoh 7: lewati yang menerima email 7 hari terakhir.",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "kampanye email"
        verbose_name_plural = "kampanye email"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("mailing:campaign_detail", kwargs={"pk": self.pk})

    @property
    def is_draft(self) -> bool:
        return self.status == self.Status.DRAFT

    @property
    def is_sending(self) -> bool:
        return self.status == self.Status.SENDING


class EmailRecipient(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu"
        QUEUED = "queued", "Dikirim ke n8n"
        SENT = "sent", "Terkirim"
        FAILED = "failed", "Gagal"
        SKIPPED = "skipped", "Dilewati"

    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name="recipients")
    subscriber = models.ForeignKey(
        Subscriber, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    email = models.EmailField()
    name = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=300, blank=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "penerima email"
        verbose_name_plural = "penerima email"
        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["status", "sent_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "email"], name="unique_email_per_campaign")
        ]

    def __str__(self):
        return f"{self.email} ({self.get_status_display()})"
