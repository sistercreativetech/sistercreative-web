import json
from datetime import datetime, time, timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.campaigns import services as campaign_services
from apps.campaigns.models import Campaign
from apps.contacts.models import Contact, ContactGroup
from apps.core import n8n
from apps.whatsapp import services as wa_services
from apps.whatsapp import waha
from apps.whatsapp.models import WhatsAppSession

from . import services
from .forms import FollowUpSequenceForm, FollowUpStepForm
from .models import FollowUpEnrollment, FollowUpMessage, FollowUpSequence, FollowUpStep

PASSWORD = "Rahasia-Kuat-2026!"
SETTINGS = {
    "WAHA_WEBHOOK_TOKEN": "token-webhook",
    "N8N_BLAST_WEBHOOK_URL": "https://n8n.contoh.test/webhook/blast",
    "N8N_AUTOREPLY_WEBHOOK_URL": "https://n8n.contoh.test/webhook/autoreply",
    "N8N_BLAST_TOKEN": "token-ke-n8n",
    "N8N_CALLBACK_TOKEN": "token-dari-n8n",
    "SITE_URL": "https://sistercreative.test",
    "FOLLOWUP_BATCH_SIZE": 20,
}
Status = FollowUpEnrollment.Status
CUSTOMER = "6281234567890@c.us"


def make_member(email="siti@contoh.id", **extra):
    extra.setdefault("full_name", "Siti Aminah")
    extra.setdefault("status", User.Status.ACTIVE)
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


def make_sequence(owner, steps=(1, 7), **extra):
    extra.setdefault("name", "Calon pembeli")
    extra.setdefault("trigger", FollowUpSequence.Trigger.ANY_CHAT)
    extra.setdefault("send_from", time(0))
    extra.setdefault("send_until", time(23, 59))
    sequence = FollowUpSequence.objects.create(owner=owner, **extra)
    for days in steps:
        FollowUpStep.objects.create(
            sequence=sequence,
            delay_value=days,
            delay_unit=FollowUpStep.Unit.DAYS,
            body=f"Halo {{nama_depan}}, follow-up hari ke-{days}.",
        )
    return sequence


def incoming(session, body="Kak, harga paket berapa?", sender=CUSTOMER, **extra):
    payload = {"id": f"false_{sender}_{body}", "from": sender, "body": body, "fromMe": False}
    payload.update(extra)
    return services.handle_incoming(session, payload)


class FollowUpTestCase(TestCase):
    def setUp(self):
        self.member = make_member()
        self.session = WhatsAppSession.objects.create(
            owner=self.member, name=f"member-{self.member.pk}", status="WORKING"
        )


@override_settings(**SETTINGS)
class IncomingChatTests(FollowUpTestCase):
    def test_any_chat_enrolls_and_schedules_first_step_from_chat_time(self):
        sequence = make_sequence(self.member)
        before = timezone.now()
        self.assertEqual(incoming(self.session), "enrolled:1 stopped:0")
        enrollment = FollowUpEnrollment.objects.get()
        self.assertEqual(enrollment.sequence, sequence)
        self.assertEqual(enrollment.status, Status.ACTIVE)
        self.assertEqual(enrollment.next_step.delay_value, 1)
        self.assertGreaterEqual(enrollment.next_due_at, before + timedelta(days=1))
        self.assertLess(enrollment.next_due_at, timezone.now() + timedelta(days=1, minutes=1))

    def test_keyword_trigger_only_matches_keywords(self):
        make_sequence(self.member, trigger=FollowUpSequence.Trigger.KEYWORD, keywords="harga")
        self.assertEqual(incoming(self.session, "Assalamualaikum"), "enrolled:0 stopped:0")
        self.assertEqual(incoming(self.session, "Berapa HARGA-nya?"), "enrolled:1 stopped:0")

    def test_manual_inactive_and_empty_sequences_do_not_auto_enroll(self):
        make_sequence(self.member, trigger=FollowUpSequence.Trigger.MANUAL)
        make_sequence(self.member, is_active=False)
        make_sequence(self.member, steps=())
        incoming(self.session)
        self.assertFalse(FollowUpEnrollment.objects.exists())

    def test_same_chat_enrolled_only_once(self):
        make_sequence(self.member)
        incoming(self.session, "halo")
        incoming(self.session, "mau tanya")
        self.assertEqual(FollowUpEnrollment.objects.count(), 1)

    def test_groups_own_messages_and_opted_out_contacts_ignored(self):
        make_sequence(self.member)
        Contact.objects.create(
            owner=self.member, name="Rina", phone="6281111111111", is_opted_out=True
        )
        self.assertEqual(incoming(self.session, sender="120363@g.us"), "ignored")
        self.assertEqual(incoming(self.session, fromMe=True), "ignored")
        incoming(self.session, sender="6281111111111@c.us")
        self.assertFalse(FollowUpEnrollment.objects.exists())

    def test_name_from_contact_or_whatsapp_profile(self):
        make_sequence(self.member)
        Contact.objects.create(owner=self.member, name="Rina Wati", phone="6281234567890")
        incoming(self.session)
        incoming(self.session, sender="6282222222222@c.us", _data={"pushName": "Budi  Santoso"})
        names = set(FollowUpEnrollment.objects.values_list("display_name", flat=True))
        self.assertEqual(names, {"Rina Wati", "Budi Santoso"})

    def test_reply_stops_only_after_a_follow_up_was_sent(self):
        make_sequence(self.member)
        incoming(self.session, "halo")
        incoming(self.session, "mau tanya harga")  # pesan beruntun di awal: tetap berjalan
        enrollment = FollowUpEnrollment.objects.get()
        self.assertEqual(enrollment.status, Status.ACTIVE)

        enrollment.last_step_at = timezone.now()
        enrollment.save()
        self.assertEqual(incoming(self.session, "iya kak, jadi pesan"), "enrolled:0 stopped:1")
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Status.STOPPED)
        self.assertEqual(enrollment.stop_reason, FollowUpEnrollment.StopReason.REPLIED)
        self.assertIsNone(enrollment.next_due_at)

    def test_reply_does_not_stop_when_disabled(self):
        make_sequence(self.member, stop_on_reply=False)
        incoming(self.session)
        FollowUpEnrollment.objects.update(last_step_at=timezone.now())
        incoming(self.session, "oke")
        self.assertEqual(FollowUpEnrollment.objects.get().status, Status.ACTIVE)

    def test_other_members_chats_are_separate(self):
        other = make_member("budi@contoh.id")
        make_sequence(other)
        incoming(self.session)
        self.assertFalse(FollowUpEnrollment.objects.exists())


@override_settings(**SETTINGS)
class WebhookIntegrationTests(FollowUpTestCase):
    def post(self, body):
        event = {
            "event": "message",
            "session": self.session.name,
            "payload": {"id": f"msg-{body}", "from": CUSTOMER, "body": body, "fromMe": False},
        }
        return self.client.post(
            reverse("waha_webhook"),
            json.dumps(event),
            content_type="application/json",
            HTTP_X_SC_TOKEN="token-webhook",
        )

    def test_webhook_enrolls_and_stop_ends_follow_up(self):
        make_sequence(self.member)
        Contact.objects.create(owner=self.member, name="Rina", phone="6281234567890")
        self.post("Kak, info harga")
        self.assertEqual(FollowUpEnrollment.objects.get().status, Status.ACTIVE)
        with mock.patch.object(waha, "send_text"):
            self.post("STOP")
        enrollment = FollowUpEnrollment.objects.get()
        self.assertEqual(enrollment.status, Status.STOPPED)
        self.assertEqual(enrollment.stop_reason, FollowUpEnrollment.StopReason.OPTED_OUT)

    def test_follow_up_error_does_not_break_auto_reply(self):
        event = {
            "event": "message",
            "session": self.session.name,
            "payload": {"id": "x1", "from": CUSTOMER, "body": "halo"},
        }
        broken = mock.patch.object(services, "handle_incoming", side_effect=RuntimeError("rusak"))
        with broken, self.assertLogs("apps.whatsapp.services", "ERROR"):
            result = wa_services.handle_event(event)
        self.assertEqual(result, "no-rule")


@override_settings(**SETTINGS)
class DispatchTests(FollowUpTestCase):
    def setUp(self):
        super().setUp()
        self.post_job = mock.patch.object(n8n, "post_job").start()
        self.addCleanup(mock.patch.stopall)
        self.sequence = make_sequence(self.member)
        self.contact = Contact.objects.create(
            owner=self.member, name="Rina Wati", phone="6281234567890"
        )
        self.enrollment = services.enroll(
            self.sequence, chat_id=CUSTOMER, contact=self.contact, display_name="Rina Wati"
        )

    def due_time(self, days=1):
        return self.enrollment.enrolled_at + timedelta(days=days, minutes=1)

    def test_nothing_sent_before_due(self):
        result = services.dispatch_due(now=self.enrollment.enrolled_at + timedelta(hours=23))
        self.assertEqual(result["queued"], 0)
        self.post_job.assert_not_called()

    def test_due_step_posted_to_blast_workflow_and_next_step_scheduled(self):
        now = self.due_time()
        self.assertEqual(services.dispatch_due(now=now)["queued"], 1)

        url, payload = self.post_job.call_args.args
        self.assertEqual(url, SETTINGS["N8N_BLAST_WEBHOOK_URL"])
        self.assertEqual(payload["session"], self.session.name)
        self.assertEqual(
            payload["callback_url"], "https://sistercreative.test/api/n8n/follow-up/hasil/"
        )
        self.assertEqual(payload["image_url"], "")
        message = FollowUpMessage.objects.get()
        self.assertEqual(
            payload["recipients"],
            [{"recipient_id": message.pk, "chat_id": CUSTOMER, "text": message.text}],
        )
        self.assertTrue(message.text.startswith("Halo Rina, follow-up hari ke-1."))
        self.assertIn("STOP", message.text)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.next_step.delay_value, 7)
        self.assertEqual(
            self.enrollment.next_due_at, self.enrollment.enrolled_at + timedelta(days=7)
        )
        # Putaran berikutnya tidak mengirim ulang langkah yang sama.
        services.dispatch_due(now=now + timedelta(minutes=10))
        self.assertEqual(FollowUpMessage.objects.count(), 1)

    def test_last_step_completes_enrollment(self):
        services.dispatch_due(now=self.due_time(1))
        services.dispatch_due(now=self.due_time(7))
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Status.COMPLETED)
        self.assertEqual(FollowUpMessage.objects.count(), 2)

    def test_late_steps_keep_minimum_gap(self):
        # Langkah 1 baru terkirim hari ke-7 (mis. WA terputus): langkah 2 menunggu ≥ 1 jam.
        now = self.due_time(7)
        services.dispatch_due(now=now)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.next_due_at, now + services.MIN_GAP)

    def test_outside_send_hours_waits(self):
        self.sequence.send_from, self.sequence.send_until = time(8), time(20)
        self.sequence.save()
        local_night = timezone.make_aware(
            datetime.combine(timezone.localtime(self.due_time()).date(), time(22))
        )
        if local_night < self.due_time():
            local_night += timedelta(days=1)
        self.assertEqual(services.dispatch_due(now=local_night)["queued"], 0)
        self.assertEqual(services.dispatch_due(now=local_night + timedelta(hours=11))["queued"], 1)

    def test_deferred_when_disconnected_campaign_running_or_inactive_sequence(self):
        now = self.due_time()
        self.session.status = "STOPPED"
        self.session.save()
        self.assertEqual(services.dispatch_due(now=now)["deferred"], 1)

        self.session.status = "WORKING"
        self.session.save()
        campaign = Campaign.objects.create(
            owner=self.member, name="Promo", body="Halo", status=Campaign.Status.RUNNING
        )
        self.assertEqual(services.dispatch_due(now=now)["deferred"], 1)

        campaign.status = Campaign.Status.COMPLETED
        campaign.save()
        self.sequence.is_active = False
        self.sequence.save()
        self.assertEqual(services.dispatch_due(now=now)["queued"], 0)
        self.post_job.assert_not_called()

    def test_respects_daily_quota(self):
        self.member.daily_message_quota = 1
        self.member.save()
        services.enroll(self.sequence, chat_id="6282222222222@c.us")
        now = self.due_time()
        self.assertEqual(services.dispatch_due(now=now)["queued"], 1)
        self.assertEqual(campaign_services.used_today(self.member), 1)
        self.assertEqual(services.dispatch_due(now=now)["deferred"], 1)

    def test_n8n_error_rolls_back_for_retry(self):
        self.post_job.side_effect = n8n.N8nError("down")
        with self.assertLogs("apps.followups.services", "WARNING"):
            self.assertEqual(services.dispatch_due(now=self.due_time())["deferred"], 1)
        self.assertFalse(FollowUpMessage.objects.exists())
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.next_step.delay_value, 1)
        self.assertIsNone(self.enrollment.last_step_at)

    def test_opted_out_contact_is_stopped_not_sent(self):
        self.contact.is_opted_out = True
        self.contact.save()
        result = services.dispatch_due(now=self.due_time())
        self.assertEqual(result, {"queued": 0, "stopped": 1, "deferred": 0})
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.stop_reason, FollowUpEnrollment.StopReason.OPTED_OUT)

    def test_one_job_per_member(self):
        other = make_member("budi@contoh.id")
        WhatsAppSession.objects.create(owner=other, name=f"member-{other.pk}", status="WORKING")
        other_enrollment = services.enroll(make_sequence(other), chat_id=CUSTOMER)
        now = max(self.due_time(), other_enrollment.enrolled_at + timedelta(days=1, minutes=1))
        self.assertEqual(services.dispatch_due(now=now)["queued"], 2)
        sessions = {call.args[1]["session"] for call in self.post_job.call_args_list}
        self.assertEqual(sessions, {self.session.name, f"member-{other.pk}"})

    def test_adding_earlier_step_reschedules_active_enrollments(self):
        FollowUpStep.objects.create(
            sequence=self.sequence, delay_value=3, delay_unit="hours", body="Cepat"
        )
        services.reschedule_sequence(self.sequence)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.next_step.delay_minutes, 180)


@override_settings(**SETTINGS)
class EndpointTests(FollowUpTestCase):
    def post(self, name, payload=None, token="token-dari-n8n"):
        return self.client.post(
            reverse(name),
            json.dumps(payload or {}),
            content_type="application/json",
            HTTP_X_SC_TOKEN=token,
        )

    def make_message(self):
        sequence = make_sequence(self.member)
        enrollment = services.enroll(sequence, chat_id=CUSTOMER)
        return FollowUpMessage.objects.create(
            owner=self.member,
            enrollment=enrollment,
            step=sequence.steps.first(),
            chat_id=CUSTOMER,
            text="Halo",
        )

    def test_endpoints_require_token(self):
        self.assertEqual(self.post("followup_dispatch", token="salah").status_code, 403)
        self.assertEqual(self.post("followup_callback", token="salah").status_code, 403)

    def test_dispatch_endpoint_runs(self):
        response = self.post("followup_dispatch")
        self.assertEqual(response.json(), {"ok": True, "queued": 0, "stopped": 0, "deferred": 0})

    def test_callback_records_sent_and_failed(self):
        message = self.make_message()
        response = self.post(
            "followup_callback",
            {"campaign_id": 0, "recipient_id": message.pk, "status": "sent", "message_id": "ABC"},
        )
        self.assertEqual(response.json(), {"ok": True, "continue": True})
        message.refresh_from_db()
        self.assertEqual(message.status, FollowUpMessage.Status.SENT)
        self.assertEqual(message.wa_message_id, "ABC")
        self.assertIsNotNone(message.sent_at)

        failed = FollowUpMessage.objects.create(owner=self.member, chat_id=CUSTOMER, text="x")
        self.post(
            "followup_callback", {"recipient_id": failed.pk, "status": "failed", "error": "nope"}
        )
        failed.refresh_from_db()
        self.assertEqual((failed.status, failed.error), ("failed", "nope"))

    def test_callback_unknown_message(self):
        response = self.post("followup_callback", {"recipient_id": 999, "status": "sent"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["continue"])

    def test_sent_follow_ups_count_toward_quota_even_after_sequence_deleted(self):
        message = self.make_message()
        message.status, message.sent_at = FollowUpMessage.Status.SENT, timezone.now()
        message.save()
        message.enrollment.sequence.delete()
        self.assertEqual(campaign_services.used_today(self.member), 1)


class FormTests(TestCase):
    def setUp(self):
        self.member = make_member()

    def sequence_form(self, **data):
        base = {"name": "Calon", "trigger": "keyword", "keywords": "", "is_active": "on"}
        base.update({"send_from": "08:00", "send_until": "20:00", **data})
        return FollowUpSequenceForm(base, owner=self.member)

    def test_keyword_trigger_requires_keywords_and_rejects_stop(self):
        self.assertIn("keywords", self.sequence_form().errors)
        self.assertIn("keywords", self.sequence_form(keywords="stop, harga").errors)
        self.assertTrue(self.sequence_form(keywords="harga, Harga, daftar").is_valid())
        self.assertTrue(self.sequence_form(trigger="any_chat").is_valid())

    def test_send_hours_must_be_ordered(self):
        form = self.sequence_form(trigger="any_chat", send_until="07:00")
        self.assertIn("send_until", form.errors)

    def step_form(self, sequence, **data):
        base = {"delay_value": 1, "delay_unit": "days", "body": "Halo {nama_depan}"}
        base.update(data)
        return FollowUpStepForm(base, sequence=sequence)

    def test_step_validation(self):
        sequence = make_sequence(self.member, steps=(1,))
        self.assertIn("delay_value", self.step_form(sequence).errors)  # waktu sama
        self.assertIn("delay_value", self.step_form(sequence, delay_value=91).errors)
        self.assertIn("body", self.step_form(sequence, delay_value=2, body="Hai {alamat}").errors)
        form = self.step_form(sequence, delay_value=24, delay_unit="hours")
        self.assertIn("delay_value", form.errors)  # 24 jam = 1 hari
        form = self.step_form(sequence, delay_value=3)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().delay_minutes, 3 * 24 * 60)

    def test_max_steps(self):
        sequence = make_sequence(self.member, steps=(1, 2, 3, 4, 5))
        form = self.step_form(sequence, delay_value=6)
        self.assertFalse(form.is_valid())
        self.assertIn("maksimal 5 langkah", str(form.non_field_errors()))


@override_settings(**SETTINGS)
class MemberViewTests(FollowUpTestCase):
    def setUp(self):
        super().setUp()
        self.other = make_member("budi@contoh.id", full_name="Budi Santoso")
        self.client.force_login(self.member)

    def test_pending_member_redirected(self):
        pending = make_member("baru@contoh.id", status=User.Status.PENDING)
        self.client.force_login(pending)
        response = self.client.get(reverse("followups:sequence_list"))
        self.assertRedirects(response, reverse("members:pending"))

    def test_create_sequence_then_add_step(self):
        response = self.client.post(
            reverse("followups:sequence_create"),
            {
                "name": "Tanya harga",
                "trigger": "keyword",
                "keywords": "harga",
                "is_active": "on",
                "stop_on_reply": "on",
                "send_from": "08:00",
                "send_until": "20:00",
            },
        )
        sequence = FollowUpSequence.objects.get()
        self.assertRedirects(response, sequence.get_absolute_url())
        self.assertEqual(sequence.owner, self.member)

        response = self.client.post(
            reverse("followups:step_create", args=[sequence.pk]),
            {"delay_value": 1, "delay_unit": "days", "body": "Halo {nama_depan}"},
        )
        self.assertRedirects(response, sequence.get_absolute_url())
        page = self.client.get(sequence.get_absolute_url())
        self.assertContains(page, "1 hari setelah chat")
        self.assertContains(self.client.get(reverse("followups:sequence_list")), "Tanya harga")

    def test_manual_enroll_from_group_skips_opted_out(self):
        sequence = make_sequence(self.member, trigger=FollowUpSequence.Trigger.MANUAL)
        group = ContactGroup.objects.create(owner=self.member, name="Alumni")
        ok = Contact.objects.create(owner=self.member, name="Rina", phone="6281111111111")
        stop = Contact.objects.create(
            owner=self.member, name="Dewi", phone="6282222222222", is_opted_out=True
        )
        group.contacts.add(ok, stop)
        url = reverse("followups:enroll_contacts", args=[sequence.pk])
        self.client.post(url, {"groups": [group.pk]})
        self.assertEqual(
            list(FollowUpEnrollment.objects.values_list("chat_id", flat=True)),
            ["6281111111111@c.us"],
        )

    def test_stop_and_restart_enrollment(self):
        sequence = make_sequence(self.member)
        enrollment = services.enroll(sequence, chat_id=CUSTOMER)
        self.client.post(reverse("followups:enrollment_stop", args=[enrollment.pk]))
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.stop_reason, FollowUpEnrollment.StopReason.MANUAL)
        self.client.post(reverse("followups:enrollment_restart", args=[enrollment.pk]))
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Status.ACTIVE)
        self.assertEqual(enrollment.next_step.delay_value, 1)

    def test_cannot_touch_other_members_data(self):
        sequence = make_sequence(self.other, name="Rahasia Budi")
        step = sequence.steps.first()
        enrollment = services.enroll(sequence, chat_id=CUSTOMER)
        own_group = ContactGroup.objects.create(owner=self.member, name="Grup saya")
        detail = reverse("followups:sequence_detail", args=[sequence.pk])
        self.assertEqual(self.client.get(detail).status_code, 404)
        for name, pk in [
            ("followups:sequence_update", sequence.pk),
            ("followups:sequence_delete", sequence.pk),
            ("followups:step_create", sequence.pk),
            ("followups:step_update", step.pk),
            ("followups:step_delete", step.pk),
        ]:
            url = reverse(name, args=[pk])
            self.assertEqual(self.client.get(url).status_code, 404, name)
            self.assertEqual(self.client.post(url, {"name": "Ubah"}).status_code, 404, name)
        for name, pk, data in [
            ("followups:enroll_contacts", sequence.pk, {"groups": [own_group.pk]}),
            ("followups:enrollment_stop", enrollment.pk, {}),
            ("followups:enrollment_restart", enrollment.pk, {}),
        ]:
            self.assertEqual(self.client.post(reverse(name, args=[pk]), data).status_code, 404)
        self.assertTrue(FollowUpSequence.objects.filter(name="Rahasia Budi").exists())
        self.assertEqual(sequence.steps.count(), 2)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Status.ACTIVE)
        self.assertNotContains(self.client.get(reverse("followups:sequence_list")), "Rahasia Budi")

    def test_cannot_enroll_other_members_group(self):
        sequence = make_sequence(self.member, trigger=FollowUpSequence.Trigger.MANUAL)
        foreign = ContactGroup.objects.create(owner=self.other, name="Grup Budi")
        foreign.contacts.add(Contact.objects.create(owner=self.other, phone="6283333333333"))
        self.client.post(
            reverse("followups:enroll_contacts", args=[sequence.pk]), {"groups": [foreign.pk]}
        )
        self.assertFalse(FollowUpEnrollment.objects.exists())
