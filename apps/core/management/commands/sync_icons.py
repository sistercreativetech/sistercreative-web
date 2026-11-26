import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.icons import ICONS

SVG_BODY = re.compile(r"<svg[^>]*>(?P<body>.*)</svg>", re.DOTALL)


class Command(BaseCommand):
    help = "Salin isi SVG ikon Lucide (dari apps/core/icons.py) ke templates/components/icons/."

    def handle(self, *args, **options):
        source = settings.BASE_DIR / "node_modules" / "lucide-static" / "icons"
        target = settings.BASE_DIR / "templates" / "components" / "icons"
        if not source.is_dir():
            raise CommandError("lucide-static belum terpasang. Jalankan `npm install` dulu.")
        target.mkdir(parents=True, exist_ok=True)

        for name in ICONS:
            svg_file = source / f"{name}.svg"
            if not svg_file.exists():
                raise CommandError(f"Ikon Lucide '{name}' tidak ditemukan.")
            match = SVG_BODY.search(svg_file.read_text(encoding="utf-8"))
            if not match:
                raise CommandError(f"Format SVG '{name}' tidak dikenali.")
            body = "\n".join(line.strip() for line in match["body"].strip().splitlines())
            (target / f"{name}.html").write_text(body + "\n", encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"{len(ICONS)} ikon disalin ke {target}"))
