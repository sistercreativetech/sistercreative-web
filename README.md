# Website Sister Creative

Website, portofolio, dan aplikasi kirim pesan WhatsApp untuk **sistercreative.tech**.

- **Publik:** landing page, portofolio (`/portofolio/`), konsultasi via WhatsApp.
- **Admin** (`/dashboard/`): menyetujui member, mengatur kuota pesan, mengelola portofolio dan kategori, memantau dan menghentikan kampanye.
- **Member** (`/member/`): menghubungkan WhatsApp (scan QR), mengelola kontak/grup/template, mengirim kampanye ke kontak maupun grup WhatsApp, dan **balas otomatis** berdasarkan kata kunci (tanda dibaca + jeda mengetik).
- **Admin NPL lama** (`/admin`, `/admin/api`): diproksikan ke webhook n8n, dengan path yang sama seperti Cloudflare Worker lama.

Stack: Django 5.2, PostgreSQL, Tailwind CSS v4, django-allauth, WAHA ≥ 2026.6.1 (WhatsApp, multi-sesi sudah termasuk di versi gratis), n8n.
Aturan kode dan desain ada di [CLAUDE.md](CLAUDE.md) dan [docs/DESIGN.md](docs/DESIGN.md).

---

## Pengembangan lokal

Kebutuhan: Python 3.12 dan Node.js 20+.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
npm install
cp .env.example .env              # lalu isi DJANGO_SECRET_KEY
python manage.py migrate
python manage.py createsuperuser
```

Jalankan di dua terminal:

```bash
npm run dev                       # Tailwind watch
python manage.py runserver        # http://127.0.0.1:8000
```

Sebelum commit, jalankan:

```bash
python manage.py test
ruff check . && ruff format .
djlint templates --reformat
```

Perintah lain:
- `python manage.py sync_icons`: salin ikon Lucide yang terdaftar di `apps/core/icons.py`.
- `npm run vendor`: salin bundle Motion (versi terkunci) ke `static/vendor/`.

---

## Variabel lingkungan (`.env`)

Contoh lengkap ada di [.env.example](.env.example). Jangan pernah commit `.env`.

| Variabel | Keterangan |
|---|---|
| `DJANGO_SECRET_KEY` | String acak panjang, beda untuk lokal dan produksi |
| `DJANGO_DEBUG` | `0` di produksi |
| `DJANGO_ALLOWED_HOSTS` | Produksi: `sistercreative.tech,www.sistercreative.tech,localhost,127.0.0.1` (localhost dibutuhkan healthcheck Docker) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://sistercreative.tech,https://www.sistercreative.tech` |
| `DJANGO_ADMIN_URL` | Alamat tersembunyi admin bawaan Django, mis. `kelola-a8f3k/` (**jangan** `admin/`, karena path itu dipakai admin NPL lama) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database produksi |
| `SITE_URL` | **Wajib** `https://sistercreative.tech` di produksi, dipakai WAHA dan n8n untuk memanggil balik. Kalau diubah setelah member menghubungkan WhatsApp, jalankan `python manage.py sync_waha_webhooks` |
| `WAHA_BASE_URL`, `WAHA_API_KEY` | Alamat dan API key server WAHA (versi ≥ 2026.6.1 agar bisa banyak sesi). Di VPS ini: `http://waha:3000` |
| `WAHA_WEBHOOK_TOKEN` | Token acak buatan sendiri, dikirim WAHA di header `X-SC-Token`. Tentukan sekali sebelum member menghubungkan WhatsApp |
| `N8N_BASE_URL` | Alamat n8n, untuk proksi admin NPL |
| `N8N_BLAST_WEBHOOK_URL` | Production URL webhook workflow "Sister Creative - Blast WA Member (WAHA)" |
| `N8N_BLAST_TOKEN`, `N8N_CALLBACK_TOKEN` | Dua token acak, harus sama dengan credential di workflow n8n |
| `N8N_AUTOREPLY_WEBHOOK_URL` | Production URL webhook workflow "Sister Creative - Balas Otomatis (WAHA)" |
| `AUTO_REPLY_MAX_PER_HOUR` | Batas balasan otomatis per member per jam, bawaan 30 (tidak memotong kuota blast) |
| `BLAST_DELAY_MIN`, `BLAST_DELAY_MAX` | Jeda acak antar-pesan (detik), bawaan 8–20 |
| `DEFAULT_DAILY_MESSAGE_QUOTA` | Kuota awal per member per hari, bawaan 100 |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | SMTP untuk email reset kata sandi |
| `ACCOUNT_EMAIL_VERIFICATION` | `none` (bawaan); ganti ke `mandatory` setelah SMTP berfungsi |
| `SITE_DOMAIN`, `ACME_EMAIL` | Hanya untuk Pilihan B (Caddy publik) |

Membuat token acak:

```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"
```

---

## Deploy ke VPS Hostinger

Website berjalan di VPS yang sama dengan n8n, memakai Docker Compose dengan tiga layanan:

```
Cloudflare (DNS + proxy) → reverse proxy VPS → caddy (media + teruskan) → web (Django/Gunicorn) → db (PostgreSQL)
```

### 1. Siapkan kode dan `.env`

```bash
ssh root@<ip-vps>
mkdir -p /opt && cd /opt
git clone https://github.com/sistercreativetech/sistercreative-web.git sistercreative
cd sistercreative
cp .env.example .env && nano .env      # isi semua nilai produksi (lihat tabel di atas)
chmod 600 .env
```

### 2. Reverse proxy: Traefik bawaan Hostinger

VPS ini sudah menjalankan **Traefik** (`traefik-traefik-1`, network host) dengan entrypoint
`websecure` dan certresolver `letsencrypt`. Label untuk website sudah dipasang di layanan `caddy`
pada `docker-compose.prod.yml`, mengikuti pola yang sama dengan n8n. Tidak ada port yang perlu dibuka.

Django juga bergabung ke jaringan WAHA (`waha-f516_default`), jadi di `.env` cukup diisi:

```
WAHA_BASE_URL=http://waha:3000
```

### 3. Jalankan

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
docker compose -f docker-compose.prod.yml --env-file .env ps
docker compose -f docker-compose.prod.yml --env-file .env logs -f web
```

> Server lain tanpa Traefik: pakai Caddy publik dengan
> `docker compose -f docker-compose.prod.yml -f docker-compose.public.yml --env-file .env up -d --build`
> (isi `SITE_DOMAIN` dan `ACME_EMAIL`, lalu hapus blok `networks.waha` bila tidak ada WAHA di server itu).

### 4. Buat akun admin

```bash
docker compose -f docker-compose.prod.yml --env-file .env exec web python manage.py createsuperuser
```

### 5. Pindahkan domain dari Cloudflare Worker ke VPS

> Situs lama masih dilayani Cloudflare Worker (`legacy/wrangler.jsonc`). Lepas dulu Worker-nya supaya tidak menimpa VPS.

1. Cloudflare → **Workers & Pages** → worker `sistercreative-github` → **Settings → Domains & Routes**: hapus custom domain atau route `sistercreative.tech`.
2. Cloudflare → **DNS**: buat atau ubah record `A` untuk `sistercreative.tech` dan `www` ke IP VPS, **sementara dengan status "DNS only" (awan abu-abu)**.
   Traefik memakai *HTTP challenge* Let's Encrypt, yang bisa gagal kalau lalu lintas sudah lewat proxy Cloudflare.
3. Tunggu 1–3 menit, lalu cek `https://sistercreative.tech/healthz/`. Kalau sudah tampil `{"ok": true}` dengan gembok valid, sertifikat sudah terbit.
4. Setelah itu ubah kedua record menjadi **Proxied** (awan oranye), dan atur Cloudflare → **SSL/TLS** ke mode **Full (strict)**.
   (Perpanjangan otomatis tiap ~60 hari tetap berjalan selama "Always Use HTTPS" di Cloudflare tidak memblokir `/.well-known/acme-challenge/`. Kalau perpanjangan gagal, ulangi langkah ini.)
5. Pastikan branch `feat/django-foundation` sudah digabung ke `main`, karena itu yang di-clone di VPS. Kalau repo masih terhubung ke Cloudflare Workers Builds, nonaktifkan build otomatis agar tidak mencoba men-deploy worker dari kode baru.

### 6. Sambungkan WAHA dan n8n

1. Isi `WAHA_BASE_URL`, `WAHA_API_KEY` dan `WAHA_WEBHOOK_TOKEN` di `.env`.
2. Di n8n, buka workflow **"Sister Creative - Blast WA Member (WAHA)"**:
   - node *Terima Kampanye dari Django*: credential **Header Auth**, nama `X-SC-Token`, nilai = `N8N_BLAST_TOKEN`;
   - node *Laporkan Hasil ke Django*: credential **Custom Auth** `{"headers":{"X-SC-Token":"<N8N_CALLBACK_TOKEN>"}}`;
   - salin **Production URL** webhook ke `N8N_BLAST_WEBHOOK_URL`, lalu **aktifkan** workflow.
3. Buka workflow **"Sister Creative - Balas Otomatis (WAHA)"**:
   - node *Terima Balasan dari Django*: pilih credential Header Auth **yang sama** dengan workflow Blast (`X-SC-Token` = `N8N_BLAST_TOKEN`);
   - salin **Production URL** webhook ke `N8N_AUTOREPLY_WEBHOOK_URL`, lalu **aktifkan** workflow.
4. Muat ulang website: `docker compose -f docker-compose.prod.yml --env-file .env up -d`.

### 7. Checklist setelah deploy

- [ ] `https://sistercreative.tech/healthz/` → `{"ok": true}`
- [ ] Beranda, `/portofolio/` dan detail proyek tampil normal di ponsel
- [ ] `/admin` (admin NPL lama) masih bisa dibuka dan login
- [ ] Login admin, lalu diarahkan ke `/dashboard/`
- [ ] Unggah gambar sampul portofolio, lalu gambar tampil (cek `/media/...`)
- [ ] Daftar member baru, setujui dari dashboard, lalu member bisa masuk
- [ ] Member: menu WhatsApp → QR muncul → scan → status "Terhubung"
- [ ] Kampanye uji ke 1–2 nomor sendiri → status "Terkirim" di detail kampanye
- [ ] Balas **STOP** dari nomor uji → kontak berubah menjadi "Berhenti"
- [ ] Buat aturan balas otomatis, kirim kata kuncinya dari nomor lain → pesan ditandai dibaca, muncul "mengetik…", lalu balasan masuk
- [ ] Reset kata sandi mengirim email (bila SMTP sudah diisi)

### Pembaruan

```bash
cd /opt/sistercreative
git pull
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Migrasi database berjalan otomatis saat container `web` mulai.

### Backup

```bash
chmod +x scripts/backup.sh
./scripts/backup.sh                    # hasil di ./backups (DB + file upload)
crontab -e                             # tambahkan baris di bawah untuk backup harian 02.00
0 2 * * * cd /opt/sistercreative && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Salin folder `backups/` secara berkala ke luar VPS (Google Drive, komputer lokal, dll.).

Memulihkan database:

```bash
gunzip -c backups/db-YYYYMMDD-HHMMSS.sql.gz | \
  docker compose -f docker-compose.prod.yml --env-file .env exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### Log dan masalah umum

```bash
docker compose -f docker-compose.prod.yml --env-file .env logs -f web
```

| Gejala | Penyebab umum |
|---|---|
| `400 Bad Request` | Domain belum ada di `DJANGO_ALLOWED_HOSTS` |
| Redirect berputar (`ERR_TOO_MANY_REDIRECTS`) | Cloudflare SSL bukan "Full (strict)", atau proxy tidak meneruskan `X-Forwarded-Proto` |
| Form gagal "CSRF verification failed" | `DJANGO_CSRF_TRUSTED_ORIGINS` belum diisi `https://...` |
| QR tidak muncul | `WAHA_BASE_URL`/`WAHA_API_KEY` salah, atau WAHA tidak bisa dihubungi dari container |
| Kampanye "Layanan pengiriman belum dikonfigurasi" | `N8N_BLAST_WEBHOOK_URL`/`N8N_BLAST_TOKEN` kosong |
| Balas otomatis tidak jalan | Workflow Balas Otomatis belum aktif, `N8N_AUTOREPLY_WEBHOOK_URL` kosong, atau cek status di Riwayat balas otomatis |
| Status penerima tetap "Menunggu" | Workflow n8n belum aktif, atau token callback beda dengan `N8N_CALLBACK_TOKEN` |
