from django.conf import settings
from django.core.management.base import BaseCommand

from apps.whatsapp import services, waha
from apps.whatsapp.models import WhatsAppSession


class Command(BaseCommand):
    help = (
        "Perbarui webhook semua sesi WAHA member ke SITE_URL dan WAHA_WEBHOOK_TOKEN saat ini. "
        "Jalankan setelah mengganti SITE_URL atau WAHA_WEBHOOK_TOKEN."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Tampilkan rencana tanpa mengubah apa pun."
        )

    def handle(self, *args, **options):
        url = services.webhook_url()
        self.stdout.write(f"Webhook tujuan: {url}")
        updated = failed = skipped = 0
        for session in WhatsAppSession.objects.order_by("pk"):
            try:
                remote = waha.get_session(session.name)
            except waha.WahaError as exc:
                failed += 1
                self.stderr.write(f"  {session.name}: gagal membaca status ({exc})")
                continue
            if remote is None:
                skipped += 1
                self.stdout.write(f"  {session.name}: belum dibuat di WAHA, dilewati")
                continue
            if options["dry_run"]:
                self.stdout.write(
                    f"  {session.name}: akan diperbarui (status {remote.get('status')})"
                )
                continue
            try:
                waha.update_session_webhooks(session.name, url, settings.WAHA_WEBHOOK_TOKEN)
            except waha.WahaError as exc:
                failed += 1
                self.stderr.write(f"  {session.name}: gagal diperbarui ({exc})")
                continue
            updated += 1
            self.stdout.write(f"  {session.name}: diperbarui")
        summary = f"Selesai: {updated} diperbarui, {skipped} dilewati, {failed} gagal."
        self.stdout.write(
            self.style.SUCCESS(summary) if not failed else self.style.WARNING(summary)
        )
