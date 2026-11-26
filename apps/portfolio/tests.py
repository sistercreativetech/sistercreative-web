import shutil
import tempfile
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.core.validators import validate_image_upload

from . import selectors
from .models import Category, Project, Tag

MEDIA_ROOT = tempfile.mkdtemp()


def make_image(fmt="PNG", size=(32, 18), name="sampul.png"):
    buffer = BytesIO()
    Image.new("RGB", size, (109, 40, 217)).save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class PortfolioDataMixin:
    @classmethod
    def setUpTestData(cls):
        # Data migration sudah menanam 3 proyek; mulai dari kondisi bersih.
        Project.objects.all().delete()
        cls.web = Category.objects.create(name="Website Sekolah")
        cls.bot = Category.objects.create(name="Bot WhatsApp")
        cls.tag_n8n = Tag.objects.create(name="n8n Workflow")
        cls.tag_django = Tag.objects.create(name="Django")
        cls.school = Project.objects.create(
            title="Website Profil SD Islam Al Falah",
            category=cls.web,
            summary="Website profil sekolah dengan info PPDB dan galeri kegiatan.",
            description="Paragraf pertama.\n\nParagraf kedua.",
            client_name="SD Islam Al Falah",
            year=2026,
            is_published=True,
            is_featured=True,
            order=1,
        )
        cls.school.tags.add(cls.tag_django)
        cls.reminder = Project.objects.create(
            title="Bot Pengingat Jadwal Ngaji",
            category=cls.bot,
            summary="Pengingat jadwal otomatis untuk wali murid lewat WhatsApp.",
            is_published=True,
            order=2,
        )
        cls.reminder.tags.add(cls.tag_n8n)
        cls.draft = Project.objects.create(
            title="Draft Aplikasi Kasir Warung",
            category=cls.web,
            summary="Belum siap ditampilkan.",
            is_published=False,
            is_featured=True,
        )


class SeedMigrationTests(TestCase):
    def test_legacy_projects_are_seeded_and_featured(self):
        titles = set(selectors.featured_projects().values_list("title", flat=True))
        self.assertEqual(
            titles,
            {"Admin Ngaji Privat Lombok", "Bot Laporan Pembayaran", "Input Data Otomatis"},
        )


class ModelTests(PortfolioDataMixin, TestCase):
    def test_slug_is_generated_and_unique(self):
        self.assertEqual(self.school.slug, "website-profil-sd-islam-al-falah")
        twin = Project.objects.create(
            title="Website Profil SD Islam Al Falah", category=self.web, summary="Duplikat."
        )
        self.assertEqual(twin.slug, "website-profil-sd-islam-al-falah-2")

    def test_category_and_tag_slugs(self):
        self.assertEqual(self.web.slug, "website-sekolah")
        self.assertEqual(self.tag_n8n.slug, "n8n-workflow")

    def test_absolute_url(self):
        self.assertEqual(
            self.school.get_absolute_url(), "/portofolio/website-profil-sd-islam-al-falah/"
        )

    @override_settings(MEDIA_ROOT=MEDIA_ROOT)
    def test_cover_alt_required_when_image_present(self):
        project = Project(
            title="Landing Page Katering",
            category=self.web,
            summary="Landing page pemesanan katering harian.",
            cover_image=make_image(),
        )
        with self.assertRaises(ValidationError) as ctx:
            project.full_clean()
        self.assertIn("cover_alt", ctx.exception.message_dict)


class ImageValidatorTests(TestCase):
    def test_accepts_png_jpeg_webp(self):
        for fmt, name in [("PNG", "a.png"), ("JPEG", "a.jpg"), ("WEBP", "a.webp")]:
            validate_image_upload(make_image(fmt, name=name))

    @override_settings(MAX_IMAGE_UPLOAD_BYTES=100)
    def test_rejects_large_file(self):
        with self.assertRaisesMessage(ValidationError, "Ukuran gambar maksimal"):
            validate_image_upload(make_image(size=(400, 400)))

    def test_rejects_non_image_with_image_extension(self):
        fake = SimpleUploadedFile("virus.png", b"<?php echo 'x'; ?>", content_type="image/png")
        with self.assertRaisesMessage(ValidationError, "bukan gambar"):
            validate_image_upload(fake)

    def test_rejects_disallowed_format(self):
        with self.assertRaisesMessage(ValidationError, "JPG, PNG, atau WebP"):
            validate_image_upload(make_image("GIF", name="anim.gif"))


class SelectorTests(PortfolioDataMixin, TestCase):
    def test_published_excludes_drafts(self):
        self.assertNotIn(self.draft, selectors.published_projects())

    def test_featured_only_published_and_featured(self):
        self.assertEqual(list(selectors.featured_projects()), [self.school])

    def test_related_projects_same_category(self):
        other = Project.objects.create(
            title="Website PPDB Online", category=self.web, summary="PPDB.", is_published=True
        )
        self.assertEqual(list(selectors.related_projects(self.school)), [other])

    def test_categories_only_with_published_projects(self):
        empty = Category.objects.create(name="Desain Grafis")
        categories = list(selectors.categories_with_projects())
        self.assertIn(self.web, categories)
        self.assertNotIn(empty, categories)


class ProjectListViewTests(PortfolioDataMixin, TestCase):
    url = reverse("portfolio:list")

    def test_lists_published_only(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pages/portfolio/list.html")
        self.assertContains(response, self.school.title)
        self.assertContains(response, self.reminder.title)
        self.assertNotContains(response, self.draft.title)
        self.assertContains(response, "2 proyek")

    def test_filter_by_category(self):
        response = self.client.get(self.url, {"category": self.bot.slug})
        self.assertContains(response, self.reminder.title)
        self.assertNotContains(response, self.school.title)

    def test_filter_by_tag(self):
        response = self.client.get(self.url, {"tag": self.tag_django.slug})
        self.assertContains(response, self.school.title)
        self.assertNotContains(response, self.reminder.title)

    def test_search(self):
        response = self.client.get(self.url, {"q": "pengingat"})
        self.assertContains(response, self.reminder.title)
        self.assertNotContains(response, self.school.title)

    def test_unknown_category_shows_empty_state(self):
        response = self.client.get(self.url, {"category": "tidak-ada"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Belum ada proyek yang cocok")

    def test_search_input_is_escaped(self):
        response = self.client.get(self.url, {"q": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_pagination_keeps_filters(self):
        for i in range(10):
            Project.objects.create(
                title=f"Website Sekolah Cabang {i}",
                category=self.web,
                summary="Website cabang sekolah.",
                is_published=True,
            )
        response = self.client.get(self.url, {"category": self.web.slug})
        self.assertContains(response, "Halaman 1 dari 2")
        self.assertContains(response, f"?category={self.web.slug}&amp;page=2")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ProjectDetailViewTests(PortfolioDataMixin, TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_shows_published_project(self):
        response = self.client.get(self.school.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1", count=1)
        self.assertContains(response, "SD Islam Al Falah")
        self.assertContains(response, "<p>Paragraf pertama.</p>", html=True)
        self.assertContains(response, "wa.me/")

    def test_draft_returns_404(self):
        response = self.client.get(self.draft.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_cover_image_has_alt(self):
        self.school.cover_image = make_image()
        self.school.cover_alt = "Tampilan beranda website SD Islam Al Falah di ponsel"
        self.school.save()
        response = self.client.get(self.school.get_absolute_url())
        self.assertContains(response, 'alt="Tampilan beranda website SD Islam Al Falah di ponsel"')


class HomeFeaturedTests(PortfolioDataMixin, TestCase):
    def test_home_shows_featured_published_projects(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, self.school.title)
        self.assertNotContains(response, self.draft.title)
        self.assertContains(response, reverse("portfolio:list"))
