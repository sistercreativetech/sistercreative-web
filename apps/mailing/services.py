"""Blast email (khusus admin): penerima, pengiriman bertahap lewat n8n, impor CSV."""

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from apps.contacts.services import NAME_HEADERS, ImportFileError, _decode, _delimiter
from apps.core import n8n

from . import selectors
from .models import EmailCampaign, EmailRecipient, MailingList, Subscriber
from .rendering import absolute, render_email

logger = logging.getLogger(__name__)

Recipient = EmailRecipient
EMAIL_HEADERS = {"email", "e-mail", "alamat email", "surel", "email address", "gmail"}
EMAILED_HEADERS = {"updated", "terakhir dikirim", "last_emailed", "dikirim", "sent"}
MAX_REPORTED_ERRORS = 20


class MailingError(Exception):
    """Kesalahan yang aman ditampilkan ke admin."""


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


# --- Batas harian -------------------------------------------------------------------


def start_of_today():
    return timezone.make_aware(datetime.combine(timezone.localdate(), time.min))


def remaining_today() -> int:
    used = selectors.emails_used_since(start_of_today())
    return max(settings.EMAIL_BLAST_DAILY_LIMIT - used, 0)


# --- Kampanye -----------------------------------------------------------------------


@transaction.atomic
def start_campaign(campaign: EmailCampaign) -> int:
    """Tetapkan penerima lalu tandai kampanye 'sedang mengirim'. Kembalikan jumlah penerima."""
    campaign = EmailCampaign.objects.select_for_update().get(pk=campaign.pk)
    if not campaign.is_draft:
        raise MailingError("Kampanye ini sudah pernah dimulai.")
    if not settings.N8N_EMAIL_WEBHOOK_URL or not settings.N8N_BLAST_TOKEN:
        raise MailingError("Webhook n8n untuk email belum diatur (N8N_EMAIL_WEBHOOK_URL).")
    subscribers = list(selectors.target_subscribers(campaign))
    if not subscribers:
        raise MailingError("Tidak ada pelanggan aktif yang dituju kampanye ini.")
    Recipient.objects.bulk_create(
        [
            Recipient(campaign=campaign, subscriber=s, email=s.email, name=s.name)
            for s in subscribers
        ]
    )
    campaign.status = EmailCampaign.Status.SENDING
    campaign.started_at = timezone.now()
    campaign.save(update_fields=["status", "started_at"])
    return len(subscribers)


@transaction.atomic
def cancel_campaign(campaign: EmailCampaign) -> None:
    campaign = EmailCampaign.objects.select_for_update().get(pk=campaign.pk)
    if not campaign.is_sending:
        raise MailingError("Hanya kampanye yang sedang mengirim yang bisa dihentikan.")
    campaign.recipients.filter(status=Recipient.Status.PENDING).update(
        status=Recipient.Status.SKIPPED, error="Kampanye dihentikan"
    )
    campaign.status = EmailCampaign.Status.CANCELLED
    campaign.finished_at = timezone.now()
    campaign.save(update_fields=["status", "finished_at"])


def delete_campaign(campaign: EmailCampaign) -> None:
    if campaign.is_sending:
        raise MailingError("Hentikan kampanye dulu sebelum menghapusnya.")
    campaign.delete()


def status_counts(campaign: EmailCampaign) -> dict:
    counts = {status: 0 for status in Recipient.Status.values}
    rows = campaign.recipients.values("status").order_by().annotate(n=Count("pk"))
    for row in rows:
        counts[row["status"]] = row["n"]
    counts["total"] = sum(counts[s] for s in Recipient.Status.values)
    open_count = counts[Recipient.Status.PENDING] + counts[Recipient.Status.QUEUED]
    counts["done"] = counts["total"] - open_count
    counts["percent"] = round(counts["done"] * 100 / counts["total"]) if counts["total"] else 0
    return counts


# --- Kirim ke n8n -------------------------------------------------------------------


def _job(campaign_id: int, items: list[dict]) -> dict:
    return {
        "kind": "email",
        "campaign_id": campaign_id,
        "callback_url": absolute(reverse("mailing_callback")),
        "from": settings.EMAIL_BLAST_FROM,
        "reply_to": settings.EMAIL_BLAST_REPLY_TO,
        "delay_seconds": {
            "min": settings.EMAIL_BLAST_DELAY_MIN,
            "max": settings.EMAIL_BLAST_DELAY_MAX,
        },
        "recipients": items,
    }


def _item(recipient_id: int, to: str, rendered) -> dict:
    return {
        "recipient_id": recipient_id,
        "to": to,
        "subject": rendered.subject,
        "html": rendered.html,
        "text": rendered.text,
    }


def send_test(campaign: EmailCampaign, *, to: str, name: str = "") -> None:
    """Kirim satu email uji (recipient_id 0, tidak dicatat sebagai penerima)."""
    rendered = render_email(campaign, name=name, unsubscribe_url=absolute("/"))
    rendered.subject = f"[UJI] {rendered.subject}"
    try:
        n8n.post_job(settings.N8N_EMAIL_WEBHOOK_URL, _job(campaign.pk, [_item(0, to, rendered)]))
    except n8n.N8nError as exc:
        raise MailingError(f"Email uji gagal dikirim ke n8n: {exc}") from exc


def _expire_stale(now) -> int:
    """Penerima yang terlalu lama 'dikirim ke n8n' tanpa laporan dianggap gagal."""
    limit = now - timedelta(minutes=settings.EMAIL_BLAST_QUEUE_TIMEOUT_MINUTES)
    return Recipient.objects.filter(status=Recipient.Status.QUEUED, queued_at__lt=limit).update(
        status=Recipient.Status.FAILED, error="Tidak ada laporan dari n8n"
    )


def _finish_if_done(campaign: EmailCampaign, now) -> bool:
    open_statuses = (Recipient.Status.PENDING, Recipient.Status.QUEUED)
    if campaign.recipients.filter(status__in=open_statuses).exists():
        return False
    campaign.status = EmailCampaign.Status.COMPLETED
    campaign.finished_at = now
    campaign.save(update_fields=["status", "finished_at"])
    return True


@transaction.atomic
def dispatch_due(now=None) -> dict:
    """Dipanggil n8n berkala: kirim satu batch berikutnya bila batch sebelumnya sudah selesai."""
    now = now or timezone.now()
    result = {"queued": 0, "expired": _expire_stale(now), "completed": 0, "skipped": 0}

    sending = EmailCampaign.objects.select_for_update().filter(status=EmailCampaign.Status.SENDING)
    campaigns = list(sending.order_by("started_at", "pk"))
    for campaign in campaigns:
        if _finish_if_done(campaign, now):
            result["completed"] += 1
    if Recipient.objects.filter(status=Recipient.Status.QUEUED).exists():
        result["busy"] = True
        return result

    budget = min(remaining_today(), settings.EMAIL_BLAST_BATCH_SIZE)
    campaign = next((c for c in campaigns if c.status == EmailCampaign.Status.SENDING), None)
    if campaign is None or budget <= 0:
        return result

    batch = []
    pending = (
        campaign.recipients.filter(status=Recipient.Status.PENDING)
        .select_related("subscriber")
        .order_by("pk")
    )
    for recipient in pending.iterator():
        subscriber = recipient.subscriber
        if subscriber is None or not subscriber.is_subscribed:
            recipient.status = Recipient.Status.SKIPPED
            recipient.error = "Sudah berhenti berlangganan"
            recipient.save(update_fields=["status", "error"])
            result["skipped"] += 1
            continue
        batch.append(recipient)
        if len(batch) >= budget:
            break

    if not batch:
        result["completed"] += int(_finish_if_done(campaign, now))
        return result

    items = []
    for recipient in batch:
        rendered = render_email(
            campaign,
            name=recipient.name,
            unsubscribe_url=absolute(recipient.subscriber.get_unsubscribe_url()),
        )
        items.append(_item(recipient.pk, recipient.email, rendered))
    Recipient.objects.filter(pk__in=[r.pk for r in batch]).update(
        status=Recipient.Status.QUEUED, queued_at=now
    )
    try:
        n8n.post_job(settings.N8N_EMAIL_WEBHOOK_URL, _job(campaign.pk, items))
    except n8n.N8nError as exc:
        logger.warning("Batch email kampanye %s gagal dikirim ke n8n: %s", campaign.pk, exc)
        transaction.set_rollback(True)
        return {**result, "queued": 0, "error": str(exc)}
    result["queued"] = len(batch)
    return result


# --- Callback dari n8n --------------------------------------------------------------


@transaction.atomic
def record_result(payload: dict) -> dict:
    """Simpan hasil satu email. `continue` memberi tahu n8n apakah lanjut ke email berikutnya."""
    try:
        recipient_id = int(payload.get("recipient_id") or 0)
    except (TypeError, ValueError):
        raise MailingError("recipient_id tidak valid.") from None
    if recipient_id == 0:
        return {"continue": False}  # email uji

    recipient = (
        Recipient.objects.select_for_update()
        .select_related("campaign", "subscriber")
        .filter(pk=recipient_id, campaign_id=payload.get("campaign_id"))
        .first()
    )
    if recipient is None:
        raise MailingError("Penerima tidak ditemukan.")

    now = timezone.now()
    if recipient.status in (Recipient.Status.QUEUED, Recipient.Status.PENDING):
        status = payload.get("status")
        if status == "sent":
            recipient.status = Recipient.Status.SENT
            recipient.sent_at = now
            recipient.error = ""
            if recipient.subscriber_id:
                Subscriber.objects.filter(pk=recipient.subscriber_id).update(last_emailed_at=now)
        elif status == "failed":
            recipient.status = Recipient.Status.FAILED
            recipient.error = str(payload.get("error") or "Gagal terkirim")[:300]
        else:
            raise MailingError("Status tidak dikenal.")
        recipient.save(update_fields=["status", "sent_at", "error"])

    campaign = recipient.campaign
    if campaign.is_sending:
        _finish_if_done(campaign, now)
    return {"continue": campaign.status == EmailCampaign.Status.SENDING}


# --- Berhenti berlangganan ----------------------------------------------------------


def unsubscribe(subscriber: Subscriber) -> None:
    if subscriber.is_subscribed:
        subscriber.status = Subscriber.Status.UNSUBSCRIBED
        subscriber.unsubscribed_at = timezone.now()
        subscriber.save(update_fields=["status", "unsubscribed_at"])


# --- Impor CSV ----------------------------------------------------------------------


@dataclass
class ImportResult:
    created: int = 0
    existing: int = 0
    duplicates_in_file: int = 0
    invalid_count: int = 0
    invalid_rows: list[tuple[int, str]] = field(default_factory=list)
    mailing_list: MailingList | None = None


def _find(header: list[str], names: set[str]) -> int | None:
    cleaned = [cell.strip().lower() for cell in header]
    return next((i for i, cell in enumerate(cleaned) if cell in names), None)


def _emailed_at(value: str):
    """Kolom 'updated' dari Sheet lama: ambil tanggalnya; isi lain dianggap 'sudah dikirim'."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        day = date.fromisoformat(value[:10])
    except ValueError:
        return timezone.now()
    return timezone.make_aware(datetime.combine(day, time(12)))


def parse_csv(raw: bytes) -> list[tuple[int, str, str, str]]:
    """Kembalikan [(nomor_baris, email, nama, kolom_terakhir_dikirim)]."""
    text = _decode(raw)
    rows = list(csv.reader(io.StringIO(text), delimiter=_delimiter(text)))
    rows = [(i, row) for i, row in enumerate(rows, start=1) if any(cell.strip() for cell in row)]
    if not rows:
        raise ImportFileError("File CSV kosong.")
    header = rows[0][1]
    email_col = _find(header, EMAIL_HEADERS)
    if email_col is None:
        raise ImportFileError("Kolom email tidak ditemukan. Beri judul kolom “email”.")
    name_col = _find(header, NAME_HEADERS)
    emailed_col = _find(header, EMAILED_HEADERS)
    data_rows = rows[1:]
    if len(data_rows) > settings.EMAIL_IMPORT_MAX_ROWS:
        raise ImportFileError(
            f"Maksimal {settings.EMAIL_IMPORT_MAX_ROWS} baris per impor. Pecah file dulu."
        )

    def cell(row, col):
        return row[col].strip() if col is not None and col < len(row) else ""

    return [
        (
            line_no,
            cell(row, email_col),
            " ".join(cell(row, name_col).split())[:120],
            cell(row, emailed_col),
        )
        for line_no, row in data_rows
    ]


@transaction.atomic
def import_subscribers(
    raw: bytes, *, mailing_list: MailingList | None = None, source: str = "Impor CSV"
) -> ImportResult:
    """Tambah pelanggan baru dan lengkapi yang sudah ada (yang sudah berhenti tetap berhenti)."""
    result = ImportResult(mailing_list=mailing_list)
    seen = set()
    valid = []
    for line_no, raw_email, name, emailed in parse_csv(raw):
        email = normalize_email(raw_email)
        try:
            validate_email(email)
        except ValidationError:
            result.invalid_count += 1
            if len(result.invalid_rows) < MAX_REPORTED_ERRORS:
                result.invalid_rows.append((line_no, raw_email[:120]))
            continue
        if email in seen:
            result.duplicates_in_file += 1
            continue
        seen.add(email)
        valid.append((email, name, _emailed_at(emailed)))

    existing = {s.email: s for s in Subscriber.objects.filter(email__in=seen)}
    to_link = []
    for email, name, emailed_at in valid:
        subscriber = existing.get(email)
        if subscriber is None:
            subscriber = Subscriber.objects.create(
                email=email, name=name, source=source[:60], last_emailed_at=emailed_at
            )
            result.created += 1
        else:
            changed = []
            if name and not subscriber.name:
                subscriber.name = name
                changed.append("name")
            if emailed_at and (
                subscriber.last_emailed_at is None or emailed_at > subscriber.last_emailed_at
            ):
                subscriber.last_emailed_at = emailed_at
                changed.append("last_emailed_at")
            if changed:
                subscriber.save(update_fields=changed)
            result.existing += 1
        to_link.append(subscriber)
    if mailing_list is not None:
        mailing_list.subscribers.add(*to_link)
    return result


def sample_csv() -> str:
    return "nama,email\nRina Wulandari,rina@contoh.id\nDedi Kurniawan,dedi@contoh.id\n"
