from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.phone import normalize_whatsapp

from . import services
from .models import User

PASSWORD = "Rahasia-Kuat-2026!"


def make_member(email="aminah@contoh.id", status=User.Status.PENDING, **extra):
    extra.setdefault("full_name", "Siti Aminah")
    user = User.objects.create_user(email=email, password=PASSWORD, status=status, **extra)
    return user


def make_admin(email="admin@sistercreative.tech"):
    return User.objects.create_superuser(email=email, password=PASSWORD, full_name="Admin Sister")


class PhoneNormalizationTests(SimpleTestCase):
    def test_accepts_common_formats(self):
        for raw in ["0812-3456-7890", "+62 812 3456 7890", "6281234567890", "812 3456 7890"]:
            self.assertEqual(normalize_whatsapp(raw), "6281234567890", raw)

    def test_rejects_invalid_numbers(self):
        for raw in ["", "12345", "021-555-1234", "0812", "+1 415 555 0100", "08" + "1" * 20]:
            with self.assertRaises(ValidationError, msg=raw):
                normalize_whatsapp(raw)


class UserModelTests(TestCase):
    def test_new_member_is_pending_and_can_login(self):
        user = make_member()
        self.assertEqual(user.status, User.Status.PENDING)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_approved_member)

    def test_superuser_is_active_staff(self):
        admin = make_admin()
        self.assertTrue(admin.is_staff)
        self.assertEqual(admin.status, User.Status.ACTIVE)

    def test_short_name(self):
        self.assertEqual(make_member().get_short_name(), "Siti")


class MemberStatusServiceTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.member = make_member()

    def test_approve(self):
        services.approve_member(self.member, by=self.admin)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_approved_member)
        self.assertEqual(self.member.status_changed_by, self.admin)
        self.assertIsNotNone(self.member.status_changed_at)

    def test_reject_and_suspend_deactivate_account(self):
        for func in (services.reject_member, services.suspend_member):
            func(self.member, by=self.admin)
            self.member.refresh_from_db()
            self.assertFalse(self.member.is_active)

    def test_reapprove_reactivates(self):
        services.suspend_member(self.member, by=self.admin)
        services.approve_member(self.member, by=self.admin)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_unknown_status_raises(self):
        with self.assertRaises(ValueError):
            services.set_member_status(self.member, "banned")


class SignupTests(TestCase):
    url = reverse("account_signup")

    def payload(self, **overrides):
        data = {
            "full_name": "  Budi   Santoso ",
            "email": "budi@contoh.id",
            "whatsapp_number": "0812-3456-7890",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return data

    def test_page_renders_with_labels(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/signup.html")
        for label in ["Nama lengkap", "Nomor WhatsApp"]:
            self.assertContains(response, label)
        self.assertContains(response, "ditinjau admin")

    def test_signup_creates_pending_member_and_redirects_to_pending_page(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("members:home"), target_status_code=302)
        user = User.objects.get(email="budi@contoh.id")
        self.assertEqual(user.full_name, "Budi Santoso")
        self.assertEqual(user.whatsapp_number, "6281234567890")
        self.assertEqual(user.status, User.Status.PENDING)
        self.assertFalse(user.is_staff)
        follow = self.client.get(reverse("members:home"))
        self.assertRedirects(follow, reverse("members:pending"))

    def test_duplicate_whatsapp_is_rejected(self):
        make_member(whatsapp_number="6281234567890")
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sudah terdaftar")
        self.assertContains(response, 'aria-invalid="true"')

    def test_invalid_whatsapp_is_rejected(self):
        response = self.client.post(self.url, self.payload(whatsapp_number="021-555-1234"))
        self.assertContains(response, "nomor WhatsApp Indonesia yang valid")
        self.assertFalse(User.objects.filter(email="budi@contoh.id").exists())

    def test_signup_cannot_grant_staff(self):
        self.client.post(self.url, self.payload(is_staff="on", status="active"))
        user = User.objects.get(email="budi@contoh.id")
        self.assertFalse(user.is_staff)
        self.assertEqual(user.status, User.Status.PENDING)


class LoginRedirectTests(TestCase):
    url = reverse("account_login")

    def login(self, email):
        return self.client.post(self.url, {"login": email, "password": PASSWORD})

    def test_login_page_renders(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Masuk ke akun Anda")
        self.assertContains(response, reverse("account_reset_password"))

    def test_staff_goes_to_dashboard(self):
        make_admin()
        self.assertRedirects(self.login("admin@sistercreative.tech"), reverse("dashboard:home"))

    def test_member_goes_to_member_area(self):
        make_member(status=User.Status.ACTIVE)
        self.assertRedirects(self.login("aminah@contoh.id"), reverse("members:home"))

    def test_rejected_member_cannot_login(self):
        member = make_member()
        services.reject_member(member)
        response = self.login("aminah@contoh.id")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(response.url if response.status_code == 302 else "", "/member/")

    def test_wrong_password_shows_error(self):
        make_member()
        response = self.client.post(self.url, {"login": "aminah@contoh.id", "password": "salah"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')

    def test_logout_requires_post(self):
        self.client.force_login(make_member())
        self.client.get(reverse("account_logout"))
        self.assertIn("_auth_user_id", self.client.session)
        self.client.post(reverse("account_logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class AccessControlTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.pending = make_member()
        self.active = make_member(email="aktif@contoh.id", status=User.Status.ACTIVE)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, f"{reverse('account_login')}?next=/dashboard/")

    def test_dashboard_forbidden_for_member(self):
        self.client.force_login(self.active)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Akses ditolak", status_code=403)

    def test_dashboard_for_staff_shows_pending_count(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["pending_members"], 1)
        self.assertEqual(response.context["stats"]["active_members"], 1)

    def test_member_area_requires_login(self):
        response = self.client.get(reverse("members:home"))
        self.assertRedirects(response, f"{reverse('account_login')}?next=/member/")

    def test_pending_member_redirected_to_pending_page(self):
        self.client.force_login(self.pending)
        self.assertRedirects(self.client.get(reverse("members:home")), reverse("members:pending"))
        response = self.client.get(reverse("members:pending"))
        self.assertContains(response, "Akun sedang ditinjau")

    def test_active_member_sees_member_home(self):
        self.client.force_login(self.active)
        response = self.client.get(reverse("members:home"))
        self.assertContains(response, "Halo, Siti")
        self.assertRedirects(self.client.get(reverse("members:pending")), reverse("members:home"))

    def test_header_shows_login_or_account_link(self):
        self.assertContains(self.client.get("/"), reverse("account_login"))
        self.client.force_login(self.active)
        self.assertContains(self.client.get("/"), "Akun saya")
