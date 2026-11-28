"""Pengaturan dasar yang dipakai semua lingkungan."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Variabel lingkungan {name} wajib diisi di .env")
    return value


def env_bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").lower() in {"1", "true", "yes"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
ADMIN_URL = env("DJANGO_ADMIN_URL", "kelola-rahasia/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django_filters",
    "allauth",
    "allauth.account",
    "apps.core",
    "apps.accounts",
    "apps.portfolio",
    "apps.contacts",
    "apps.whatsapp",
    "apps.campaigns",
    "apps.autoreply",
    "apps.followups",
    "apps.members",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Makassar"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Batas ukuran upload (validasi tipe/ukuran per field ada di masing-masing form).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 2 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autentikasi (django-allauth) ------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "members:home"
ACCOUNT_ADAPTER = "apps.accounts.adapter.AccountAdapter"
ACCOUNT_FORMS = {"signup": "apps.accounts.forms.SignupForm"}
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
# Persetujuan admin menjadi gerbang utama; verifikasi email diaktifkan setelah SMTP siap.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", "none")
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_PREVENT_ENUMERATION = True

# Kuota awal pesan WhatsApp per member per hari (bisa diubah admin per member).
DEFAULT_DAILY_MESSAGE_QUOTA = int(env("DEFAULT_DAILY_MESSAGE_QUOTA", "100"))

# Batas kontak per member dan impor CSV.
MAX_CONTACTS_PER_MEMBER = int(env("MAX_CONTACTS_PER_MEMBER", "5000"))
CONTACT_IMPORT_MAX_ROWS = 5000
CONTACT_IMPORT_MAX_BYTES = 1024 * 1024

# --- WhatsApp (WAHA) & pengiriman (n8n) -----------------------------------------
# URL publik situs, dipakai untuk alamat webhook/callback yang dipanggil WAHA & n8n.
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000")
WAHA_BASE_URL = env("WAHA_BASE_URL", "")
WAHA_API_KEY = env("WAHA_API_KEY", "")
WAHA_WEBHOOK_TOKEN = env("WAHA_WEBHOOK_TOKEN", "")
N8N_BASE_URL = env("N8N_BASE_URL", "")
N8N_BLAST_WEBHOOK_URL = env("N8N_BLAST_WEBHOOK_URL", "")
N8N_BLAST_TOKEN = env("N8N_BLAST_TOKEN", "")
N8N_CALLBACK_TOKEN = env("N8N_CALLBACK_TOKEN", "")
N8N_AUTOREPLY_WEBHOOK_URL = env("N8N_AUTOREPLY_WEBHOOK_URL", "")
# Batas balasan otomatis per member per jam (tidak memotong kuota blast).
AUTO_REPLY_MAX_PER_HOUR = int(env("AUTO_REPLY_MAX_PER_HOUR", "30"))
# Jeda acak antar-pesan (detik) untuk mengurangi risiko nomor diblokir.
BLAST_DELAY_MIN = int(env("BLAST_DELAY_MIN", "8"))
BLAST_DELAY_MAX = int(env("BLAST_DELAY_MAX", "20"))
# Ditambahkan di akhir pesan ke kontak pribadi (tidak untuk grup WA).
# Kampanye: gambar & jadwal.
CAMPAIGN_IMAGE_MAX_BYTES = 5 * 1024 * 1024
# Batas keterangan gambar WhatsApp 1024; sisakan ruang untuk nama & catatan STOP.
CAMPAIGN_CAPTION_MAX_CHARS = 900
CAMPAIGN_SCHEDULE_MIN_MINUTES = 5
CAMPAIGN_SCHEDULE_MAX_DAYS = 30
# Bila saat jadwal tiba masih ada kampanye lain berjalan, coba lagi sampai batas ini.
CAMPAIGN_SCHEDULE_GRACE_MINUTES = 120
OPT_OUT_FOOTER = "\n\n_Balas STOP untuk berhenti menerima pesan._"
# Follow-up: maksimal pesan per member dalam satu putaran pemicu n8n.
FOLLOWUP_BATCH_SIZE = int(env("FOLLOWUP_BATCH_SIZE", "20"))
FOLLOWUP_MAX_STEPS = 5

# --- Email ------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Sister Creative <noreply@sistercreative.tech>")

# Info publik situs
SITE_NAME = "Sister Creative"
CONTACT_WHATSAPP = env("CONTACT_WHATSAPP", "6285737086612")
