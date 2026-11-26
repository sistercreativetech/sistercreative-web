import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.portfolio.models import Category, Project, Tag
from apps.portfolio.services import parse_tag_names

PASSWORD = "Rahasia-Kuat-2026!"
MEDIA_ROOT = tempfile.mkdtemp()


def png(name="sampul.png"):
    buffer = BytesIO()
    Image.new("RGB", (32, 18), (109, 40, 217)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class DashboardTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@sistercreative.tech", password=PASSWORD, full_name="Admin Sister"
        )
        cls.pending = User.objects.create_user(
            email="rina@contoh.id",
            password=PASSWORD,
            full_name="Rina Wulandari",
            whatsapp_number="6281111111111",
        )
        cls.active = User.objects.create_user(
            email="dedi@contoh.id",
            password=PASSWORD,
            full_name="Dedi Kurniawan",
            whatsapp_number="6282222222222",
            status=User.Status.ACTIVE,
        )

    def setUp(self):
        self.client.force_login(self.admin)


class AccessTests(DashboardTestCase):
    urls = [
        ("dashboard:home", {}),
        ("dashboard:member_list", {}),
        ("dashboard:project_list", {}),
        ("dashboard:project_create", {}),
        ("dashboard:category_list", {}),
        ("dashboard:category_create", {}),
    ]

    def test_every_dashboard_page_blocks_members(self):
        self.client.force_login(self.active)
        for name, kwargs in self.urls:
            self.assertEqual(self.client.get(reverse(name, kwargs=kwargs)).status_code, 403, name)
        response = self.client.post(
            reverse("dashboard:member_status", args=[self.pending.pk]), {"status": "active"}
        )
        self.assertEqual(response.status_code, 403)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, User.Status.PENDING)

    def test_every_dashboard_page_redirects_guests(self):
        self.client.logout()
        for name, kwargs in self.urls:
            response = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("account_login"), response.url)

    def test_staff_can_open_every_page(self):
        for name, kwargs in self.urls:
            self.assertEqual(self.client.get(reverse(name, kwargs=kwargs)).status_code, 200, name)


class HomeTests(DashboardTestCase):
    def test_shows_pending_members_with_actions(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "Rina Wulandari")
        self.assertContains(response, reverse("dashboard:member_status", args=[self.pending.pk]))
        self.assertNotContains(response, "Dedi Kurniawan")

    def test_nav_marks_current_section_and_pending_badge(self):
        response = self.client.get(reverse("dashboard:member_list"))
        html = response.content.decode()
        self.assertIn('aria-current="page"', html)
        self.assertIn('1<span class="sr-only">menunggu persetujuan</span>', html)


class MemberManagementTests(DashboardTestCase):
    def status_url(self, user):
        return reverse("dashboard:member_status", args=[user.pk])

    def test_list_excludes_staff_and_filters(self):
        response = self.client.get(reverse("dashboard:member_list"))
        self.assertContains(response, "Rina Wulandari")
        self.assertContains(response, "Dedi Kurniawan")
        self.assertNotContains(response, "admin@sistercreative.tech")
        filtered = self.client.get(reverse("dashboard:member_list"), {"status": "active"})
        self.assertNotContains(filtered, "Rina Wulandari")
        by_phone = self.client.get(reverse("dashboard:member_list"), {"q": "0811-1111"})
        self.assertContains(by_phone, "Rina Wulandari")
        self.assertNotContains(by_phone, "Dedi Kurniawan")

    def test_approve_member(self):
        response = self.client.post(self.status_url(self.pending), {"status": "active"})
        self.assertRedirects(response, reverse("dashboard:member_detail", args=[self.pending.pk]))
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_approved_member)
        self.assertEqual(self.pending.status_changed_by, self.admin)

    def test_approve_from_list_returns_to_list(self):
        response = self.client.post(
            self.status_url(self.pending), {"status": "active", "next": "list"}
        )
        self.assertRedirects(response, reverse("dashboard:member_list"))

    def test_suspend_member_blocks_login(self):
        self.client.post(self.status_url(self.active), {"status": "suspended"})
        self.active.refresh_from_db()
        self.assertFalse(self.active.is_active)

    def test_invalid_status_is_rejected(self):
        self.client.post(self.status_url(self.pending), {"status": "superadmin"})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, User.Status.PENDING)

    def test_status_change_requires_post(self):
        self.assertEqual(self.client.get(self.status_url(self.pending)).status_code, 405)

    def test_cannot_change_staff_status(self):
        other_admin = User.objects.create_superuser(
            email="admin2@sistercreative.tech", password=PASSWORD, full_name="Admin Dua"
        )
        response = self.client.post(self.status_url(other_admin), {"status": "suspended"})
        self.assertEqual(response.status_code, 404)

    def test_update_quota(self):
        url = reverse("dashboard:member_detail", args=[self.active.pk])
        response = self.client.post(url, {"daily_message_quota": "250"})
        self.assertRedirects(response, url)
        self.active.refresh_from_db()
        self.assertEqual(self.active.daily_message_quota, 250)

    def test_quota_upper_limit(self):
        url = reverse("dashboard:member_detail", args=[self.active.pk])
        response = self.client.post(url, {"daily_message_quota": "99999"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-invalid="true"')
        self.active.refresh_from_db()
        self.assertEqual(self.active.daily_message_quota, 100)


class TagParsingTests(TestCase):
    def test_parse_tag_names(self):
        self.assertEqual(
            parse_tag_names(" n8n,  Google   Sheets ,N8N,, WhatsApp "),
            ["n8n", "Google Sheets", "WhatsApp"],
        )


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ProjectManagementTests(DashboardTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.category = Category.objects.create(name="Landing Page")

    def payload(self, **overrides):
        data = {
            "title": "Landing Page Katering Bu Ani",
            "category": self.category.pk,
            "summary": "Landing page pemesanan katering harian dengan tombol WhatsApp.",
            "description": "",
            "client_name": "Katering Bu Ani",
            "year": "2026",
            "cover_alt": "",
            "project_url": "",
            "is_published": "on",
            "order": "1",
            "tags_text": "Django, WhatsApp",
        }
        data.update(overrides)
        return data

    def test_create_project_with_tags(self):
        response = self.client.post(reverse("dashboard:project_create"), self.payload())
        self.assertRedirects(response, reverse("dashboard:project_list"))
        project = Project.objects.get(title="Landing Page Katering Bu Ani")
        self.assertTrue(project.is_published)
        self.assertEqual(
            sorted(project.tags.values_list("name", flat=True)), ["Django", "WhatsApp"]
        )
        self.assertEqual(self.client.get(project.get_absolute_url()).status_code, 200)

    def test_existing_tag_is_reused(self):
        Tag.objects.create(name="WhatsApp")
        self.client.post(reverse("dashboard:project_create"), self.payload())
        self.assertEqual(Tag.objects.filter(slug="whatsapp").count(), 1)

    def test_image_requires_alt(self):
        response = self.client.post(
            reverse("dashboard:project_create"), self.payload(cover_image=png())
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wajib diisi bila ada gambar sampul")

    def test_rejects_fake_image(self):
        fake = SimpleUploadedFile("sampul.png", b"bukan gambar", content_type="image/png")
        response = self.client.post(
            reverse("dashboard:project_create"),
            self.payload(cover_image=fake, cover_alt="Sampul"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(title="Landing Page Katering Bu Ani").exists())

    def test_update_replaces_image_and_removes_old_file(self):
        self.client.post(
            reverse("dashboard:project_create"),
            self.payload(cover_image=png("lama.png"), cover_alt="Tampilan lama"),
        )
        project = Project.objects.get(title="Landing Page Katering Bu Ani")
        old_path = Path(project.cover_image.path)
        self.assertTrue(old_path.exists())
        response = self.client.post(
            reverse("dashboard:project_update", args=[project.pk]),
            self.payload(cover_image=png("baru.png"), cover_alt="Tampilan baru", tags_text=""),
        )
        self.assertRedirects(response, reverse("dashboard:project_list"))
        project.refresh_from_db()
        self.assertFalse(old_path.exists())
        self.assertIn("baru", project.cover_image.name)
        self.assertEqual(project.tags.count(), 0)

    def test_edit_form_prefills_tags(self):
        self.client.post(reverse("dashboard:project_create"), self.payload())
        project = Project.objects.get(title="Landing Page Katering Bu Ani")
        response = self.client.get(reverse("dashboard:project_update", args=[project.pk]))
        self.assertContains(response, 'value="Django, WhatsApp"')

    def test_list_shows_drafts_and_filters(self):
        Project.objects.create(title="Draf Rahasia", category=self.category, summary="x")
        response = self.client.get(reverse("dashboard:project_list"))
        self.assertContains(response, "Draf Rahasia")
        published = self.client.get(reverse("dashboard:project_list"), {"is_published": "1"})
        self.assertNotContains(published, "Draf Rahasia")

    def test_delete_project(self):
        project = Project.objects.create(title="Hapus Saya", category=self.category, summary="x")
        url = reverse("dashboard:project_delete", args=[project.pk])
        self.assertContains(self.client.get(url), "Hapus proyek “Hapus Saya”?")
        self.assertRedirects(self.client.post(url), reverse("dashboard:project_list"))
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())


class CategoryManagementTests(DashboardTestCase):
    def test_create_and_rename_keeps_slug(self):
        self.client.post(reverse("dashboard:category_create"), {"name": "Bot Telegram", "order": 2})
        category = Category.objects.get(name="Bot Telegram")
        self.client.post(
            reverse("dashboard:category_update", args=[category.pk]),
            {"name": "Bot Telegram & WhatsApp", "order": 2},
        )
        category.refresh_from_db()
        self.assertEqual(category.name, "Bot Telegram & WhatsApp")
        self.assertEqual(category.slug, "bot-telegram")

    def test_duplicate_name_rejected(self):
        Category.objects.create(name="Website")
        response = self.client.post(
            reverse("dashboard:category_create"), {"name": "Website", "order": 0}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Category.objects.filter(name="Website").count(), 1)

    def test_cannot_delete_category_in_use(self):
        category = Category.objects.create(name="Dipakai")
        Project.objects.create(title="Proyek A", category=category, summary="x")
        response = self.client.post(reverse("dashboard:category_delete", args=[category.pk]))
        self.assertRedirects(response, reverse("dashboard:category_list"))
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_delete_unused_category(self):
        category = Category.objects.create(name="Kosong")
        self.client.post(reverse("dashboard:category_delete", args=[category.pk]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())
