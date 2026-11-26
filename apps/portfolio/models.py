from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from apps.core.validators import ALLOWED_IMAGE_EXTENSIONS, validate_image_upload


def unique_slug(instance, value, max_length=60):
    """Slug unik per model; tambahkan -2, -3, ... bila sudah dipakai."""
    base = slugify(value)[:max_length].strip("-") or "item"
    slug, counter = base, 2
    queryset = type(instance).objects.exclude(pk=instance.pk)
    while queryset.filter(slug=slug).exists():
        suffix = f"-{counter}"
        slug = f"{base[: max_length - len(suffix)]}{suffix}"
        counter += 1
    return slug


class Category(models.Model):
    name = models.CharField("nama", max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)
    order = models.PositiveSmallIntegerField("urutan", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "kategori"
        verbose_name_plural = "kategori"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Tag(models.Model):
    name = models.CharField("nama", max_length=40, unique=True)
    slug = models.SlugField(max_length=40, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "tag"
        verbose_name_plural = "tag"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name, max_length=40)
        super().save(*args, **kwargs)


class Project(models.Model):
    title = models.CharField("judul", max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    category = models.ForeignKey(
        Category,
        verbose_name="kategori",
        on_delete=models.PROTECT,
        related_name="projects",
    )
    tags = models.ManyToManyField(Tag, verbose_name="tag", blank=True, related_name="projects")
    summary = models.CharField(
        "ringkasan", max_length=280, help_text="Satu-dua kalimat untuk kartu portofolio."
    )
    description = models.TextField(
        "deskripsi", blank=True, help_text="Cerita lengkap: masalah, solusi, dan hasil."
    )
    client_name = models.CharField("nama klien", max_length=120, blank=True)
    year = models.PositiveSmallIntegerField("tahun", null=True, blank=True)
    cover_image = models.ImageField(
        "gambar sampul",
        upload_to="portfolio/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS),
            validate_image_upload,
        ],
        help_text="JPG, PNG, atau WebP, maksimal 2 MB. Rasio 16:9 disarankan.",
    )
    cover_alt = models.CharField(
        "teks alternatif gambar",
        max_length=160,
        blank=True,
        help_text="Jelaskan isi gambar untuk pembaca layar.",
    )
    project_url = models.URLField("tautan proyek", blank=True)
    is_published = models.BooleanField("terbit", default=False)
    is_featured = models.BooleanField("tampil di beranda", default=False)
    order = models.PositiveSmallIntegerField("urutan", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "proyek"
        verbose_name_plural = "proyek"
        indexes = [models.Index(fields=["is_published", "order"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title, max_length=140)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("portfolio:detail", kwargs={"slug": self.slug})

    def clean(self):
        if self.cover_image and not self.cover_alt.strip():
            raise ValidationError({"cover_alt": "Wajib diisi bila ada gambar sampul."})
