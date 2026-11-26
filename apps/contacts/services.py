"""Impor kontak dari CSV dan operasi kontak lain milik satu member."""

import csv
import io
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.phone import normalize_whatsapp

from .models import Contact, ContactGroup

NAME_HEADERS = {"nama", "name", "nama lengkap", "full name", "nama kontak"}
PHONE_HEADERS = {
    "nomor",
    "no",
    "no hp",
    "no. hp",
    "nomor hp",
    "nomor whatsapp",
    "no wa",
    "no. wa",
    "whatsapp",
    "wa",
    "hp",
    "telepon",
    "telp",
    "phone",
    "phone number",
    "mobile",
}
MAX_REPORTED_ERRORS = 20


@dataclass
class ImportResult:
    created: int = 0
    existing: int = 0
    duplicates_in_file: int = 0
    skipped_over_limit: int = 0
    invalid_count: int = 0
    invalid_rows: list[tuple[int, str, str]] = field(default_factory=list)
    group: ContactGroup | None = None

    @property
    def total_valid(self) -> int:
        return self.created + self.existing


class ImportFileError(Exception):
    """File CSV tidak bisa dibaca sama sekali."""


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFileError("File tidak bisa dibaca. Simpan ulang sebagai CSV UTF-8.")


def _delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text else ""
    counts = {delim: first_line.count(delim) for delim in (";", ",", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _columns(header: list[str]) -> tuple[int | None, int | None]:
    cleaned = [cell.strip().lower() for cell in header]
    name_col = next((i for i, cell in enumerate(cleaned) if cell in NAME_HEADERS), None)
    phone_col = next((i for i, cell in enumerate(cleaned) if cell in PHONE_HEADERS), None)
    return name_col, phone_col


def _looks_like_phone(value: str) -> bool:
    try:
        normalize_whatsapp(value)
    except ValidationError:
        return False
    return True


def parse_csv(raw: bytes) -> list[tuple[int, str, str]]:
    """Kembalikan [(nomor_baris, nama, nomor_mentah)] dari isi file CSV."""
    text = _decode(raw)
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=_delimiter(text))]
    rows = [(i, row) for i, row in enumerate(rows, start=1) if any(cell.strip() for cell in row)]
    if not rows:
        raise ImportFileError("File CSV kosong.")

    name_col, phone_col = _columns(rows[0][1])
    if phone_col is not None:
        data_rows = rows[1:]
    else:
        # Tanpa header yang dikenali: [nama, nomor] atau hanya [nomor].
        first = rows[0][1]
        if len(first) == 1:
            name_col, phone_col = None, 0
        else:
            name_col, phone_col = 0, 1
        data_rows = rows if _looks_like_phone(first[phone_col]) else rows[1:]

    max_rows = settings.CONTACT_IMPORT_MAX_ROWS
    if len(data_rows) > max_rows:
        raise ImportFileError(
            f"Maksimal {max_rows} baris per impor. Pecah file menjadi beberapa bagian."
        )

    parsed = []
    for line_no, row in data_rows:
        name = row[name_col].strip() if name_col is not None and name_col < len(row) else ""
        phone = row[phone_col].strip() if phone_col < len(row) else ""
        parsed.append((line_no, " ".join(name.split())[:120], phone))
    return parsed


@transaction.atomic
def import_contacts(owner, raw: bytes, group: ContactGroup | None = None) -> ImportResult:
    if group is not None and group.owner_id != owner.pk:
        raise PermissionError("Grup bukan milik member ini.")
    rows = parse_csv(raw)
    result = ImportResult(group=group)

    existing = dict(Contact.objects.filter(owner=owner).values_list("phone", "pk"))
    remaining = max(settings.MAX_CONTACTS_PER_MEMBER - len(existing), 0)
    seen: set[str] = set()
    to_create: list[Contact] = []
    existing_ids: list[int] = []

    for line_no, name, raw_phone in rows:
        if "e+" in raw_phone.lower():
            result.invalid_count += 1
            if len(result.invalid_rows) < MAX_REPORTED_ERRORS:
                result.invalid_rows.append(
                    (line_no, raw_phone, "Format angka Excel (E+). Ubah kolom nomor menjadi teks.")
                )
            continue
        try:
            phone = normalize_whatsapp(raw_phone)
        except ValidationError:
            result.invalid_count += 1
            if len(result.invalid_rows) < MAX_REPORTED_ERRORS:
                result.invalid_rows.append((line_no, raw_phone or "(kosong)", "Nomor tidak valid"))
            continue

        if phone in seen:
            result.duplicates_in_file += 1
            continue
        seen.add(phone)

        if phone in existing:
            result.existing += 1
            existing_ids.append(existing[phone])
            continue
        if len(to_create) >= remaining:
            result.skipped_over_limit += 1
            continue
        to_create.append(Contact(owner=owner, name=name, phone=phone))

    Contact.objects.bulk_create(to_create)
    result.created = len(to_create)

    if group is not None:
        imported_phones = {contact.phone for contact in to_create}
        contact_ids = existing_ids + list(
            Contact.objects.filter(owner=owner, phone__in=imported_phones).values_list(
                "pk", flat=True
            )
        )
        through = Contact.groups.through
        through.objects.bulk_create(
            [through(contact_id=pk, contactgroup_id=group.pk) for pk in contact_ids],
            ignore_conflicts=True,
        )
    return result


def sample_csv() -> str:
    return "nama,nomor\nSiti Aminah,0812-3456-7890\nBudi Santoso,+62 813 2222 3333\n"
