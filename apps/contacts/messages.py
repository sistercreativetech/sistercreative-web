"""Variabel personalisasi pesan: {nama}, {nama_depan}, {nomor}.

Penggantian dilakukan dengan regex sederhana (bukan str.format), sehingga isi
pesan tidak bisa mengakses atribut objek apa pun.
"""

import re

VARIABLE = re.compile(r"\{([a-zA-Z_]+)\}")

VARIABLES = {
    "nama": "Nama lengkap kontak",
    "nama_depan": "Kata pertama dari nama kontak",
    "nomor": "Nomor WhatsApp kontak",
}

# Dipakai bila kontak tidak punya nama.
NAME_FALLBACK = "Bapak/Ibu"


def unknown_variables(body: str) -> list[str]:
    seen = []
    for name in VARIABLE.findall(body or ""):
        if name not in VARIABLES and name not in seen:
            seen.append(name)
    return seen


def render_message(body: str, *, name: str = "", phone: str = "") -> str:
    name = " ".join((name or "").split())
    values = {
        "nama": name or NAME_FALLBACK,
        "nama_depan": name.split(" ")[0] if name else NAME_FALLBACK,
        "nomor": f"+{phone}" if phone else "",
    }
    return VARIABLE.sub(lambda match: values.get(match.group(1), match.group(0)), body or "")
