"""Pemeriksaan konfigurasi yang sering salah saat deploy."""

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Warning, register

LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", ""}  # noqa: S104


@register(deploy=True)
def site_url_is_public(app_configs, **kwargs):
    """SITE_URL dipakai WAHA & n8n untuk memanggil balik; harus alamat publik HTTPS."""
    parsed = urlparse(settings.SITE_URL)
    if parsed.scheme != "https" or (parsed.hostname or "") in LOCAL_HOSTS:
        return [
            Warning(
                f"SITE_URL={settings.SITE_URL!r} bukan alamat publik HTTPS.",
                hint=(
                    "Isi SITE_URL=https://sistercreative.tech di .env. Tanpa itu webhook WAHA "
                    "(balas otomatis, STOP) dan laporan n8n tidak sampai. Setelah diperbaiki, "
                    "jalankan: python manage.py sync_waha_webhooks"
                ),
                id="sistercreative.W001",
            )
        ]
    return []
