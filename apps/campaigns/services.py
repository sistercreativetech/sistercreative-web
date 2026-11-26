"""Logika kampanye: penerima, kuota, kirim ke n8n, dan status dari n8n."""

import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.contacts.messages import render_message
from apps.contacts.models import Contact
from apps.core import n8n
from apps.whatsapp import services as wa_services
from apps.whatsapp import waha
from apps.whatsapp.models import WhatsAppSession

from .models import Campaign, CampaignRecipient

logger = logging.getLogger(__name__)

Recipient = CampaignRecipient


class CampaignError(Exception):
    """Kesalahan yang aman ditampilkan ke member."""


class CampaignBusy(CampaignError):
    """Masih ada kampanye lain milik member yang sedang berjalan."""


# --- Kuota ----------------------------------------------------------------------


def start_of_today():
    today = timezone.localdate()
    return timezone.make_aware(datetime.combine(today, time.min))


def used_today(owner) -> int:
    """Pesan terkirim hari ini + pesan yang masih antre di kampanye aktif."""
    return (
        Recipient.objects.filter(campaign__owner=owner)
        .filter(
            Q(status=Recipient.Status.SENT, sent_at__gte=start_of_today())
            | Q(status=Recipient.Status.PENDING, campaign__status__in=Campaign.ACTIVE_STATUSES)
        )
        .count()
    )


def remaining_quota(owner) -> int:
    return max(owner.daily_message_quota - used_today(owner), 0)


# --- Penerima -------------------------------------------------------------------


def target_contacts(owner, *, all_contacts: bool, groups) -> tuple[list[Contact], int]:
    """Kontak tujuan (unik) dan jumlah kontak opt-out yang dilewati."""
    queryset = Contact.objects.filter(owner=owner)
    if not all_contacts:
        queryset = queryset.filter(groups__in=groups).distinct()
    contacts = list(queryset.order_by("pk"))
    allowed = [c for c in contacts if not c.is_opted_out]
    return allowed, len(contacts) - len(allowed)


@transaction.atomic
def create_campaign(owner, *, name, body, all_contacts, groups, wa_groups, image=None) -> Campaign:
    """Buat draf beserta penerimanya. `image` = ContentFile hasil images.prepare_image."""
    contacts, skipped = target_contacts(owner, all_contacts=all_contacts, groups=groups)
    campaign = Campaign.objects.create(
        owner=owner,
        name=name,
        body=body,
        send_to_all_contacts=all_contacts,
        skipped_opted_out=skipped,
        image=image,
    )
    campaign.contact_groups.set(groups)

    footer = settings.OPT_OUT_FOOTER
    recipients = [
        Recipient(
            campaign=campaign,
            kind=Recipient.Kind.CONTACT,
            contact=contact,
            chat_id=f"{contact.phone}@c.us",
            display_name=contact.name,
            text=render_message(body, name=contact.name, phone=contact.phone) + footer,
        )
        for contact in contacts
    ]
    recipients += [
        Recipient(
            campaign=campaign,
            kind=Recipient.Kind.WA_GROUP,
            chat_id=group["id"],
            display_name=group["name"][:120],
            text=render_message(body, name=group["name"]),
        )
        for group in wa_groups
    ]
    Recipient.objects.bulk_create(recipients)
    return campaign


# --- Mulai / kirim ke n8n -----------------------------------------------------------


def _post_to_n8n(payload: dict) -> None:
    try:
        n8n.post_job(settings.N8N_BLAST_WEBHOOK_URL, payload)
    except n8n.N8nNotConfigured as exc:
        raise CampaignError("Layanan pengiriman belum dikonfigurasi. Hubungi admin.") from exc
    except n8n.N8nError as exc:
        raise CampaignError("Layanan pengiriman sedang tidak bisa dihubungi. Coba lagi.") from exc


def build_payload(campaign: Campaign, session: WhatsAppSession) -> dict:
    pending = campaign.recipients.filter(status=Recipient.Status.PENDING)
    return {
        "campaign_id": campaign.pk,
        "session": session.name,
        "delay_seconds": {"min": settings.BLAST_DELAY_MIN, "max": settings.BLAST_DELAY_MAX},
        "callback_url": settings.SITE_URL.rstrip("/") + reverse("campaign_callback"),
        "image_url": (settings.SITE_URL.rstrip("/") + campaign.image.url) if campaign.image else "",
        "recipients": [
            {"recipient_id": r.pk, "chat_id": r.chat_id, "text": r.text}
            for r in pending.only("pk", "chat_id", "text")
        ],
    }


def skip_opted_out(campaign: Campaign) -> int:
    """Lewati kontak yang berhenti berlangganan sejak kampanye dibuat."""
    return campaign.recipients.filter(
        status=Recipient.Status.PENDING, contact__is_opted_out=True
    ).update(status=Recipient.Status.SKIPPED, error="Berhenti berlangganan")


def start_campaign(campaign: Campaign) -> Campaign:
    owner = campaign.owner
    if not campaign.can_be_started:
        raise CampaignError("Kampanye ini sudah pernah dimulai.")
    skip_opted_out(campaign)
    pending = campaign.recipients.filter(status=Recipient.Status.PENDING).count()
    if not pending:
        raise CampaignError("Tidak ada penerima untuk dikirimi.")
    if Campaign.objects.filter(owner=owner, status__in=Campaign.ACTIVE_STATUSES).exists():
        raise CampaignBusy("Masih ada kampanye yang sedang berjalan. Tunggu sampai selesai.")
    if pending > remaining_quota(owner):
        raise CampaignError(
            f"Kuota hari ini tersisa {remaining_quota(owner)} pesan, "
            f"sedangkan kampanye ini butuh {pending}."
        )

    session = WhatsAppSession.objects.filter(owner=owner).first()
    try:
        if session:
            session = wa_services.refresh_status(session)
    except waha.WahaError as exc:
        raise CampaignError("Server WhatsApp sedang tidak bisa dihubungi. Coba lagi.") from exc
    if not session or not session.is_connected:
        raise CampaignError("WhatsApp Anda belum terhubung. Scan QR di menu WhatsApp dulu.")

    _post_to_n8n(build_payload(campaign, session))
    campaign.status = Campaign.Status.QUEUED
    campaign.started_at = timezone.now()
    campaign.error = ""
    campaign.save(update_fields=["status", "started_at", "error"])
    return campaign


# --- Jadwal ----------------------------------------------------------------------


def schedule_campaign(campaign: Campaign, when) -> Campaign:
    if campaign.status not in {Campaign.Status.DRAFT, Campaign.Status.SCHEDULED}:
        raise CampaignError("Hanya draf yang bisa dijadwalkan.")
    now = timezone.now()
    earliest = now + timedelta(minutes=settings.CAMPAIGN_SCHEDULE_MIN_MINUTES)
    latest = now + timedelta(days=settings.CAMPAIGN_SCHEDULE_MAX_DAYS)
    if when < earliest:
        raise CampaignError(
            f"Jadwal minimal {settings.CAMPAIGN_SCHEDULE_MIN_MINUTES} menit dari sekarang."
        )
    if when > latest:
        raise CampaignError(f"Jadwal maksimal {settings.CAMPAIGN_SCHEDULE_MAX_DAYS} hari ke depan.")
    if not campaign.recipients.filter(status=Recipient.Status.PENDING).exists():
        raise CampaignError("Tidak ada penerima untuk dikirimi.")
    campaign.status = Campaign.Status.SCHEDULED
    campaign.scheduled_at = when
    campaign.error = ""
    campaign.save(update_fields=["status", "scheduled_at", "error"])
    return campaign


def unschedule_campaign(campaign: Campaign) -> Campaign:
    if campaign.status != Campaign.Status.SCHEDULED:
        raise CampaignError("Kampanye ini tidak sedang terjadwal.")
    campaign.status = Campaign.Status.DRAFT
    campaign.scheduled_at = None
    campaign.save(update_fields=["status", "scheduled_at"])
    return campaign


@transaction.atomic
def fail_campaign(campaign: Campaign, message: str) -> Campaign:
    campaign.recipients.filter(status=Recipient.Status.PENDING).update(
        status=Recipient.Status.SKIPPED, error="Kampanye gagal dimulai"
    )
    campaign.status = Campaign.Status.FAILED
    campaign.error = message[:500]
    campaign.finished_at = timezone.now()
    campaign.save(update_fields=["status", "error", "finished_at"])
    return campaign


def dispatch_due_campaigns(now=None) -> dict:
    """Dipanggil n8n tiap menit: mulai kampanye terjadwal yang sudah jatuh tempo."""
    now = now or timezone.now()
    grace = timedelta(minutes=settings.CAMPAIGN_SCHEDULE_GRACE_MINUTES)
    result = {"started": 0, "deferred": 0, "failed": 0}
    due = Campaign.objects.filter(
        status=Campaign.Status.SCHEDULED,
        scheduled_at__lte=now,
        deleted_at__isnull=True,
    ).order_by("scheduled_at", "pk")
    for pk in list(due.values_list("pk", flat=True)):
        try:
            with transaction.atomic():
                # Kunci baris agar panggilan pemicu yang tumpang-tindih tidak memulai dua kali.
                campaign = Campaign.objects.select_for_update().get(pk=pk)
                if campaign.status != Campaign.Status.SCHEDULED:
                    continue
                start_campaign(campaign)
        except CampaignBusy as exc:
            if now - campaign.scheduled_at <= grace:
                result["deferred"] += 1
                continue
            fail_campaign(campaign, f"{exc} Jadwal dibatalkan setelah menunggu 2 jam.")
            result["failed"] += 1
        except CampaignError as exc:
            fail_campaign(campaign, str(exc))
            result["failed"] += 1
        else:
            result["started"] += 1
    return result


@transaction.atomic
def cancel_campaign(campaign: Campaign, *, by=None) -> Campaign:
    if campaign.is_finished:
        return campaign
    campaign.recipients.filter(status=Recipient.Status.PENDING).update(
        status=Recipient.Status.SKIPPED, error="Kampanye dihentikan"
    )
    campaign.status = Campaign.Status.CANCELLED
    campaign.finished_at = timezone.now()
    campaign.cancelled_by = by
    campaign.save(update_fields=["status", "finished_at", "cancelled_by"])
    return campaign


def delete_campaign(campaign: Campaign, *, by=None) -> Campaign:
    """Hentikan bila masih berjalan, lalu sembunyikan dari member.

    Baris penerima tetap disimpan agar pesan yang sudah terkirim tetap dihitung kuota.
    """
    cancel_campaign(campaign, by=by)
    campaign.deleted_at = timezone.now()
    campaign.save(update_fields=["deleted_at"])
    return campaign


# --- Callback dari n8n -------------------------------------------------------------


@transaction.atomic
def record_result(payload: dict) -> dict:
    """Simpan hasil satu penerima. Balasan `continue` memberi tahu n8n apakah lanjut."""
    campaign = Campaign.objects.select_for_update().filter(pk=payload.get("campaign_id")).first()
    if campaign is None:
        raise CampaignError("Kampanye tidak ditemukan.")
    if campaign.status in {Campaign.Status.CANCELLED, Campaign.Status.FAILED}:
        return {"continue": False}

    recipient = campaign.recipients.filter(pk=payload.get("recipient_id")).first()
    if recipient is None:
        raise CampaignError("Penerima tidak ditemukan di kampanye ini.")

    if recipient.status == Recipient.Status.PENDING:
        status = payload.get("status")
        if status == "sent":
            recipient.status = Recipient.Status.SENT
            recipient.sent_at = timezone.now()
            recipient.wa_message_id = str(payload.get("message_id") or "")[:120]
        elif status == "failed":
            recipient.status = Recipient.Status.FAILED
            recipient.error = str(payload.get("error") or "Gagal terkirim")[:300]
        else:
            raise CampaignError("Status penerima tidak dikenal.")
        recipient.save(update_fields=["status", "sent_at", "wa_message_id", "error"])

    if campaign.status == Campaign.Status.QUEUED:
        campaign.status = Campaign.Status.RUNNING
    if not campaign.recipients.filter(status=Recipient.Status.PENDING).exists():
        campaign.status = Campaign.Status.COMPLETED
        campaign.finished_at = timezone.now()
    campaign.save(update_fields=["status", "finished_at"])

    over_quota = used_today(campaign.owner) > campaign.owner.daily_message_quota
    return {"continue": campaign.status == Campaign.Status.RUNNING and not over_quota}


def progress(campaign: Campaign) -> dict:
    counts = {status: 0 for status in Recipient.Status.values}
    for row in campaign.recipients.values("status").order_by().annotate(n=Count("pk")):
        counts[row["status"]] = row["n"]
    total = sum(counts.values())
    done = total - counts[Recipient.Status.PENDING]
    return {
        "status": campaign.status,
        "status_label": campaign.get_status_display(),
        "total": total,
        "done": done,
        "percent": round(done * 100 / total) if total else 0,
        **counts,
    }
