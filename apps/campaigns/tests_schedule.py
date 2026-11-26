"""Test gambar kampanye, penjadwalan, dan pemicu kampanye terjadwal."""

import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.whatsapp import waha

from . import services
from .images import prepare_image
from .models import Campaign, CampaignRecipient
from .tests import CampaignTestCase, make_member

MEDIA_ROOT = tempfile.mkdtemp()


def image_upload(size=(3000, 2000), fmt="PNG", name="promo.png", mode="RGBA", exif=None):
    buffer = BytesIO()
    color = (109, 40, 217, 255) if mode == "RGBA" else (109, 40, 217)
    image = Image.new(mode, size, color)
    kwargs = {"exif": exif} if exif else {}
    image.save(buffer, format=fmt, **kwargs)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class PrepareImageTests(TestCase):
    def test_resizes_and_converts_to_jpeg(self):
        result = prepare_image(image_upload())
        with Image.open(BytesIO(result.read())) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertLessEqual(max(image.size), 1600)

    def test_strips_exif(self):
        exif = Image.Exif()
        exif[0x010F] = "Kamera Rahasia"
        upload = image_upload(size=(800, 600), fmt="JPEG", name="foto.jpg", mode="RGB", exif=exif)
        result = prepare_image(upload)
        with Image.open(BytesIO(result.read())) as image:
            self.assertEqual(len(image.getexif()), 0)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CampaignImageTests(CampaignTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def post_create(self, **extra):
        data = {
            "name": "Promo",
            "body": "Diskon untuk {nama_depan}",
            "contact_groups": [self.group.pk],
        }
        data.update(extra)
        with mock.patch("apps.campaigns.views.wa_services.whatsapp_groups", return_value=[]):
            return self.client.post(reverse("campaigns:create"), data)

    def test_create_with_image_and_payload_has_public_url(self):
        response = self.post_create(image=image_upload())
        campaign = Campaign.objects.get(owner=self.member)
        self.assertRedirects(response, campaign.get_absolute_url())
        self.assertTrue(campaign.image.name.startswith("campaigns/"))
        self.assertTrue(campaign.image.name.endswith(".jpg"))
        self.assertNotIn("promo", campaign.image.name)
        payload = services.build_payload(campaign, self.session)
        self.assertEqual(payload["image_url"], f"https://sistercreative.tech{campaign.image.url}")
        self.assertContains(self.client.get(campaign.get_absolute_url()), campaign.image.url)

    def test_payload_without_image_is_empty_string(self):
        campaign = self.make_campaign()
        self.assertEqual(services.build_payload(campaign, self.session)["image_url"], "")

    def test_caption_limit_with_image(self):
        response = self.post_create(body="a" * 901, image=image_upload())
        self.assertContains(response, "maksimal 900 karakter")
        self.assertFalse(Campaign.objects.exists())

    def test_rejects_fake_image(self):
        fake = SimpleUploadedFile("promo.png", b"bukan gambar", content_type="image/png")
        response = self.post_create(image=fake)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Campaign.objects.exists())


class ScheduleTests(CampaignTestCase):
    def schedule_url(self, campaign):
        return reverse("campaigns:schedule", args=[campaign.pk])

    def when(self, **delta):
        return (timezone.localtime() + timedelta(**delta)).strftime("%Y-%m-%dT%H:%M")

    def test_schedule_and_unschedule(self):
        campaign = self.make_campaign()
        self.client.post(self.schedule_url(campaign), {"scheduled_at": self.when(hours=2)})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.SCHEDULED)
        self.assertIsNotNone(campaign.scheduled_at)
        self.assertContains(self.client.get(campaign.get_absolute_url()), "Batalkan jadwal")
        self.client.post(reverse("campaigns:unschedule", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertIsNone(campaign.scheduled_at)

    def test_schedule_bounds(self):
        campaign = self.make_campaign()
        too_soon = self.client.post(
            self.schedule_url(campaign), {"scheduled_at": self.when(minutes=1)}, follow=True
        )
        self.assertContains(too_soon, "minimal 5 menit")
        too_late = self.client.post(
            self.schedule_url(campaign), {"scheduled_at": self.when(days=31)}, follow=True
        )
        self.assertContains(too_late, "maksimal 30 hari")
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_cannot_schedule_other_members_campaign(self):
        campaign = self.make_campaign()
        self.client.force_login(make_member("budi@contoh.id"))
        response = self.client.post(
            self.schedule_url(campaign), {"scheduled_at": self.when(hours=2)}
        )
        self.assertEqual(response.status_code, 404)


class DispatchTests(CampaignTestCase):
    def due_campaign(self, minutes_ago=1):
        campaign = self.make_campaign()
        campaign.status = Campaign.Status.SCHEDULED
        campaign.scheduled_at = timezone.now() - timedelta(minutes=minutes_ago)
        campaign.save()
        return campaign

    def dispatch(self, remote_status="WORKING"):
        with (
            mock.patch.object(waha, "get_session", return_value={"status": remote_status}),
            mock.patch.object(services, "_post_to_n8n") as post,
        ):
            result = services.dispatch_due_campaigns()
        return result, post

    def test_starts_due_campaign_only(self):
        due = self.due_campaign()
        future = self.make_campaign()
        future.status = Campaign.Status.SCHEDULED
        future.scheduled_at = timezone.now() + timedelta(hours=1)
        future.save()
        result, post = self.dispatch()
        self.assertEqual(result, {"started": 1, "deferred": 0, "failed": 0})
        post.assert_called_once()
        due.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(due.status, Campaign.Status.QUEUED)
        self.assertEqual(future.status, Campaign.Status.SCHEDULED)

    def test_opt_out_since_creation_is_skipped(self):
        due = self.due_campaign()
        self.rina.is_opted_out = True
        self.rina.save()
        _, post = self.dispatch()
        chat_ids = [r["chat_id"] for r in post.call_args.args[0]["recipients"]]
        self.assertNotIn("6281111111111@c.us", chat_ids)
        skipped = due.recipients.filter(status=CampaignRecipient.Status.SKIPPED).count()
        self.assertEqual(skipped, 1)

    def test_busy_is_deferred_then_fails_after_grace(self):
        running = self.make_campaign()
        running.status = Campaign.Status.RUNNING
        running.save()
        due = self.due_campaign(minutes_ago=10)
        result, _ = self.dispatch()
        self.assertEqual(result["deferred"], 1)
        due.refresh_from_db()
        self.assertEqual(due.status, Campaign.Status.SCHEDULED)
        due.scheduled_at = timezone.now() - timedelta(minutes=121)
        due.save()
        result, _ = self.dispatch()
        self.assertEqual(result["failed"], 1)
        due.refresh_from_db()
        self.assertEqual(due.status, Campaign.Status.FAILED)
        self.assertIn("2 jam", due.error)

    def test_disconnected_whatsapp_fails_with_message(self):
        due = self.due_campaign()
        result, post = self.dispatch(remote_status="SCAN_QR_CODE")
        self.assertEqual(result["failed"], 1)
        post.assert_not_called()
        due.refresh_from_db()
        self.assertEqual(due.status, Campaign.Status.FAILED)
        self.assertIn("belum terhubung", due.error)
        pending = due.recipients.filter(status=CampaignRecipient.Status.PENDING)
        self.assertFalse(pending.exists())
        self.assertContains(self.client.get(due.get_absolute_url()), "Gagal dimulai")

    def test_deleted_scheduled_campaign_not_started(self):
        due = self.due_campaign()
        services.delete_campaign(due, by=self.member)
        result, post = self.dispatch()
        self.assertEqual(result["started"], 0)
        post.assert_not_called()

    def test_dispatch_endpoint_requires_token(self):
        url = reverse("campaign_dispatch")
        self.assertEqual(self.client.post(url).status_code, 403)
        empty = {"started": 0, "deferred": 0, "failed": 0}
        with mock.patch.object(services, "dispatch_due_campaigns", return_value=empty):
            response = self.client.post(url, HTTP_X_SC_TOKEN="token-dari-n8n")
        self.assertTrue(response.json()["ok"])
