import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.contacts.models import Contact, ContactGroup, MessageTemplate
from apps.whatsapp import waha
from apps.whatsapp.models import WhatsAppSession

from . import services
from .models import Campaign, CampaignRecipient

PASSWORD = "Rahasia-Kuat-2026!"
SETTINGS = {
    "WAHA_BASE_URL": "https://waha.contoh.test",
    "WAHA_API_KEY": "kunci-rahasia",
    "N8N_BLAST_WEBHOOK_URL": "https://n8n.contoh.test/webhook/blast",
    "N8N_BLAST_TOKEN": "token-ke-n8n",
    "N8N_CALLBACK_TOKEN": "token-dari-n8n",
    "SITE_URL": "https://sistercreative.tech",
}
WA_GROUPS = [{"id": "120363@g.us", "name": "Wali Murid 5A"}]


def make_member(email="siti@contoh.id", **extra):
    extra.setdefault("full_name", "Siti Aminah")
    extra.setdefault("status", User.Status.ACTIVE)
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


@override_settings(**SETTINGS)
class CampaignTestCase(TestCase):
    def setUp(self):
        self.member = make_member()
        self.session = WhatsAppSession.objects.create(
            owner=self.member, name=f"member-{self.member.pk}", status="WORKING"
        )
        self.group = ContactGroup.objects.create(owner=self.member, name="Kelas 5")
        self.rina = Contact.objects.create(
            owner=self.member, name="Rina Wati", phone="6281111111111"
        )
        self.dedi = Contact.objects.create(owner=self.member, name="", phone="6282222222222")
        self.stop = Contact.objects.create(
            owner=self.member, name="Sudah Stop", phone="6283333333333", is_opted_out=True
        )
        for contact in (self.rina, self.dedi, self.stop):
            contact.groups.add(self.group)
        self.client.force_login(self.member)

    def make_campaign(self, **kwargs):
        defaults = {
            "name": "Pengingat",
            "body": "Halo {nama_depan}, besok ngaji jam 4.",
            "all_contacts": False,
            "groups": [self.group],
            "wa_groups": [],
        }
        defaults.update(kwargs)
        return services.create_campaign(self.member, **defaults)


class CreateCampaignServiceTests(CampaignTestCase):
    def test_recipients_skip_opt_out_and_personalize(self):
        campaign = self.make_campaign(wa_groups=WA_GROUPS)
        recipients = {r.chat_id: r for r in campaign.recipients.all()}
        self.assertEqual(
            set(recipients), {"6281111111111@c.us", "6282222222222@c.us", "120363@g.us"}
        )
        self.assertEqual(campaign.skipped_opted_out, 1)
        self.assertTrue(recipients["6281111111111@c.us"].text.startswith("Halo Rina,"))
        self.assertIn("Balas STOP", recipients["6281111111111@c.us"].text)
        self.assertTrue(recipients["6282222222222@c.us"].text.startswith("Halo Bapak/Ibu,"))
        group_text = recipients["120363@g.us"].text
        self.assertTrue(group_text.startswith("Halo Wali,"))
        self.assertNotIn("Balas STOP", group_text)

    def test_contact_in_two_groups_only_once(self):
        other = ContactGroup.objects.create(owner=self.member, name="VIP")
        self.rina.groups.add(other)
        campaign = self.make_campaign(groups=[self.group, other])
        self.assertEqual(campaign.recipients.filter(contact=self.rina).count(), 1)


class QuotaTests(CampaignTestCase):
    def test_used_today_counts_sent_today_and_active_pending(self):
        done = self.make_campaign()
        done.status = Campaign.Status.COMPLETED
        done.save()
        done.recipients.update(status=CampaignRecipient.Status.SENT, sent_at=timezone.now())
        old = self.make_campaign()
        old.status = Campaign.Status.COMPLETED
        old.save()
        old.recipients.update(
            status=CampaignRecipient.Status.SENT, sent_at=timezone.now() - timedelta(days=2)
        )
        running = self.make_campaign()
        running.status = Campaign.Status.RUNNING
        running.save()
        self.make_campaign()  # draf tidak dihitung
        self.assertEqual(services.used_today(self.member), 4)
        self.assertEqual(services.remaining_quota(self.member), 96)


class StartCampaignTests(CampaignTestCase):
    def start(self, campaign, remote_status="WORKING"):
        with (
            mock.patch.object(waha, "get_session", return_value={"status": remote_status}),
            mock.patch.object(services, "_post_to_n8n") as post,
        ):
            services.start_campaign(campaign)
        return post

    def test_start_sends_payload_without_secrets(self):
        campaign = self.make_campaign(wa_groups=WA_GROUPS)
        post = self.start(campaign)
        payload = post.call_args.args[0]
        self.assertEqual(payload["session"], self.session.name)
        self.assertEqual(len(payload["recipients"]), 3)
        self.assertEqual(
            payload["callback_url"], "https://sistercreative.tech/api/n8n/kampanye/hasil/"
        )
        self.assertNotIn("kunci-rahasia", json.dumps(payload))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.QUEUED)

    def test_requires_connected_whatsapp(self):
        campaign = self.make_campaign()
        with self.assertRaisesMessage(services.CampaignError, "belum terhubung"):
            self.start(campaign, remote_status="SCAN_QR_CODE")
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_respects_daily_quota(self):
        self.member.daily_message_quota = 1
        self.member.save()
        with self.assertRaisesMessage(services.CampaignError, "Kuota hari ini tersisa 1"):
            self.start(self.make_campaign())

    def test_only_one_active_campaign(self):
        self.start(self.make_campaign())
        with self.assertRaisesMessage(services.CampaignError, "Masih ada kampanye"):
            self.start(self.make_campaign())

    def test_cannot_start_twice(self):
        campaign = self.make_campaign()
        self.start(campaign)
        with self.assertRaisesMessage(services.CampaignError, "sudah pernah dimulai"):
            self.start(campaign)

    @override_settings(N8N_BLAST_WEBHOOK_URL="")
    def test_n8n_not_configured(self):
        campaign = self.make_campaign()
        with (
            mock.patch.object(waha, "get_session", return_value={"status": "WORKING"}),
            self.assertRaisesMessage(services.CampaignError, "belum dikonfigurasi"),
        ):
            services.start_campaign(campaign)


class CallbackTests(CampaignTestCase):
    url = reverse("campaign_callback")

    def setUp(self):
        super().setUp()
        self.campaign = self.make_campaign()
        self.campaign.status = Campaign.Status.QUEUED
        self.campaign.save()
        self.r1, self.r2 = list(self.campaign.recipients.all())

    def post(self, payload, token="token-dari-n8n"):
        return self.client.post(
            self.url, json.dumps(payload), content_type="application/json", HTTP_X_SC_TOKEN=token
        )

    def result(self, recipient, status="sent", **extra):
        return {
            "campaign_id": self.campaign.pk,
            "recipient_id": recipient.pk,
            "status": status,
            **extra,
        }

    def test_rejects_wrong_token(self):
        self.assertEqual(self.post(self.result(self.r1), token="salah").status_code, 403)
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.status, CampaignRecipient.Status.PENDING)

    def test_full_flow_to_completed(self):
        first = self.post(self.result(self.r1, message_id="wamid.1")).json()
        self.assertTrue(first["continue"])
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.RUNNING)
        last = self.post(self.result(self.r2, "failed", error="not on whatsapp")).json()
        self.assertFalse(last["continue"])
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.COMPLETED)
        self.r2.refresh_from_db()
        self.assertEqual(self.r2.error, "not on whatsapp")

    def test_callback_is_idempotent(self):
        self.post(self.result(self.r1))
        self.post(self.result(self.r1, "failed"))
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.status, CampaignRecipient.Status.SENT)

    def test_recipient_from_other_campaign_rejected(self):
        other = self.make_campaign()
        foreign = other.recipients.first()
        response = self.post(self.result(foreign))
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, CampaignRecipient.Status.PENDING)

    def test_cancelled_campaign_tells_n8n_to_stop(self):
        services.cancel_campaign(self.campaign, by=self.member)
        response = self.post(self.result(self.r1)).json()
        self.assertFalse(response["continue"])
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.status, CampaignRecipient.Status.SKIPPED)


class CampaignViewTests(CampaignTestCase):
    def test_create_with_template_and_wa_group(self):
        template = MessageTemplate.objects.create(
            owner=self.member, name="Sapaan", body="Assalamu'alaikum {nama_depan}"
        )
        with mock.patch("apps.campaigns.views.wa_services.whatsapp_groups", return_value=WA_GROUPS):
            response = self.client.post(
                reverse("campaigns:create"),
                {
                    "name": "Info libur",
                    "template": template.pk,
                    "body": "",
                    "wa_groups": ["120363@g.us"],
                },
            )
        campaign = Campaign.objects.get(owner=self.member)
        self.assertRedirects(response, campaign.get_absolute_url())
        self.assertEqual(campaign.body, "Assalamu'alaikum {nama_depan}")
        self.assertEqual(campaign.recipients.get().display_name, "Wali Murid 5A")

    def test_cannot_inject_unknown_wa_group(self):
        with mock.patch("apps.campaigns.views.wa_services.whatsapp_groups", return_value=[]):
            response = self.client.post(
                reverse("campaigns:create"),
                {"name": "X", "body": "Halo", "wa_groups": ["999999@g.us"]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Campaign.objects.exists())

    def test_requires_target(self):
        with mock.patch("apps.campaigns.views.wa_services.whatsapp_groups", return_value=[]):
            response = self.client.post(reverse("campaigns:create"), {"name": "X", "body": "Halo"})
        self.assertContains(response, "Pilih minimal satu tujuan")

    def test_detail_and_other_members_campaign(self):
        campaign = self.make_campaign()
        response = self.client.get(campaign.get_absolute_url())
        self.assertContains(response, "Mulai kirim")
        self.assertContains(response, "Halo Rina")
        other = make_member("budi@contoh.id")
        self.client.force_login(other)
        for name in ["campaigns:detail", "campaigns:progress"]:
            self.assertEqual(self.client.get(reverse(name, args=[campaign.pk])).status_code, 404)
        for name in ["campaigns:start", "campaigns:cancel"]:
            self.assertEqual(self.client.post(reverse(name, args=[campaign.pk])).status_code, 404)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_start_view_shows_error_message(self):
        campaign = self.make_campaign()
        with mock.patch.object(waha, "get_session", return_value={"status": "SCAN_QR_CODE"}):
            response = self.client.post(reverse("campaigns:start", args=[campaign.pk]), follow=True)
        self.assertContains(response, "belum terhubung")

    def test_progress_json(self):
        campaign = self.make_campaign()
        data = self.client.get(reverse("campaigns:progress", args=[campaign.pk])).json()
        self.assertEqual((data["total"], data["pending"], data["percent"]), (2, 2, 0))


class AdminCampaignTests(CampaignTestCase):
    def test_admin_can_cancel_any_campaign(self):
        campaign = self.make_campaign()
        admin = User.objects.create_superuser(
            email="admin@sistercreative.tech", password=PASSWORD, full_name="Admin"
        )
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse("dashboard:campaign_list")), "Pengingat")
        self.client.post(reverse("dashboard:campaign_cancel", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.CANCELLED)
        self.assertEqual(campaign.cancelled_by, admin)

    def test_member_cannot_use_admin_cancel(self):
        campaign = self.make_campaign()
        response = self.client.post(reverse("dashboard:campaign_cancel", args=[campaign.pk]))
        self.assertEqual(response.status_code, 403)


class DeleteCampaignTests(CampaignTestCase):
    def test_confirm_page_and_delete_hides_campaign(self):
        campaign = self.make_campaign()
        url = reverse("campaigns:delete", args=[campaign.pk])
        self.assertContains(self.client.get(url), "Hapus kampanye")
        self.assertRedirects(self.client.post(url), reverse("campaigns:list"))
        campaign.refresh_from_db()
        self.assertIsNotNone(campaign.deleted_at)
        self.assertNotContains(self.client.get(reverse("campaigns:list")), "Pengingat")
        self.assertEqual(self.client.get(campaign.get_absolute_url()).status_code, 404)

    def test_deleting_queued_campaign_cancels_it_and_stops_n8n(self):
        campaign = self.make_campaign()
        campaign.status = Campaign.Status.QUEUED
        campaign.save()
        warning = self.client.get(reverse("campaigns:delete", args=[campaign.pk]))
        self.assertContains(warning, "akan dihentikan")
        self.client.post(reverse("campaigns:delete", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.CANCELLED)
        self.assertFalse(
            campaign.recipients.filter(status=CampaignRecipient.Status.PENDING).exists()
        )
        recipient = campaign.recipients.first()
        result = services.record_result(
            {"campaign_id": campaign.pk, "recipient_id": recipient.pk, "status": "sent"}
        )
        self.assertFalse(result["continue"])

    def test_deleted_campaign_still_counts_toward_quota(self):
        campaign = self.make_campaign()
        campaign.status = Campaign.Status.COMPLETED
        campaign.save()
        campaign.recipients.update(status=CampaignRecipient.Status.SENT, sent_at=timezone.now())
        before = services.used_today(self.member)
        services.delete_campaign(campaign, by=self.member)
        self.assertEqual(services.used_today(self.member), before)
        self.assertEqual(before, 2)

    def test_cannot_delete_other_members_campaign(self):
        campaign = self.make_campaign()
        self.client.force_login(make_member("budi@contoh.id"))
        url = reverse("campaigns:delete", args=[campaign.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        campaign.refresh_from_db()
        self.assertIsNone(campaign.deleted_at)

    def test_delete_requires_post(self):
        campaign = self.make_campaign()
        self.client.get(reverse("campaigns:delete", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertIsNone(campaign.deleted_at)

    def test_admin_still_sees_deleted_campaign(self):
        campaign = self.make_campaign()
        services.delete_campaign(campaign, by=self.member)
        admin = User.objects.create_superuser(
            email="admin@sistercreative.tech", password=PASSWORD, full_name="Admin"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("dashboard:campaign_list"))
        self.assertContains(response, "Pengingat")
        self.assertContains(response, "Dihapus member")
