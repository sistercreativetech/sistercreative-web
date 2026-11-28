"""Follow-up otomatis: daftarkan chat ke urutan, jadwalkan langkah, kirim lewat n8n.

Pengiriman memakai workflow n8n "Blast WA Member" yang sama dengan kampanye
(callback_url & image_url dikirim per pekerjaan), sehingga jeda acak dan
indikator mengetik ikut berlaku.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.autoreply.matching import keyword_matches, within_hours
from apps.contacts.messages import render_message
from apps.contacts.models import Contact
from apps.core import n8n
from apps.whatsapp.models import WhatsAppSession

from .models import FollowUpEnrollment, FollowUpMessage, FollowUpSequence, FollowUpStep

logger = logging.getLogger(__name__)

Enrollment = FollowUpEnrollment
Message = FollowUpMessage

PERSONAL_SUFFIXES = ("@c.us", "@lid")
# Jarak minimal antar dua follow-up ke chat yang sama.
MIN_GAP = timedelta(hours=1)


class FollowUpError(Exception):
    """Kesalahan yang aman ditampilkan ke member / n8n."""


# --- Jadwal ----------------------------------------------------------------------


def next_step_for(enrollment: Enrollment) -> tuple[FollowUpStep | None, object]:
    """Langkah berikutnya dan waktu jatuh temponya (dihitung dari waktu chat masuk)."""
    step = (
        enrollment.sequence.steps.filter(delay_minutes__gt=enrollment.progress_minutes)
        .order_by("delay_minutes", "pk")
        .first()
    )
    if step is None:
        return None, None
    due = enrollment.enrolled_at + step.delay
    if enrollment.last_step_at:
        due = max(due, enrollment.last_step_at + MIN_GAP)
    return step, due


def schedule_next(enrollment: Enrollment) -> Enrollment:
    step, due = next_step_for(enrollment)
    enrollment.next_step, enrollment.next_due_at = step, due
    if step is None and enrollment.status == Enrollment.Status.ACTIVE:
        enrollment.status = Enrollment.Status.COMPLETED
    enrollment.save(update_fields=["next_step", "next_due_at", "status", "updated_at"])
    return enrollment


def reschedule_sequence(sequence: FollowUpSequence) -> None:
    """Hitung ulang jadwal peserta aktif setelah langkah ditambah/diubah/dihapus."""
    for enrollment in sequence.enrollments.filter(status=Enrollment.Status.ACTIVE):
        schedule_next(enrollment)


# --- Daftar / hentikan --------------------------------------------------------------


def enroll(
    sequence: FollowUpSequence, *, chat_id: str, contact=None, display_name: str = ""
) -> Enrollment | None:
    """Daftarkan satu chat. None bila urutan belum punya langkah atau chat sudah pernah ikut."""
    if not sequence.steps.exists():
        return None
    try:
        with transaction.atomic():
            enrollment, created = Enrollment.objects.get_or_create(
                sequence=sequence,
                chat_id=chat_id,
                defaults={"contact": contact, "display_name": display_name[:120]},
            )
    except IntegrityError:
        return None
    if not created:
        return None
    return schedule_next(enrollment)


def enroll_contacts(sequence: FollowUpSequence, contacts) -> tuple[int, int]:
    """Daftarkan kontak secara manual. Kembalikan (terdaftar, dilewati)."""
    if not sequence.steps.exists():
        raise FollowUpError("Tambahkan minimal satu langkah sebelum mendaftarkan kontak.")
    added = skipped = 0
    for contact in contacts:
        if contact.owner_id != sequence.owner_id or contact.is_opted_out:
            skipped += 1
            continue
        chat_id = f"{contact.phone}@c.us"
        if enroll(sequence, chat_id=chat_id, contact=contact, display_name=contact.name):
            added += 1
        else:
            skipped += 1
    return added, skipped


def stop_enrollment(enrollment: Enrollment, reason: str) -> Enrollment:
    if enrollment.status != Enrollment.Status.ACTIVE:
        return enrollment
    enrollment.status = Enrollment.Status.STOPPED
    enrollment.stop_reason = reason
    enrollment.next_due_at = None
    enrollment.save(update_fields=["status", "stop_reason", "next_due_at", "updated_at"])
    return enrollment


def restart_enrollment(enrollment: Enrollment) -> Enrollment:
    """Mulai ulang dari langkah pertama, dihitung dari sekarang."""
    if enrollment.status == Enrollment.Status.ACTIVE:
        raise FollowUpError("Follow-up ini masih berjalan.")
    if enrollment.contact and enrollment.contact.is_opted_out:
        raise FollowUpError("Kontak ini sudah berhenti berlangganan (STOP).")
    if not enrollment.sequence.steps.exists():
        raise FollowUpError("Urutan ini belum punya langkah.")
    enrollment.status = Enrollment.Status.ACTIVE
    enrollment.stop_reason = ""
    enrollment.enrolled_at = timezone.now()
    enrollment.progress_minutes = 0
    enrollment.last_step_at = None
    enrollment.save()
    return schedule_next(enrollment)


def stop_for_chat(owner, chat_id: str, reason: str) -> int:
    return Enrollment.objects.filter(
        sequence__owner=owner, chat_id=chat_id, status=Enrollment.Status.ACTIVE
    ).update(
        status=Enrollment.Status.STOPPED,
        stop_reason=reason,
        next_due_at=None,
        updated_at=timezone.now(),
    )


# --- Pesan masuk (dari webhook WAHA) ----------------------------------------------------


def _sender_name(payload: dict) -> str:
    """Nama profil WhatsApp pengirim (dipakai untuk {nama} bila belum ada di kontak)."""
    data = payload.get("_data")
    if not isinstance(data, dict):
        return ""
    name = data.get("pushName") or data.get("notifyName") or ""
    return " ".join(str(name).split())[:120]


def handle_incoming(session, payload: dict) -> str:
    """Hentikan follow-up yang dibalas customer, lalu daftarkan chat ke urutan yang cocok."""
    owner = session.owner
    chat_id = payload.get("from") or ""
    if payload.get("fromMe") or not chat_id.endswith(PERSONAL_SUFFIXES):
        return "ignored"
    text = (payload.get("body") or "").strip()

    # Hanya dihitung "membalas" bila follow-up sudah pernah terkirim ke chat ini,
    # sehingga beberapa pesan beruntun di awal percakapan tidak langsung menghentikannya.
    stopped = Enrollment.objects.filter(
        sequence__owner=owner,
        sequence__stop_on_reply=True,
        chat_id=chat_id,
        status=Enrollment.Status.ACTIVE,
        last_step_at__isnull=False,
    ).update(
        status=Enrollment.Status.STOPPED,
        stop_reason=Enrollment.StopReason.REPLIED,
        next_due_at=None,
        updated_at=timezone.now(),
    )

    contact = None
    if chat_id.endswith("@c.us"):
        contact = Contact.objects.filter(owner=owner, phone=chat_id.split("@")[0]).first()
        if contact and contact.is_opted_out:
            return f"enrolled:0 stopped:{stopped}"
    name = contact.name if contact and contact.name else _sender_name(payload)

    enrolled = 0
    sequences = FollowUpSequence.objects.filter(
        owner=owner,
        is_active=True,
        trigger__in=[FollowUpSequence.Trigger.ANY_CHAT, FollowUpSequence.Trigger.KEYWORD],
    )
    for sequence in sequences:
        if sequence.trigger == FollowUpSequence.Trigger.KEYWORD and not any(
            keyword_matches(text, word, "contains") for word in sequence.keyword_list
        ):
            continue
        if enroll(sequence, chat_id=chat_id, contact=contact, display_name=name):
            enrolled += 1
    return f"enrolled:{enrolled} stopped:{stopped}"


# --- Kirim yang jatuh tempo (dipanggil n8n berkala) ----------------------------------------


def _post_job(payload: dict) -> None:
    n8n.post_job(settings.N8N_BLAST_WEBHOOK_URL, payload)


def _absolute(path: str) -> str:
    return settings.SITE_URL.rstrip("/") + path


def _opted_out_phones(owner, enrollments) -> set[str]:
    phones = [e.chat_id.split("@")[0] for e in enrollments if e.chat_id.endswith("@c.us")]
    return set(
        Contact.objects.filter(owner=owner, phone__in=phones, is_opted_out=True).values_list(
            "phone", flat=True
        )
    )


def _blocked_reason(owner) -> str:
    """Alasan follow-up member ini ditunda pada putaran ini ("" bila boleh kirim)."""
    # Impor lokal: campaigns.services juga mengimpor selector follow-up untuk kuota.
    from apps.campaigns import services as campaign_services
    from apps.campaigns.models import Campaign

    if owner.status != User.Status.ACTIVE:
        return "member-inactive"
    session = WhatsAppSession.objects.filter(owner=owner).first()
    if session is None or not session.is_connected:
        return "not-connected"
    if Campaign.objects.filter(owner=owner, status__in=Campaign.ACTIVE_STATUSES).exists():
        return "campaign-running"
    if campaign_services.remaining_quota(owner) <= 0:
        return "quota"
    return ""


def _dispatch_owner(owner, now) -> dict:
    from apps.campaigns import services as campaign_services

    result = {"queued": 0, "stopped": 0, "deferred": 0}
    reason = _blocked_reason(owner)
    if reason:
        result["deferred"] = 1
        return result
    limit = min(settings.FOLLOWUP_BATCH_SIZE, campaign_services.remaining_quota(owner))
    session = WhatsAppSession.objects.get(owner=owner)
    local_time = timezone.localtime(now).time()

    with transaction.atomic():
        due = list(
            Enrollment.objects.select_for_update(of=("self",))
            .filter(
                sequence__owner=owner,
                sequence__is_active=True,
                status=Enrollment.Status.ACTIVE,
                next_due_at__lte=now,
            )
            .select_related("sequence", "next_step", "contact")
            .order_by("next_due_at", "pk")[: settings.FOLLOWUP_BATCH_SIZE * 3]
        )
        opted_out = _opted_out_phones(owner, due)
        batch, image = [], None
        for enrollment in due:
            if (enrollment.contact and enrollment.contact.is_opted_out) or (
                enrollment.chat_id.split("@")[0] in opted_out
            ):
                stop_enrollment(enrollment, Enrollment.StopReason.OPTED_OUT)
                result["stopped"] += 1
                continue
            sequence = enrollment.sequence
            if not within_hours(local_time, sequence.send_from, sequence.send_until):
                continue
            if enrollment.next_step is None:
                schedule_next(enrollment)
                continue
            # Satu pekerjaan n8n hanya membawa satu gambar: kelompokkan per gambar.
            step_image = enrollment.next_step.image.name or ""
            if image is None:
                image = step_image
            if step_image != image or len(batch) >= limit:
                continue
            batch.append(enrollment)

        if not batch:
            return result

        first_step = batch[0].next_step
        image_url = _absolute(first_step.image.url) if first_step.image else ""
        messages = []
        for enrollment in batch:
            step = enrollment.next_step
            name = enrollment.contact.name if enrollment.contact else enrollment.display_name
            phone = enrollment.chat_id.split("@")[0] if enrollment.chat_id.endswith("@c.us") else ""
            text = render_message(step.body, name=name, phone=phone) + settings.OPT_OUT_FOOTER
            messages.append(
                Message.objects.create(
                    owner=owner,
                    enrollment=enrollment,
                    step=step,
                    chat_id=enrollment.chat_id,
                    text=text,
                )
            )
            enrollment.progress_minutes = step.delay_minutes
            enrollment.last_step_at = now
            enrollment.save(update_fields=["progress_minutes", "last_step_at", "updated_at"])
            schedule_next(enrollment)

        payload = {
            "kind": "followup",
            "campaign_id": 0,
            "session": session.name,
            "delay_seconds": {"min": settings.BLAST_DELAY_MIN, "max": settings.BLAST_DELAY_MAX},
            "callback_url": _absolute(reverse("followup_callback")),
            "image_url": image_url,
            "recipients": [
                {"recipient_id": m.pk, "chat_id": m.chat_id, "text": m.text} for m in messages
            ],
        }
        try:
            _post_job(payload)
        except n8n.N8nError as exc:
            # Batalkan semua perubahan putaran ini; dicoba lagi pada panggilan berikutnya.
            logger.warning("Follow-up member %s gagal diteruskan: %s", owner.pk, exc)
            transaction.set_rollback(True)
            result["deferred"] = 1
            result["stopped"] = 0
            return result
    result["queued"] = len(messages)
    return result


def dispatch_due(now=None) -> dict:
    """Kirim follow-up yang jatuh tempo, satu pekerjaan n8n per member per putaran."""
    now = now or timezone.now()
    totals = {"queued": 0, "stopped": 0, "deferred": 0}
    owner_ids = (
        Enrollment.objects.filter(
            status=Enrollment.Status.ACTIVE, next_due_at__lte=now, sequence__is_active=True
        )
        .values_list("sequence__owner_id", flat=True)
        .distinct()
    )
    for owner in User.objects.filter(pk__in=list(owner_ids)).order_by("pk"):
        for key, value in _dispatch_owner(owner, now).items():
            totals[key] += value
    return totals


# --- Callback dari n8n -----------------------------------------------------------------


@transaction.atomic
def record_result(payload: dict) -> dict:
    """Simpan hasil satu pesan follow-up. `continue` = n8n boleh lanjut ke pesan berikutnya."""
    from apps.campaigns import services as campaign_services

    message = (
        Message.objects.select_for_update()
        .select_related("owner")
        .filter(pk=payload.get("recipient_id"))
        .first()
    )
    if message is None:
        raise FollowUpError("Pesan follow-up tidak ditemukan.")
    if message.status == Message.Status.PENDING:
        status = payload.get("status")
        if status == "sent":
            message.status = Message.Status.SENT
            message.sent_at = timezone.now()
            message.wa_message_id = str(payload.get("message_id") or "")[:120]
        elif status == "failed":
            message.status = Message.Status.FAILED
            message.error = str(payload.get("error") or "Gagal terkirim")[:300]
        else:
            raise FollowUpError("Status pesan tidak dikenal.")
        message.save(update_fields=["status", "sent_at", "wa_message_id", "error"])
    owner = message.owner
    return {"continue": campaign_services.used_today(owner) <= owner.daily_message_quota}
