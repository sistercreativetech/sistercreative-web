"""Logika sesi WhatsApp member dan event masuk dari WAHA."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.contacts.models import Contact

from . import waha
from .models import WhatsAppSession

logger = logging.getLogger(__name__)

GROUPS_CACHE_SECONDS = 300
STOP_KEYWORDS = {"STOP", "BERHENTI", "UNSUBSCRIBE", "UNREG"}
STOP_CONFIRMATION = (
    "Baik, nomor Anda tidak akan menerima pesan dari pengirim ini lagi. Terima kasih."
)


def get_or_init_session(user) -> WhatsAppSession:
    session, _ = WhatsAppSession.objects.get_or_create(
        owner=user, defaults={"name": WhatsAppSession.name_for(user)}
    )
    return session


def webhook_url() -> str:
    return settings.SITE_URL.rstrip("/") + reverse("waha_webhook")


def _apply_remote(session: WhatsAppSession, data: dict | None) -> WhatsAppSession:
    if data is None:
        session.status = WhatsAppSession.Status.NOT_CREATED
        session.connected_number = ""
        session.connected_name = ""
    else:
        status = data.get("status", "")
        if status in WhatsAppSession.Status.values:
            session.status = status
        me = data.get("me") or {}
        if session.status == WhatsAppSession.Status.WORKING and me:
            session.connected_number = (me.get("id") or "").split("@")[0]
            session.connected_name = (me.get("pushName") or "")[:120]
        elif session.status != WhatsAppSession.Status.WORKING:
            session.connected_number = ""
            session.connected_name = ""
    session.last_checked_at = timezone.now()
    session.save()
    return session


def refresh_status(session: WhatsAppSession) -> WhatsAppSession:
    return _apply_remote(session, waha.get_session(session.name))


def connect(user) -> WhatsAppSession:
    """Buat (atau nyalakan ulang) sesi WAHA milik member agar QR muncul."""
    session = get_or_init_session(user)
    remote = waha.get_session(session.name)
    if remote is None:
        remote = waha.create_session(session.name, webhook_url(), settings.WAHA_WEBHOOK_TOKEN)
    elif remote.get("status") in {"STOPPED", "FAILED"}:
        remote = waha.start_session(session.name)
    cache.delete(groups_cache_key(user))
    return _apply_remote(session, remote)


def disconnect(user) -> WhatsAppSession:
    session = get_or_init_session(user)
    waha.logout_session(session.name)
    cache.delete(groups_cache_key(user))
    return refresh_status(session)


def groups_cache_key(user) -> str:
    return f"wa-groups:{user.pk}"


def whatsapp_groups(user, *, refresh: bool = False) -> list[dict]:
    """Grup WA yang diikuti nomor member. Kosong bila belum terhubung."""
    session = WhatsAppSession.objects.filter(owner=user).first()
    if not session or not session.is_connected:
        return []
    key = groups_cache_key(user)
    groups = None if refresh else cache.get(key)
    if groups is None:
        groups = waha.list_groups(session.name)
        cache.set(key, groups, GROUPS_CACHE_SECONDS)
    return groups


# --- Event masuk dari WAHA -----------------------------------------------------


def handle_event(event: dict) -> str:
    """Proses webhook WAHA. Kembalikan ringkasan untuk log/test."""
    session = WhatsAppSession.objects.filter(name=event.get("session", "")).first()
    if session is None:
        return "unknown-session"
    kind = event.get("event")
    payload = event.get("payload") or {}

    if kind == "session.status":
        _apply_remote(session, {"status": payload.get("status"), "me": event.get("me")})
        return "status-updated"

    if kind == "message":
        if payload.get("fromMe"):
            return "ignored"
        sender = payload.get("from") or ""
        text = (payload.get("body") or "").strip().upper()
        if text not in STOP_KEYWORDS:
            # Bukan STOP: serahkan ke balas otomatis (impor lokal untuk hindari impor melingkar).
            from apps.autoreply.services import handle_incoming

            return handle_incoming(session, payload)
        if not sender.endswith("@c.us"):
            return "ignored"
        phone = sender.split("@")[0]
        updated = Contact.objects.filter(
            owner=session.owner, phone=phone, is_opted_out=False
        ).update(is_opted_out=True, opted_out_at=timezone.now())
        if updated:
            try:
                waha.send_text(session.name, sender, STOP_CONFIRMATION)
            except waha.WahaError:
                logger.warning("Gagal mengirim konfirmasi STOP ke %s", phone)
        return "opted-out" if updated else "already-opted-out"

    return "ignored"
