import json
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core import n8n

from . import services
from .forms import EmailCampaignForm
from .models import EmailCampaign, EmailRecipient, MailingList, Subscriber
from .rendering import render_email

PASSWORD = "Rahasia-Kuat-2026!"
SETTINGS = {
    "N8N_EMAIL_WEBHOOK_URL": "https://n8n.contoh.test/webhook/email",
    "N8N_BLAST_TOKEN": "token-ke-n8n",
    "N8N_CALLBACK_TOKEN": "token-dari-n8n",
    "SITE_URL": "https://sistercreative.tech",
    "EMAIL_BLAST_DAILY_LIMIT": 300,
    "EMAIL_BLAST_BATCH_SIZE": 20,
}
TOKEN = {"HTTP_X_SC_TOKEN": "token-dari-n8n"}


def csv_file(text: str, name="pelanggan.csv"):
    return SimpleUploadedFile(name, text.encode(), content_type="text/csv")


class MailingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@sistercreative.tech", password=PASSWORD, full_name="Admin Sister"
        )
        cls.member = User.objects.create_user(
            email="dedi@contoh.id",
            password=PASSWORD,
            full_name="Dedi Kurniawan",
            whatsapp_number="6282222222222",
            status=User.Status.ACTIVE,
        )
        cls.remote = MailingList.objects.create(name="Pendaftar Remote Journal")
        cls.other_list = MailingList.objects.create(name="Klien website")
        cls.rina = Subscriber.objects.create(email="rina@contoh.id", name="Rina Wulandari")
        cls.rina.lists.add(cls.remote)
        cls.budi = Subscriber.objects.create(email="budi@contoh.id", name="Budi Santoso")
        cls.budi.lists.add(cls.remote)
        cls.sari = Subscriber.objects.create(email="sari@contoh.id", name="Sari")
        cls.sari.lists.add(cls.other_list)
        cls.gone = Subscriber.objects.create(
            email="gone@contoh.id", status=Subscriber.Status.UNSUBSCRIBED
        )
        cls.gone.lists.add(cls.remote)

    def make_campaign(self, **kwargs):
        lists = kwargs.pop("lists", [self.remote])
        defaults = {
            "name": "Follow-up Remote Journal",
            "subject": "Halo {nama_depan}, ini dari Dila",
            "body": "Hai {nama}!\n\nGabung grupnya ya: https://chat.whatsapp.com/abc",
            "button_label": "Gabung grup",
            "button_url": "https://chat.whatsapp.com/abc",
        }
        defaults.update(kwargs)
        campaign = EmailCampaign.objects.create(**defaults)
        campaign.lists.set(lists)
        return campaign


class RenderingTests(MailingTestCase):
    def test_personalizes_and_escapes_body(self):
        campaign = self.make_campaign(body="Halo {nama}\n\n<script>alert(1)</script>")
        email = render_email(campaign, name="Rina Wulandari", unsubscribe_url="https://x.test/u")
        self.assertEqual(email.subject, "Halo Rina, ini dari Dila")
        self.assertIn("Halo Rina Wulandari", email.html)
        self.assertNotIn("<script>", email.html)
        self.assertIn("&lt;script&gt;", email.html)
        self.assertIn("https://x.test/u", email.html)
        self.assertIn("https://x.test/u", email.text)
        self.assertIn("Gabung grup", email.html)

    def test_links_become_clickable(self):
        campaign = self.make_campaign(body="Daftar di https://sistercreative.tech/daftar")
        email = render_email(campaign, name="", unsubscribe_url="https://x.test/u")
        self.assertIn('href="https://sistercreative.tech/daftar"', email.html)
        self.assertIn(
            "Bapak/Ibu",
            render_email(
                self.make_campaign(subject="Halo {nama}"), name="", unsubscribe_url="u"
            ).subject,
        )


class FormTests(MailingTestCase):
    def data(self, **overrides):
        data = {
            "name": "Promo",
            "subject": "Halo {nama}",
            "body": "Isi email",
            "button_label": "",
            "button_url": "",
            "lists": [self.remote.pk],
            "skip_recent_days": 0,
        }
        data.update(overrides)
        return data

    def test_valid(self):
        self.assertTrue(EmailCampaignForm(self.data()).is_valid())

    def test_rejects_unknown_variable(self):
        form = EmailCampaignForm(self.data(body="Halo {nomor}"))
        self.assertFalse(form.is_valid())
        self.assertIn("{nomor}", str(form.non_field_errors()))

    def test_button_needs_label_and_url(self):
        form = EmailCampaignForm(self.data(button_label="Klik"))
        self.assertFalse(form.is_valid())

    def test_needs_target(self):
        self.assertFalse(EmailCampaignForm(self.data(lists=[])).is_valid())
        self.assertTrue(EmailCampaignForm(self.data(lists=[], send_to_all="on")).is_valid())


@override_settings(**SETTINGS)
class StartCampaignTests(MailingTestCase):
    def test_snapshots_subscribed_members_of_lists(self):
        campaign = self.make_campaign()
        self.assertEqual(services.start_campaign(campaign), 2)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.SENDING)
        emails = set(campaign.recipients.values_list("email", flat=True))
        self.assertEqual(emails, {"rina@contoh.id", "budi@contoh.id"})

    def test_send_to_all_without_duplicates(self):
        self.sari.lists.add(self.remote)
        campaign = self.make_campaign(send_to_all=True, lists=[])
        self.assertEqual(services.start_campaign(campaign), 3)

    def test_skips_recently_emailed(self):
        Subscriber.objects.filter(pk=self.rina.pk).update(
            last_emailed_at=timezone.now() - timedelta(days=2)
        )
        campaign = self.make_campaign(skip_recent_days=7)
        self.assertEqual(services.start_campaign(campaign), 1)

    def test_cannot_start_twice_or_without_webhook(self):
        campaign = self.make_campaign()
        services.start_campaign(campaign)
        with self.assertRaises(services.MailingError):
            services.start_campaign(campaign)
        with (
            override_settings(N8N_EMAIL_WEBHOOK_URL=""),
            self.assertRaises(services.MailingError),
        ):
            services.start_campaign(self.make_campaign())

    def test_no_target(self):
        with self.assertRaises(services.MailingError):
            services.start_campaign(self.make_campaign(lists=[]))


@override_settings(**SETTINGS)
class DispatchTests(MailingTestCase):
    def setUp(self):
        self.post_job = mock.patch.object(n8n, "post_job").start()
        self.addCleanup(mock.patch.stopall)
        self.campaign = self.make_campaign()
        services.start_campaign(self.campaign)

    def test_posts_batch_and_marks_queued(self):
        result = services.dispatch_due()
        self.assertEqual(result["queued"], 2)
        url, payload = self.post_job.call_args.args
        self.assertEqual(url, SETTINGS["N8N_EMAIL_WEBHOOK_URL"])
        self.assertEqual(payload["campaign_id"], self.campaign.pk)
        self.assertEqual(
            payload["callback_url"], "https://sistercreative.tech/api/n8n/email/hasil/"
        )
        first = payload["recipients"][0]
        self.assertEqual(first["to"], "rina@contoh.id")
        self.assertEqual(first["subject"], "Halo Rina, ini dari Dila")
        self.assertIn(
            f"https://sistercreative.tech/email/berhenti/{self.rina.token}/", first["html"]
        )
        self.assertEqual(
            self.campaign.recipients.filter(status=EmailRecipient.Status.QUEUED).count(), 2
        )

    def test_waits_while_batch_in_flight(self):
        services.dispatch_due()
        result = services.dispatch_due()
        self.assertTrue(result["busy"])
        self.assertEqual(self.post_job.call_count, 1)

    def test_respects_batch_size_and_daily_limit(self):
        with override_settings(EMAIL_BLAST_BATCH_SIZE=1):
            self.assertEqual(services.dispatch_due()["queued"], 1)
        EmailRecipient.objects.update(status=EmailRecipient.Status.PENDING, queued_at=None)
        with override_settings(EMAIL_BLAST_DAILY_LIMIT=0):
            self.assertEqual(services.dispatch_due()["queued"], 0)

    def test_skips_who_unsubscribed_after_start(self):
        services.unsubscribe(self.budi)
        result = services.dispatch_due()
        self.assertEqual(result["queued"], 1)
        self.assertEqual(result["skipped"], 1)

    def test_rolls_back_when_n8n_fails(self):
        self.post_job.side_effect = n8n.N8nError("n8n tidak bisa dihubungi")
        result = services.dispatch_due()
        self.assertEqual(result["queued"], 0)
        self.assertFalse(
            self.campaign.recipients.exclude(status=EmailRecipient.Status.PENDING).exists()
        )

    def test_expires_stale_queue_and_completes(self):
        services.dispatch_due()
        later = timezone.now() + timedelta(hours=2)
        result = services.dispatch_due(now=later)
        self.assertEqual(result["expired"], 2)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, EmailCampaign.Status.COMPLETED)

    def test_cancel_skips_pending(self):
        services.cancel_campaign(self.campaign)
        self.assertEqual(services.dispatch_due()["queued"], 0)
        self.assertEqual(
            self.campaign.recipients.filter(status=EmailRecipient.Status.SKIPPED).count(), 2
        )


@override_settings(**SETTINGS)
class CallbackTests(MailingTestCase):
    def setUp(self):
        self.post_job = mock.patch.object(n8n, "post_job").start()
        self.addCleanup(mock.patch.stopall)
        self.campaign = self.make_campaign()
        services.start_campaign(self.campaign)
        services.dispatch_due()
        self.first, self.second = self.campaign.recipients.order_by("pk")

    def post(self, payload, headers=TOKEN):
        return self.client.post(
            reverse("mailing_callback"),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_requires_token(self):
        response = self.post({"recipient_id": self.first.pk}, headers={})
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("mailing_dispatch"))
        self.assertEqual(response.status_code, 403)

    def test_records_sent_and_completes(self):
        payload = {"campaign_id": self.campaign.pk, "recipient_id": self.first.pk, "status": "sent"}
        self.assertTrue(self.post(payload).json()["continue"])
        self.rina.refresh_from_db()
        self.assertIsNotNone(self.rina.last_emailed_at)
        payload = {
            "campaign_id": self.campaign.pk,
            "recipient_id": self.second.pk,
            "status": "failed",
            "error": "SMTP 550",
        }
        self.assertFalse(self.post(payload).json()["continue"])
        self.second.refresh_from_db()
        self.assertEqual(self.second.error, "SMTP 550")
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, EmailCampaign.Status.COMPLETED)

    def test_stops_after_cancel(self):
        services.cancel_campaign(self.campaign)
        payload = {"campaign_id": self.campaign.pk, "recipient_id": self.first.pk, "status": "sent"}
        self.assertFalse(self.post(payload).json()["continue"])

    def test_test_email_and_unknown_recipient(self):
        self.assertFalse(self.post({"recipient_id": 0, "status": "sent"}).json()["continue"])
        response = self.post({"campaign_id": 999, "recipient_id": self.first.pk, "status": "sent"})
        self.assertEqual(response.status_code, 404)

    def test_dispatch_endpoint(self):
        response = self.client.post(reverse("mailing_dispatch"), **TOKEN)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["busy"])


class ImportTests(MailingTestCase):
    def test_imports_sheet_with_history(self):
        raw = (
            b"name,email,updated\n"
            b"Ani,ANI@Contoh.id,2026-11-10 08:12:10\n"
            b"Ani lagi,ani@contoh.id,\n"
            b"Rina W,rina@contoh.id,\n"
            b",bukan-email,\n"
            b"Gone,gone@contoh.id,\n"
        )
        new_list = MailingList.objects.create(name="Sheet gmail blast")
        result = services.import_subscribers(raw, mailing_list=new_list)
        self.assertEqual((result.created, result.existing), (1, 2))
        self.assertEqual(result.duplicates_in_file, 1)
        self.assertEqual(result.invalid_count, 1)
        ani = Subscriber.objects.get(email="ani@contoh.id")
        self.assertEqual(timezone.localdate(ani.last_emailed_at).isoformat(), "2026-11-10")
        self.assertIn(new_list, ani.lists.all())
        self.rina.refresh_from_db()
        self.assertEqual(self.rina.name, "Rina Wulandari")
        self.gone.refresh_from_db()
        self.assertFalse(self.gone.is_subscribed)

    def test_requires_email_column(self):
        with self.assertRaises(services.ImportFileError):
            services.import_subscribers(b"nama,nomor\nAni,0812\n")


@override_settings(**SETTINGS)
class DashboardViewTests(MailingTestCase):
    def setUp(self):
        self.client.force_login(self.admin)
        self.post_job = mock.patch.object(n8n, "post_job").start()
        self.addCleanup(mock.patch.stopall)

    def test_only_staff(self):
        campaign = self.make_campaign()
        urls = [
            reverse("mailing:campaign_list"),
            reverse("mailing:campaign_create"),
            reverse("mailing:campaign_detail", args=[campaign.pk]),
            reverse("mailing:campaign_preview", args=[campaign.pk]),
            reverse("mailing:subscriber_list"),
            reverse("mailing:subscriber_import"),
            reverse("mailing:subscriber_sample"),
        ]
        self.client.force_login(self.member)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(
            self.client.post(reverse("mailing:campaign_start", args=[campaign.pk])).status_code,
            403,
        )
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_pages_render(self):
        campaign = self.make_campaign()
        for url in [
            reverse("mailing:campaign_list"),
            reverse("mailing:campaign_create"),
            reverse("mailing:campaign_detail", args=[campaign.pk]),
            reverse("mailing:subscriber_list") + "?q=rina&status=subscribed",
            reverse("mailing:subscriber_create"),
            reverse("mailing:subscriber_import"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        preview = self.client.get(reverse("mailing:campaign_preview", args=[campaign.pk]))
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(preview, "Rina Wulandari")

    def test_create_start_and_cancel_flow(self):
        response = self.client.post(
            reverse("mailing:campaign_create"),
            {
                "name": "Promo Desember",
                "subject": "Halo {nama_depan}",
                "body": "Ada promo website akhir tahun.",
                "lists": [self.remote.pk],
                "skip_recent_days": 0,
            },
        )
        campaign = EmailCampaign.objects.get(name="Promo Desember")
        self.assertRedirects(response, campaign.get_absolute_url())
        self.assertEqual(campaign.created_by, self.admin)
        self.client.post(reverse("mailing:campaign_start", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertTrue(campaign.is_sending)
        # Kampanye berjalan tidak bisa diubah atau dihapus.
        update_url = reverse("mailing:campaign_update", args=[campaign.pk])
        self.assertEqual(self.client.get(update_url).status_code, 404)
        self.client.post(reverse("mailing:campaign_delete", args=[campaign.pk]))
        self.assertTrue(EmailCampaign.objects.filter(pk=campaign.pk).exists())
        self.client.post(reverse("mailing:campaign_cancel", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.CANCELLED)

    def test_send_test_email(self):
        campaign = self.make_campaign()
        self.client.post(
            reverse("mailing:campaign_test", args=[campaign.pk]), {"email": "uji@contoh.id"}
        )
        payload = self.post_job.call_args.args[1]
        self.assertEqual(payload["recipients"][0]["recipient_id"], 0)
        self.assertEqual(payload["recipients"][0]["to"], "uji@contoh.id")
        self.assertTrue(payload["recipients"][0]["subject"].startswith("[UJI]"))
        self.assertFalse(campaign.recipients.exists())

    def test_import_view(self):
        response = self.client.post(
            reverse("mailing:subscriber_import"),
            {"file": csv_file("nama;email\nAni;ani@contoh.id\n"), "new_list_name": "Webinar"},
        )
        webinar = MailingList.objects.get(name="Webinar")
        self.assertRedirects(response, reverse("mailing:subscriber_list") + f"?daftar={webinar.pk}")
        self.assertTrue(webinar.subscribers.filter(email="ani@contoh.id").exists())

    def test_add_unsubscribe_and_delete_subscriber(self):
        self.client.post(
            reverse("mailing:subscriber_create"), {"email": "Baru@Contoh.id", "name": "Baru"}
        )
        new = Subscriber.objects.get(email="baru@contoh.id")
        duplicate = self.client.post(
            reverse("mailing:subscriber_create"), {"email": "baru@contoh.id"}
        )
        self.assertContains(duplicate, "sudah terdaftar")
        self.client.post(reverse("mailing:subscriber_unsubscribe", args=[new.pk]))
        new.refresh_from_db()
        self.assertFalse(new.is_subscribed)
        self.client.post(reverse("mailing:subscriber_delete", args=[new.pk]))
        self.assertFalse(Subscriber.objects.filter(pk=new.pk).exists())


class UnsubscribeTests(MailingTestCase):
    def test_confirm_then_unsubscribe(self):
        url = reverse("mailing_unsubscribe", args=[self.rina.token])
        self.assertContains(self.client.get(url), "Berhenti menerima email?")
        self.rina.refresh_from_db()
        self.assertTrue(self.rina.is_subscribed)
        response = self.client.post(url)
        self.assertContains(response, "sudah berhenti berlangganan")
        self.rina.refresh_from_db()
        self.assertFalse(self.rina.is_subscribed)

    def test_unknown_token(self):
        url = reverse("mailing_unsubscribe", args=["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(self.client.get(url).status_code, 404)
