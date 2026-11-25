"""Pengaturan untuk pengembangan lokal (SQLite)."""

import warnings

from .base import *  # noqa: F403

DEBUG = True

# Di lokal STATIC_ROOT belum dibuat (tanpa collectstatic); WhiteNoise memakai finders.
warnings.filterwarnings("ignore", message="No directory at", category=UserWarning)

# Di lokal tidak perlu manifest supaya tidak wajib collectstatic.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
