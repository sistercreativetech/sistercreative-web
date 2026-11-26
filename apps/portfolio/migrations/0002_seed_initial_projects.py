"""Memindahkan tiga proyek dari situs statis lama ke database."""

from django.db import migrations
from django.utils.text import slugify

CATEGORIES = ["Aplikasi Web", "Automasi", "Administrasi"]

PROJECTS = [
    {
        "category": "Aplikasi Web",
        "title": "Admin Ngaji Privat Lombok",
        "summary": (
            "Dashboard mobile untuk melihat data murid dan guru dari Google Sheets, "
            "dilengkapi pencarian serta tombol WhatsApp."
        ),
        "description": (
            "Pengelola Ngaji Privat Lombok sebelumnya harus membuka spreadsheet yang panjang "
            "setiap kali mencari data murid atau guru dari ponsel.\n\n"
            "Kami membuat dashboard web mobile yang membaca data langsung dari Google Sheets "
            "melalui n8n. Admin cukup mengetik nama untuk menemukan murid atau guru, lalu "
            "menghubungi mereka lewat tombol WhatsApp. Tim tetap mencatat di Google Sheets "
            "seperti biasa."
        ),
        "client_name": "Ngaji Privat Lombok",
        "tags": ["Google Sheets", "n8n", "Web Mobile"],
    },
    {
        "category": "Automasi",
        "title": "Bot Laporan Pembayaran",
        "summary": (
            "Alur pencatatan transaksi, bukti transfer, penyimpanan data, "
            "dan laporan berkala melalui Telegram."
        ),
        "description": (
            "Bukti transfer yang dikirim lewat chat sering tercecer dan harus disalin "
            "manual ke catatan keuangan.\n\n"
            "Bot Telegram ini menerima foto bukti transfer, menyimpannya ke Google Drive, "
            "mencatat nominal dan tanggal ke spreadsheet, lalu mengirim rekap berkala "
            "kepada pengelola."
        ),
        "client_name": "",
        "tags": ["Telegram", "Drive", "Reporting"],
    },
    {
        "category": "Administrasi",
        "title": "Input Data Otomatis",
        "summary": (
            "Sistem yang mengubah pesan terstruktur menjadi data rapi "
            "dan mengurangi pekerjaan input manual."
        ),
        "description": (
            "Tim administrasi menerima banyak pesan dengan format yang sama setiap hari "
            "dan menyalinnya satu per satu ke spreadsheet.\n\n"
            "Workflow ini membaca pesan terstruktur, memisahkan setiap kolom, menyimpannya "
            "ke Google Sheets, dan mengirim notifikasi bila ada data yang tidak lengkap."
        ),
        "client_name": "",
        "tags": ["Workflow", "Sheets", "Notification"],
    },
]


def seed(apps, schema_editor):
    Category = apps.get_model("portfolio", "Category")
    Tag = apps.get_model("portfolio", "Tag")
    Project = apps.get_model("portfolio", "Project")

    categories = {}
    for order, name in enumerate(CATEGORIES, start=1):
        categories[name], _ = Category.objects.get_or_create(
            slug=slugify(name), defaults={"name": name, "order": order}
        )

    for order, data in enumerate(PROJECTS, start=1):
        slug = slugify(data["title"])
        if Project.objects.filter(slug=slug).exists():
            continue
        project = Project.objects.create(
            title=data["title"],
            slug=slug,
            category=categories[data["category"]],
            summary=data["summary"],
            description=data["description"],
            client_name=data["client_name"],
            is_published=True,
            is_featured=True,
            order=order,
        )
        for tag_name in data["tags"]:
            tag, _ = Tag.objects.get_or_create(slug=slugify(tag_name), defaults={"name": tag_name})
            project.tags.add(tag)


class Migration(migrations.Migration):
    dependencies = [("portfolio", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
