# [Sister Creative] — Website & Landing Page, Portofolio bisa diatur di dashboard admin. Ada menu Login untuk member dan admin. Member dapat memblasting whatsaap (n8n terhubung dengan WAHA) melalui website seperti Aplikasi Web Sebaran.

## Stack
- Django 5, Python 3.12, SQLite (lokal) / PostgreSQL (produksi)
- Tailwind CSS v4 (CLI) — token di assets/css/input.css (@theme)
- Font: Open-sans
- Ikon: Lucide (SVG inline via templates/components/icon.html) mengikuti ikon awal
- Animasi: Motion (vanilla JS, versi di-pin)
- django-allauth, django-filter, Pillow, WhiteNoise, python-dotenv

## Perintah
- python manage.py runserver
- npm run dev        # Tailwind watch
- python manage.py test
- ruff check . && ruff format .
- djlint templates --reformat

## Standar kode
- Class-based views (ListView/DetailView/FormView), view tipis
- Query kompleks di apps/<app>/selectors.py, logika di services.py
- Template: extends base.html, komponen di templates/components/
- Tidak ada inline style, tidak ada <script> di template halaman
- Nama file, class, URL name: konsisten & bahasa Inggris; teks UI: Bahasa Indonesia
- Setiap fitur baru wajib ada test

## Standar desain
- Warna HANYA dari token @theme (primary, accent, ink, surface, dll)
- Skala tipografi & spacing mengikuti docs/DESIGN.md
- Mobile-first, cek di 375px, 768px, 1280px
- Kontras WCAG AA, semua gambar punya alt, fokus keyboard terlihat
- Tidak ada lorem ipsum: konten realistis Bahasa Indonesia

## Keamanan
- Secrets hanya dari .env
- Validasi semua input di server (Django Forms)
- Jangan matikan CSRF, jangan pakai |safe untuk input user
- Semua view dashboard: @staff_member_required / StaffRequiredMixin
- Upload dibatasi ukuran & tipe file

## Cara kerja
- Jelaskan rencana dulu, tunggu persetujuan
- Satu bagian per langkah, lalu jalankan test & lint

## Arsitektur (keputusan 2026-11-25)
- Settings: config/settings/{base,dev,test,prod}.py. `manage.py test` otomatis memakai settings test.
- Aplikasi Django ada di apps/<nama> (label `apps.<nama>`).
- Hosting: VPS Hostinger (sama dengan n8n), Docker + Gunicorn + PostgreSQL, Cloudflare hanya untuk DNS/proxy.
- URL: dashboard admin di /dashboard/, area member di /member/, Django admin bawaan di DJANGO_ADMIN_URL (tersembunyi),
  admin NPL lama di n8n diproksikan lewat /npl-admin/.
- WhatsApp: satu sesi WAHA per member (scan QR). Django → webhook n8n (HMAC) → WAHA, lalu status dikirim balik via callback.
- Member mendaftar sendiri dan baru aktif setelah disetujui admin.
- Situs statis lama + Cloudflare Worker disimpan di legacy/ sebagai referensi konten.
- User kustom `accounts.User`: login memakai email, ada field `full_name`, `whatsapp_number` (format 62...) dan `status`
  (pending/active/rejected/suspended). Status diubah hanya lewat `apps/accounts/services.py`.
- Akses: `StaffRequiredMixin` untuk dashboard, `ApprovedMemberRequiredMixin` untuk area member (apps/accounts/mixins.py).
- Halaman allauth ada di /akun/; tampilannya diatur lewat override di templates/allauth/ (layouts + elements) dan templates/account/.
