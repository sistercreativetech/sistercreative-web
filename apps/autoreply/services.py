"""Balas otomatis: cocokkan pesan masuk dengan aturan member lalu teruskan ke n8n.

Jeda "membaca" dan "mengetik" dijalankan di n8n agar webhook Django tetap cepat.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.contacts.messages import render_message
from apps.contacts.models import Contact
from apps.core import n8n

from .matching import find_rule
from .models import AutoReplyLog, AutoReplyRule

logger = logging.getLogger(__name__)

REPLYABLE_SUFFIXES = ("@c.us", "@lid")


def typing_seconds(text: str) -> int:
    """Lama indikator "mengetik": ±2–8 detik tergantung panjang balasan (n8n menambah acak)."""
    return max(2, min(8, 2 + len(text) // 30))


def hourly_count(owner) -> int:
    since = timezone.now() - timedelta(hours=1)
    return AutoReplyLog.objects.filter(
        owner=owner, created_at__gte=since, status=AutoReplyLog.Status.QUEUED
    ).count()


def in_cooldown(rule: AutoReplyRule, chat_id: str) -> bool:
    if not rule.cooldown_minutes:
        return False
    since = timezone.now() - timedelta(minutes=rule.cooldown_minutes)
    return AutoReplyLog.objects.filter(
        rule=rule, chat_id=chat_id, created_at__gte=since, status=AutoReplyLog.Status.QUEUED
    ).exists()


def preview(owner, text: str, *, name: str = ""):
    """Untuk halaman "Coba pesan": aturan yang cocok dan balasannya (tanpa mengirim)."""
    rule = find_rule(AutoReplyRule.objects.filter(owner=owner), text, timezone.localtime().time())
    if rule is None:
        return None, ""
    return rule, render_message(rule.reply, name=name)


def handle_incoming(session, payload: dict) -> str:
    """Proses satu pesan masuk ke sesi member. Kembalikan ringkasan untuk log/test."""
    owner = session.owner
    chat_id = payload.get("from") or ""
    text = (payload.get("body") or "").strip()
    message_id = str(payload.get("id") or "")[:160]

    if payload.get("fromMe") or not chat_id.endswith(REPLYABLE_SUFFIXES):
        return "ignored"
    if not text or not message_id:
        return "ignored"
    if AutoReplyLog.objects.filter(message_id=message_id).exists():
        return "duplicate"

    contact = None
    if chat_id.endswith("@c.us"):
        contact = Contact.objects.filter(owner=owner, phone=chat_id.split("@")[0]).first()
        if contact and contact.is_opted_out:
            return "opted-out-contact"

    rules = AutoReplyRule.objects.filter(owner=owner, is_active=True)
    rule = find_rule(rules, text, timezone.localtime().time())
    if rule is None:
        return "no-rule"
    if in_cooldown(rule, chat_id):
        return "cooldown"
    if hourly_count(owner) >= settings.AUTO_REPLY_MAX_PER_HOUR:
        return "hourly-limit"

    reply = render_message(
        rule.reply,
        name=contact.name if contact else "",
        phone=contact.phone if contact else "",
    )
    try:
        log = AutoReplyLog.objects.create(
            owner=owner,
            rule=rule,
            chat_id=chat_id,
            message_id=message_id,
            incoming_text=text[:500],
            reply_text=reply,
        )
    except IntegrityError:
        return "duplicate"

    try:
        n8n.post_job(
            settings.N8N_AUTOREPLY_WEBHOOK_URL,
            {
                "session": session.name,
                "chat_id": chat_id,
                "message_id": message_id,
                "reply": reply,
                "typing_seconds": typing_seconds(reply),
            },
        )
    except n8n.N8nError as exc:
        logger.warning("Balas otomatis gagal diteruskan (%s): %s", session.name, exc)
        log.status = AutoReplyLog.Status.FAILED
        log.save(update_fields=["status"])
        return "dispatch-failed"
    return "queued"
