"""Klien HTTP minimal untuk WAHA (WhatsApp HTTP API).

Hanya dipanggil dari server. API key tidak pernah dikirim ke browser.
Dokumentasi: https://waha.devlike.pro/docs/
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

TIMEOUT_SECONDS = 15


class WahaError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class WahaNotConfigured(WahaError):
    pass


def is_configured() -> bool:
    return bool(settings.WAHA_BASE_URL and settings.WAHA_API_KEY)


def _request(method, path, payload=None, accept="application/json"):
    if not is_configured():
        raise WahaNotConfigured("WAHA belum dikonfigurasi (WAHA_BASE_URL / WAHA_API_KEY).")
    url = settings.WAHA_BASE_URL.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 (URL dari .env)
    request.add_header("X-Api-Key", settings.WAHA_API_KEY)
    request.add_header("Accept", accept)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()[:300].decode(errors="replace")
        raise WahaError(f"WAHA {exc.code}: {body}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise WahaError(f"WAHA tidak bisa dihubungi: {exc}") from exc


def _json(method, path, payload=None):
    _, _, body = _request(method, path, payload)
    return json.loads(body) if body else None


def _session_path(name: str) -> str:
    return urllib.parse.quote(name, safe="")


# --- Sesi ---------------------------------------------------------------------


def get_session(name: str) -> dict | None:
    try:
        return _json("GET", f"/api/sessions/{_session_path(name)}")
    except WahaError as exc:
        if exc.status == 404:
            return None
        raise


def create_session(name: str, webhook_url: str, webhook_token: str) -> dict:
    config = {
        "webhooks": [
            {
                "url": webhook_url,
                "events": ["message", "session.status"],
                "customHeaders": [{"name": "X-SC-Token", "value": webhook_token}],
            }
        ]
    }
    return _json("POST", "/api/sessions", {"name": name, "start": True, "config": config})


def start_session(name: str) -> dict:
    return _json("POST", f"/api/sessions/{_session_path(name)}/start")


def restart_session(name: str) -> dict:
    return _json("POST", f"/api/sessions/{_session_path(name)}/restart")


def stop_session(name: str) -> dict:
    return _json("POST", f"/api/sessions/{_session_path(name)}/stop")


def logout_session(name: str) -> dict:
    return _json("POST", f"/api/sessions/{_session_path(name)}/logout")


def get_qr_png(name: str) -> bytes:
    _, content_type, body = _request(
        "GET", f"/api/{_session_path(name)}/auth/qr?format=image", accept="image/png"
    )
    if "image" not in content_type:
        raise WahaError("QR belum tersedia.")
    return body


# --- Grup & pesan --------------------------------------------------------------


def list_groups(name: str) -> list[dict]:
    """Daftar grup sebagai [{"id": "...@g.us", "name": "..."}] (format WAHA berbeda per engine)."""
    data = _json("GET", f"/api/{_session_path(name)}/groups") or []
    if isinstance(data, dict):
        data = list(data.values())
    groups = []
    for item in data:
        raw_id = item.get("id") or item.get("JID") or ""
        if isinstance(raw_id, dict):
            raw_id = raw_id.get("_serialized", "")
        title = item.get("name") or item.get("subject") or item.get("Name") or ""
        if isinstance(raw_id, str) and raw_id.endswith("@g.us"):
            groups.append({"id": raw_id, "name": title or raw_id})
    return sorted(groups, key=lambda g: g["name"].lower())


def send_text(name: str, chat_id: str, text: str) -> dict:
    return _json("POST", "/api/sendText", {"session": name, "chatId": chat_id, "text": text})
