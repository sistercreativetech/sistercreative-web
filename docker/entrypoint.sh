#!/bin/sh
# Jalankan migrasi sebelum aplikasi dimulai, lalu teruskan ke perintah utama (gunicorn).
set -e

python manage.py migrate --noinput
python manage.py check --deploy --fail-level ERROR

exec "$@"
