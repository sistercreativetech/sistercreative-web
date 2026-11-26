import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.contacts.models import Contact

from . import services, waha
from .models import WhatsAppSession

PASSWORD = "Rahasia-Kuat-2026!"
WAHA_SETTINGS = {
    "WAHA_BASE_URL": "https://waha.contoh.test",
    "WAHA_API_KEY": "kunci-rahasia",
    "WAHA_WEBHOOK_TOKEN": "token-webhook",
    "SITE_URL": "https://sistercreative.tech",
}


def make_member(email="siti@contoh.id", **extra):
    extra.setdefault("full_name", "Siti Aminah")
    extra.setdefault("status", User.Status.ACTIVE)
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


class WahaClientParsingTests(TestCase):
    @override_settings(**WAHA_SETTINGS)
    def test_list_groups_handles_engine_formats(self):
        raw = [
            {"id": {"_serialized": "120363@g.us"}, "name": "Wali Murid 5A"},
            {"id": "999@g.us", "subject": "Alumni"},
            {"JID": "777@g.us", "Name": "Arisan RT"},
            {"id": "6281@c.us", "name": "Bukan grup"},
        ]
        with mock.patch.object(waha, "_json", return_value=raw):
            groups = waha.list_groups("member-1")
        self.assertEqual(
            groups,
            [
                {"id": "999@g.us", "name": "Alumni"},
                {"id": "777@g.us", "name": "Arisan RT"},
                {"id": "120363@g.us", "name": "Wali Murid 5A"},
            ],
        )

    @override_settings(WAHA_BASE_URL="", WAHA_API_KEY="")
    def test_not_configured_raises(self):
        with self.assertRaises(waha.WahaNotConfigured):
            waha.get_session("member-1")


@override_settings(**WAHA_SETTINGS)
class SessionServiceTests(TestCase):
    def setUp(self):
        self.member = make_member()

    def test_connect_creates_session_with_webhook_token(self):
        with (
            mock.patch.object(waha, "get_session", return_value=None),
            mock.patch.object(
                waha, "create_session", return_value={"status": "SCAN_QR_CODE"}
            ) as create,
        ):
            session = services.connect(self.member)
        self.assertEqual(session.name, f"member-{self.member.pk}")
        self.assertEqual(session.status, WhatsAppSession.Status.SCAN_QR_CODE)
        create.assert_called_once_with(
            session.name, "https://sistercreative.tech/api/webhooks/waha/", "token-webhook"
        )

    def test_connect_restarts_stopped_session(self):
        with (
            mock.patch.object(waha, "get_session", return_value={"status": "STOPPED"}),
            mock.patch.object(waha, "start_session", return_value={"status": "STARTING"}) as start,
        ):
            services.connect(self.member)
        start.assert_called_once()

    def test_refresh_stores_connected_number(self):
        session = services.get_or_init_session(self.member)
        remote = {"status": "WORKING", "me": {"id": "6281234567890@c.us", "pushName": "Siti"}}
        with mock.patch.object(waha, "get_session", return_value=remote):
            services.refresh_status(session)
        session.refresh_from_db()
        self.assertTrue(session.is_connected)
        self.assertEqual(session.connected_number, "6281234567890")

    def test_groups_empty_when_not_connected(self):
        with mock.patch.object(waha, "list_groups") as list_groups:
            self.assertEqual(services.whatsapp_groups(self.member), [])
        list_groups.assert_not_called()


@override_settings(**WAHA_SETTINGS)
class SessionViewTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.client.force_login(self.member)

    def test_page_shows_connect_button_when_not_created(self):
        with mock.patch.object(waha, "get_session", return_value=None):
            response = self.client.get(reverse("whatsapp:session"))
        self.assertContains(response, "Tampilkan kode QR")
        self.assertNotContains(response, "kunci-rahasia")

    def test_page_shows_qr_while_scanning(self):
        with mock.patch.object(waha, "get_session", return_value={"status": "SCAN_QR_CODE"}):
            response = self.client.get(reverse("whatsapp:session"))
        self.assertContains(response, reverse("whatsapp:session_qr"))
        self.assertContains(response, 'data-status="SCAN_QR_CODE"')

    def test_qr_proxy_uses_own_session_and_disables_cache(self):
        with mock.patch.object(waha, "get_qr_png", return_value=b"\x89PNG") as get_qr:
            response = self.client.get(reverse("whatsapp:session_qr"))
        get_qr.assert_called_once_with(f"member-{self.member.pk}")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_waha_down_does_not_crash(self):
        with mock.patch.object(waha, "get_session", side_effect=waha.WahaError("down")):
            response = self.client.get(reverse("whatsapp:session"))
        self.assertContains(response, "tidak bisa dihubungi")

    def test_connect_requires_post(self):
        self.assertEqual(self.client.get(reverse("whatsapp:session_connect")).status_code, 405)

    @override_settings(WAHA_BASE_URL="", WAHA_API_KEY="")
    def test_not_configured_message(self):
        response = self.client.get(reverse("whatsapp:session"))
        self.assertContains(response, "belum disiapkan admin")

    def test_pending_member_blocked(self):
        self.client.force_login(make_member("baru@contoh.id", status=User.Status.PENDING))
        self.assertRedirects(
            self.client.get(reverse("whatsapp:session")), reverse("members:pending")
        )


@override_settings(**WAHA_SETTINGS)
class WebhookTests(TestCase):
    url = reverse("waha_webhook")

    def setUp(self):
        self.member = make_member()
        self.session = WhatsAppSession.objects.create(
            owner=self.member, name=f"member-{self.member.pk}", status="WORKING"
        )
        self.contact = Contact.objects.create(owner=self.member, name="Budi", phone="6281234567890")

    def post(self, event, token="token-webhook"):
        return self.client.post(
            self.url, json.dumps(event), content_type="application/json", HTTP_X_SC_TOKEN=token
        )

    def stop_event(self, body="stop", sender="6281234567890@c.us", **payload):
        return {
            "event": "message",
            "session": self.session.name,
            "payload": {"from": sender, "body": body, "fromMe": False, **payload},
        }

    def test_rejects_wrong_token(self):
        self.assertEqual(self.post(self.stop_event(), token="salah").status_code, 403)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_opted_out)

    def test_stop_reply_opts_out_contact(self):
        with mock.patch.object(waha, "send_text") as send:
            response = self.post(self.stop_event(" Stop "))
        self.assertEqual(response.json()["result"], "opted-out")
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.is_opted_out)
        send.assert_called_once()

    def test_other_text_ignored(self):
        self.assertEqual(self.post(self.stop_event("terima kasih")).json()["result"], "ignored")

    def test_group_and_own_messages_ignored(self):
        self.post(self.stop_event(sender="120363@g.us"))
        self.post(self.stop_event(fromMe=True))
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_opted_out)

    def test_stop_only_affects_session_owner_contacts(self):
        other = make_member("budi@contoh.id")
        foreign = Contact.objects.create(owner=other, phone="6281234567890")
        with mock.patch.object(waha, "send_text"):
            self.post(self.stop_event())
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_opted_out)

    def test_session_status_event(self):
        self.post(
            {
                "event": "session.status",
                "session": self.session.name,
                "payload": {"status": "FAILED"},
            }
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "FAILED")

    def test_invalid_json(self):
        response = self.client.post(
            self.url, "bukan json", content_type="application/json", HTTP_X_SC_TOKEN="token-webhook"
        )
        self.assertEqual(response.status_code, 400)
