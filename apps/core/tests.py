import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .icons import ICONS

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"


class HealthViewTests(TestCase):
    def test_health_returns_ok(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})


class SettingsTests(SimpleTestCase):
    def test_locale_is_indonesian(self):
        self.assertEqual(settings.LANGUAGE_CODE, "id")
        self.assertEqual(settings.TIME_ZONE, "Asia/Makassar")

    def test_admin_is_not_on_default_path(self):
        self.assertNotEqual(settings.ADMIN_URL.strip("/"), "admin")


class BaseTemplateTests(SimpleTestCase):
    def test_base_template_renders_essentials(self):
        html = render_to_string("base.html", request=RequestFactory().get("/"))
        self.assertIn('lang="id"', html)
        self.assertIn("Sister Creative", html)
        self.assertIn("css/app.css", html)
        self.assertIn("js/app.js", html)
        self.assertIn('href="#konten"', html)

    def test_pinned_motion_bundle_exists(self):
        self.assertTrue((Path(settings.BASE_DIR) / "static/vendor/motion-14.14.0.js").exists())


class HomeViewTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("core:home"))
        self.html = self.response.content.decode()

    def test_renders_home_template(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertTemplateUsed(self.response, "pages/home.html")

    def test_has_all_sections(self):
        for section_id in ["layanan", "portofolio", "proses", "kontak"]:
            self.assertIn(f'id="{section_id}"', self.html)

    def test_has_single_h1(self):
        self.assertEqual(self.html.count("<h1"), 1)

    def test_lists_services_and_process(self):
        self.assertIn("Website &amp; Landing Page", self.html)
        self.assertIn("Bot WhatsApp &amp; Telegram", self.html)
        self.assertIn("Serah terima", self.html)

    def test_mobile_menu_is_accessible(self):
        self.assertIn('aria-controls="main-nav"', self.html)
        self.assertIn('aria-expanded="false"', self.html)
        self.assertIn('id="main-nav"', self.html)

    @override_settings(CONTACT_WHATSAPP="6281234567890")
    def test_whatsapp_links_use_configured_number(self):
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("https://wa.me/6281234567890?text=Halo%20Sister%20Creative", html)
        self.assertNotIn("6285737086612", html)

    def test_external_links_are_safe(self):
        for tag in re.findall(r"<a[^>]+target=\"_blank\"[^>]*>", self.html):
            self.assertIn('rel="noopener noreferrer"', tag)

    def test_all_images_have_alt(self):
        for tag in re.findall(r"<img\b[^>]*>", self.html):
            self.assertIn("alt=", tag)


class IconTests(SimpleTestCase):
    def test_every_listed_icon_has_partial(self):
        for name in ICONS:
            self.assertTrue(
                (TEMPLATES_DIR / "components/icons" / f"{name}.html").exists(),
                f"Ikon {name} belum disinkron; jalankan `manage.py sync_icons`.",
            )

    def test_icon_is_decorative_by_default(self):
        html = render_to_string("components/icon.html", {"name": "check", "class": "size-4"})
        self.assertIn('aria-hidden="true"', html)
        self.assertIn("size-4", html)
        self.assertIn("<path", html)

    def test_icon_with_label_is_announced(self):
        html = render_to_string("components/icon.html", {"name": "check", "icon_label": "Selesai"})
        self.assertIn('role="img"', html)
        self.assertIn('aria-label="Selesai"', html)
        self.assertNotIn("aria-hidden", html)

    def test_outer_label_does_not_leak_into_icon(self):
        html = render_to_string(
            "components/app_nav_link.html",
            {"url": "/x/", "label": "Kontak", "icon": "users", "active": True},
        )
        self.assertIn('aria-hidden="true"', html)
        self.assertNotIn('aria-label="Kontak"', html)

    def test_sync_icons_command(self):
        out = StringIO()
        call_command("sync_icons", stdout=out)
        self.assertIn(f"{len(ICONS)} ikon disalin", out.getvalue())


class TemplateConventionTests(SimpleTestCase):
    """Menegakkan aturan CLAUDE.md di semua template."""

    def templates(self):
        return [p for p in TEMPLATES_DIR.rglob("*.html") if "icons" not in p.parts]

    def test_no_inline_style(self):
        for path in self.templates():
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"\sstyle=", path.name)

    def test_no_script_outside_base(self):
        for path in self.templates():
            if path.name == "base.html":
                continue
            self.assertNotIn("<script", path.read_text(encoding="utf-8"), path.name)

    def test_no_arbitrary_hex_colors(self):
        for path in self.templates():
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"\[#[0-9a-fA-F]", path.name)

    def test_no_lorem_ipsum(self):
        for path in self.templates():
            self.assertNotIn("lorem", path.read_text(encoding="utf-8").lower(), path.name)

    def test_no_safe_filter(self):
        for path in self.templates():
            self.assertNotIn("|safe", path.read_text(encoding="utf-8"), path.name)
