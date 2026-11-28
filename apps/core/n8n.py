"""Kirim pekerjaan ke webhook n8n (blast, balas otomatis) dengan token header."""

import hmac
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20


class N8nError(Exception):
    pass


class N8nNotConfigured(N8nError):
    pass


def post_job(url: str, payload: dict) -> None:
    """POST JSON ke webhook n8n. Header X-SC-Token = N8N_BLAST_TOKEN."""
    if not url or not settings.N8N_BLAST_TOKEN:
        raise N8nNotConfigured("Webhook n8n belum dikonfigurasi.")
    request = urllib.request.Request(  # noqa: S310 (URL dari .env)
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-SC-Token": settings.N8N_BLAST_TOKEN},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            if response.status >= 300:
                raise N8nError(f"n8n membalas status {response.status}")
    except urllib.error.HTTPError as exc:
        raise N8nError(f"n8n membalas status {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("n8n tidak bisa dihubungi: %s", exc)
        raise N8nError("n8n tidak bisa dihubungi") from exc


def valid_callback_token(request) -> bool:
    """Panggilan dari n8n ke Django membawa header X-SC-Token = N8N_CALLBACK_TOKEN."""
    expected = settings.N8N_CALLBACK_TOKEN
    received = request.headers.get("X-SC-Token", "")
    return bool(expected) and hmac.compare_digest(received, expected)
