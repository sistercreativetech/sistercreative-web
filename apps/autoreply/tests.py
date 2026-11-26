import json
from datetime import time, timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.contacts.models import Contact
from apps.core import n8n
from apps.whatsapp import waha
from apps.whatsapp.models import WhatsAppSession

from . import services
from .matching import keyword_matches, within_hours
from .models import AutoReplyLog, AutoReplyRule

PASSWORD = "Rahasia-Kuat-2026!"
SETTINGS = {
    "WAHA_WEBHOOK_TOKEN": "token-webhook",
    "N8N_AUTOREPLY_WEBHOOK_URL": "https://n8n.contoh.test/webhook/autoreply",
    "N8N_BLAST_TOKEN": "token-ke-n8n",
    "AUTO_REPLY_MAX_PER_HOUR": 30,
}


def make_member(email="siti@contoh.id", **extra):
    extra.setdefault("full_name", "Siti Aminah")
    extra.setdefault("status", User.Status.ACTIVE)
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


class MatchingTests(SimpleTestCase):
    def test_contains_matches_whole_words_case_and_punctuation_insensitive(self):
        self.assertTrue(keyword_matches("Kak, HARGA paket berapa?", "harga", "contains"))
        self.assertTrue(keyword_matches("info jam buka dong", "jam buka", "contains"))
        self.assertFalse(keyword_matches("saya menghargai bantuannya", "harga", "contains"))

    def test_exact_and_starts_with(self):
        self.assertTrue(keyword_matches("  Halo!! ", "halo", "exact"))
        self.assertFalse(keyword_matches("halo kak", "halo", "exact"))
        self.assertTrue(keyword_matches("Daftar kelas tahfidz", "daftar", "starts_with"))
        self.assertFalse(keyword_matches("cara daftar", "daftar", "starts_with"))

    def test_active_hours_including_overnight(self):
        self.assertTrue(within_hours(time(10), time(8), time(21)))
        self.assertFalse(within_hours(time(22), time(8), time(21)))
        self.assertTrue(within_hours(time(23), time(20), time(6)))
        self.assertTrue(within_hours(time(5), time(20), time(6)))
        self.assertFalse(within_hours(time(12), time(20), time(6)))
        self.assertTrue(within_hours(time(3), None, None))


@override_settings(**SETTINGS)
class HandleIncomingTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.session = WhatsAppSession.objects.create(
            owner=self.member, name=f"member-{self.member.pk}", status="WORKING"
        )
        self.rule = AutoReplyRule.objects.create(
            owner=self.member,
            name="Harga",
            keywords="harga, price",
            reply="Halo {nama_depan}, paket mulai Rp1,5 juta.",
        )
        self.post_job = mock.patch.object(n8n, "post_job").start()
        self.addCleanup(mock.patch.stopall)
        self.counter = 0

    def incoming(self, body="Berapa harga paketnya?", sender="6281234567890@c.us", **extra):
        self.counter += 1
        payload = {"id": f"false_{sender}_MSG{self.counter}", "from": sender, "body": body}
        payload.update(extra)
        return services.handle_incoming(self.session, payload)

    def test_queues_personalized_reply_with_typing_delay(self):
        Contact.objects.create(owner=self.member, name="Rina Wati", phone="6281234567890")
        self.assertEqual(self.incoming(), "queued")
        url, payload = self.post_job.call_args.args
        self.assertEqual(url, SETTINGS["N8N_AUTOREPLY_WEBHOOK_URL"])
        self.assertEqual(payload["session"], self.session.name)
        self.assertEqual(payload["chat_id"], "6281234567890@c.us")
        self.assertEqual(payload["reply"], "Halo Rina, paket mulai Rp1,5 juta.")
        self.assertTrue(2 <= payload["typing_seconds"] <= 8)
        self.assertEqual(AutoReplyLog.objects.get().status, AutoReplyLog.Status.QUEUED)

    def test_unknown_sender_greeted_generically(self):
        self.incoming()
        self.assertTrue(self.post_job.call_args.args[1]["reply"].startswith("Halo Bapak/Ibu"))

    def test_lid_sender_is_replied_to_original_chat(self):
        self.assertEqual(self.incoming(sender="123456789@lid"), "queued")
        self.assertEqual(self.post_job.call_args.args[1]["chat_id"], "123456789@lid")

    def test_ignores_groups_status_own_and_empty(self):
        self.assertEqual(self.incoming(sender="120363@g.us"), "ignored")
        self.assertEqual(self.incoming(sender="status@broadcast"), "ignored")
        self.assertEqual(self.incoming(fromMe=True), "ignored")
        self.assertEqual(self.incoming(body="   "), "ignored")
        self.post_job.assert_not_called()

    def test_no_rule_and_inactive_rule(self):
        self.assertEqual(self.incoming("terima kasih"), "no-rule")
        self.rule.is_active = False
        self.rule.save()
        self.assertEqual(self.incoming(), "no-rule")

    def test_cooldown_per_chat(self):
        self.assertEqual(self.incoming(), "queued")
        self.assertEqual(self.incoming(), "cooldown")
        self.assertEqual(self.incoming(sender="6289999999999@c.us"), "queued")
        AutoReplyLog.objects.update(created_at=timezone.now() - timedelta(minutes=61))
        self.assertEqual(self.incoming(), "queued")

    @override_settings(AUTO_REPLY_MAX_PER_HOUR=2)
    def test_hourly_limit(self):
        self.rule.cooldown_minutes = 0
        self.rule.save()
        self.assertEqual(self.incoming(), "queued")
        self.assertEqual(self.incoming(), "queued")
        self.assertEqual(self.incoming(), "hourly-limit")

    def test_duplicate_webhook_delivery(self):
        payload = {"id": "false_x_SAMA", "from": "6281234567890@c.us", "body": "harga?"}
        self.assertEqual(services.handle_incoming(self.session, payload), "queued")
        self.assertEqual(services.handle_incoming(self.session, payload), "duplicate")
        self.assertEqual(self.post_job.call_count, 1)

    def test_opted_out_contact_not_replied(self):
        Contact.objects.create(owner=self.member, phone="6281234567890", is_opted_out=True)
        self.assertEqual(self.incoming(), "opted-out-contact")

    def test_priority_order(self):
        AutoReplyRule.objects.create(
            owner=self.member, name="Promo", keywords="harga", reply="Promo!", priority=1
        )
        self.incoming()
        self.assertEqual(self.post_job.call_args.args[1]["reply"], "Promo!")

    def test_rules_of_other_member_not_used(self):
        other = make_member("budi@contoh.id")
        AutoReplyRule.objects.create(owner=other, name="X", keywords="alamat", reply="Rahasia")
        self.assertEqual(self.incoming("alamat?"), "no-rule")

    def test_dispatch_failure_is_logged(self):
        self.post_job.side_effect = n8n.N8nError("down")
        self.assertEqual(self.incoming(), "dispatch-failed")
        self.assertEqual(AutoReplyLog.objects.get().status, AutoReplyLog.Status.FAILED)
        self.assertEqual(services.hourly_count(self.member), 0)


@override_settings(**SETTINGS)
class WebhookIntegrationTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.session = WhatsAppSession.objects.create(
            owner=self.member, name=f"member-{self.member.pk}", status="WORKING"
        )
        AutoReplyRule.objects.create(owner=self.member, name="Harga", keywords="harga", reply="Ok")

    def post(self, body, msg_id):
        event = {
            "event": "message",
            "session": self.session.name,
            "payload": {"id": msg_id, "from": "6281234567890@c.us", "body": body},
        }
        return self.client.post(
            reverse("waha_webhook"),
            json.dumps(event),
            content_type="application/json",
            HTTP_X_SC_TOKEN="token-webhook",
        ).json()

    def test_keyword_message_goes_to_autoreply(self):
        with mock.patch.object(n8n, "post_job") as post_job:
            self.assertEqual(self.post("harga?", "m1")["result"], "queued")
        post_job.assert_called_once()

    def test_stop_still_takes_priority(self):
        Contact.objects.create(owner=self.member, phone="6281234567890")
        with (
            mock.patch.object(n8n, "post_job") as post_job,
            mock.patch.object(waha, "send_text"),
        ):
            self.assertEqual(self.post("STOP", "m2")["result"], "opted-out")
        post_job.assert_not_called()


class RuleViewTests(TestCase):
    def setUp(self):
        self.member = make_member()
        self.other = make_member("budi@contoh.id", full_name="Budi Santoso")
        self.client.force_login(self.member)

    def payload(self, **overrides):
        data = {
            "name": "Info harga",
            "keywords": "Harga, price, harga ",
            "match_type": "contains",
            "reply": "Halo {nama_depan}, paket mulai Rp1,5 juta.",
            "is_active": "on",
            "priority": 10,
            "cooldown_minutes": 60,
            "active_from": "",
            "active_until": "",
        }
        data.update(overrides)
        return data

    def test_create_rule_dedupes_keywords(self):
        response = self.client.post(reverse("autoreply:rule_create"), self.payload())
        self.assertRedirects(response, reverse("autoreply:rule_list"))
        rule = AutoReplyRule.objects.get(owner=self.member)
        self.assertEqual(rule.keyword_list, ["Harga", "price"])

    def test_rejects_stop_keyword_unknown_variable_and_half_hours(self):
        url = reverse("autoreply:rule_create")
        self.assertContains(self.client.post(url, self.payload(keywords="stop")), "STOP/BERHENTI")
        self.assertContains(
            self.client.post(url, self.payload(reply="Diskon {harga}")), "Variabel tidak dikenal"
        )
        self.assertContains(
            self.client.post(url, self.payload(active_from="08:00")), "jam mulai dan jam selesai"
        )
        self.assertFalse(AutoReplyRule.objects.exists())

    def test_test_form_previews_without_sending(self):
        AutoReplyRule.objects.create(
            owner=self.member, name="Harga", keywords="harga", reply="Halo {nama_depan}!"
        )
        with mock.patch.object(n8n, "post_job") as post_job:
            response = self.client.get(
                reverse("autoreply:rule_list"), {"message": "harga?", "name": "Dedi Kurnia"}
            )
        self.assertContains(response, "Halo Dedi!")
        post_job.assert_not_called()
        no_match = self.client.get(reverse("autoreply:rule_list"), {"message": "assalamualaikum"})
        self.assertContains(no_match, "Tidak ada aturan aktif yang cocok")

    def test_other_members_rules_are_hidden(self):
        rule = AutoReplyRule.objects.create(
            owner=self.other, name="Rahasia Budi", keywords="a", reply="b"
        )
        self.assertNotContains(self.client.get(reverse("autoreply:rule_list")), "Rahasia Budi")
        for name in ["autoreply:rule_update", "autoreply:rule_delete"]:
            self.assertEqual(self.client.get(reverse(name, args=[rule.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse(name, args=[rule.pk])).status_code, 404)
        self.assertTrue(AutoReplyRule.objects.filter(pk=rule.pk).exists())

    def test_logs_only_own(self):
        AutoReplyLog.objects.create(
            owner=self.other,
            chat_id="62811@c.us",
            message_id="x1",
            incoming_text="punya budi",
            reply_text="r",
        )
        self.assertNotContains(self.client.get(reverse("autoreply:log_list")), "punya budi")

    def test_pending_member_blocked(self):
        self.client.force_login(make_member("baru@contoh.id", status=User.Status.PENDING))
        self.assertRedirects(
            self.client.get(reverse("autoreply:rule_list")), reverse("members:pending")
        )
