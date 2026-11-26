from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.contacts.models import Contact, ContactGroup


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draf"
        QUEUED = "queued", "Dalam antrean"
        RUNNING = "running", "Sedang mengirim"
        COMPLETED = "completed", "Selesai"
        CANCELLED = "cancelled", "Dihentikan"
        FAILED = "failed", "Gagal dimulai"

    ACTIVE_STATUSES = (Status.QUEUED, Status.RUNNING)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campaigns"
    )
    name = models.CharField("nama kampanye", max_length=120)
    body = models.TextField("isi pesan", max_length=4000)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    send_to_all_contacts = models.BooleanField("semua kontak", default=False)
    contact_groups = models.ManyToManyField(
        ContactGroup, verbose_name="grup kontak", blank=True, related_name="campaigns"
    )
    skipped_opted_out = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "kampanye"
        verbose_name_plural = "kampanye"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("campaigns:detail", kwargs={"pk": self.pk})

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_finished(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.CANCELLED, self.Status.FAILED}


class CampaignRecipient(models.Model):
    class Kind(models.TextChoices):
        CONTACT = "contact", "Kontak"
        WA_GROUP = "wa_group", "Grup WhatsApp"

    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu"
        SENT = "sent", "Terkirim"
        FAILED = "failed", "Gagal"
        SKIPPED = "skipped", "Dilewati"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    chat_id = models.CharField(max_length=64)
    display_name = models.CharField(max_length=120, blank=True)
    text = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=300, blank=True)
    wa_message_id = models.CharField(max_length=120, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "penerima kampanye"
        verbose_name_plural = "penerima kampanye"
        indexes = [models.Index(fields=["campaign", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "chat_id"], name="unique_chat_per_campaign")
        ]

    def __str__(self):
        return f"{self.display_name or self.chat_id} ({self.get_status_display()})"
