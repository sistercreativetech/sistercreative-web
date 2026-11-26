from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.urls import reverse


class AutoReplyRule(models.Model):
    class MatchType(models.TextChoices):
        CONTAINS = "contains", "Mengandung kata"
        EXACT = "exact", "Sama persis"
        STARTS_WITH = "starts_with", "Diawali dengan"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auto_reply_rules"
    )
    name = models.CharField("nama aturan", max_length=80)
    keywords = models.CharField(
        "kata kunci",
        max_length=300,
        help_text="Pisahkan dengan koma, contoh: harga, price, berapa.",
    )
    match_type = models.CharField(
        "cara cocok", max_length=12, choices=MatchType.choices, default=MatchType.CONTAINS
    )
    reply = models.TextField(
        "isi balasan",
        max_length=2000,
        help_text="Boleh memakai {nama} dan {nama_depan} untuk kontak yang tersimpan.",
    )
    is_active = models.BooleanField("aktif", default=True)
    priority = models.PositiveSmallIntegerField(
        "urutan", default=10, help_text="Angka kecil diperiksa lebih dulu."
    )
    cooldown_minutes = models.PositiveSmallIntegerField(
        "jeda ulang (menit)",
        default=60,
        validators=[MaxValueValidator(1440)],
        help_text="Aturan ini tidak membalas chat yang sama lagi sebelum jeda ini lewat.",
    )
    active_from = models.TimeField("aktif mulai", null=True, blank=True)
    active_until = models.TimeField("aktif sampai", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "pk"]
        verbose_name = "aturan balas otomatis"
        verbose_name_plural = "aturan balas otomatis"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("autoreply:rule_update", kwargs={"pk": self.pk})

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip() for k in self.keywords.split(",") if k.strip()]


class AutoReplyLog(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Dikirim ke antrean"
        FAILED = "failed", "Gagal diteruskan"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auto_reply_logs"
    )
    rule = models.ForeignKey(
        AutoReplyRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs"
    )
    chat_id = models.CharField(max_length=64)
    message_id = models.CharField(max_length=160, unique=True)
    incoming_text = models.CharField(max_length=500)
    reply_text = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "riwayat balas otomatis"
        verbose_name_plural = "riwayat balas otomatis"
        indexes = [
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["rule", "chat_id", "created_at"]),
        ]

    def __str__(self):
        return f"{self.chat_id}: {self.incoming_text[:30]}"
