"""Konten statis landing page. Portofolio diambil dari database (apps.portfolio)."""

TRUST_POINTS = [
    "Solusi sesuai kebutuhan",
    "Ramah untuk UMKM",
    "Pendampingan jelas",
]

HERO_FLOW = [
    {"title": "Data masuk", "detail": "Form, WhatsApp, atau Telegram"},
    {"title": "Diproses otomatis", "detail": "n8n dan integrasi aplikasi", "active": True},
    {"title": "Laporan siap", "detail": "Google Sheets dan notifikasi"},
]

SERVICES = [
    {
        "icon": "globe",
        "title": "Website & Landing Page",
        "description": (
            "Website profil, halaman promosi, dan landing page yang responsif "
            "di ponsel maupun komputer."
        ),
    },
    {
        "icon": "smartphone",
        "title": "Aplikasi Web Mobile",
        "description": (
            "Dashboard dan aplikasi ringan untuk mengelola data pelanggan, murid, "
            "guru, atau transaksi."
        ),
    },
    {
        "icon": "bot",
        "title": "Bot WhatsApp & Telegram",
        "description": (
            "Bot untuk menerima data, memberikan balasan, mengirim pengingat, dan menyusun laporan."
        ),
    },
    {
        "icon": "workflow",
        "title": "Automasi Pekerjaan",
        "description": (
            "Hubungkan formulir, Google Sheets, Drive, email, dan aplikasi lain "
            "agar tugas berulang berjalan otomatis."
        ),
    },
    {
        "icon": "megaphone",
        "title": "Konten & Media Sosial",
        "description": (
            "Perencanaan konten, desain promosi, copywriting, dan materi visual "
            "yang selaras dengan identitas usaha."
        ),
    },
]


PROCESS_STEPS = [
    {
        "title": "Konsultasi kebutuhan",
        "description": "Kami mempelajari masalah, pengguna, dan hasil yang ingin dicapai.",
    },
    {
        "title": "Rancangan solusi",
        "description": "Alur, fitur, tampilan, biaya, dan waktu pengerjaan disepakati bersama.",
    },
    {
        "title": "Pembuatan dan pengujian",
        "description": (
            "Sistem dibuat lalu diuji agar nyaman digunakan pada perangkat yang dibutuhkan."
        ),
    },
    {
        "title": "Serah terima",
        "description": (
            "Anda menerima hasil akhir beserta panduan penggunaan dan pendampingan awal."
        ),
    },
]

WHATSAPP_MESSAGES = {
    "hero": "Halo Sister Creative, saya ingin konsultasi tentang layanan digital.",
    "contact": "Halo Sister Creative, saya ingin konsultasi tentang website atau automasi.",
}
