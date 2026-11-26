from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email wajib diisi.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser harus is_staff dan is_superuser.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Pengguna situs. Login memakai email; member baru menunggu persetujuan admin."""

    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu persetujuan"
        ACTIVE = "active", "Aktif"
        REJECTED = "rejected", "Ditolak"
        SUSPENDED = "suspended", "Dinonaktifkan"

    username = None
    first_name = None
    last_name = None

    email = models.EmailField("email", unique=True)
    full_name = models.CharField("nama lengkap", max_length=120)
    whatsapp_number = models.CharField(
        "nomor WhatsApp",
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        help_text="Format 62xxxxxxxxxx.",
    )
    status = models.CharField(
        "status", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    status_changed_at = models.DateTimeField("status diubah", null=True, blank=True)
    status_changed_by = models.ForeignKey(
        "self",
        verbose_name="diubah oleh",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "pengguna"
        verbose_name_plural = "pengguna"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def is_approved_member(self) -> bool:
        return self.is_active and self.status == self.Status.ACTIVE

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING
