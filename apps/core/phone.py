"""Normalisasi nomor WhatsApp Indonesia ke format internasional tanpa tanda plus (62...)."""

import re

from django.core.exceptions import ValidationError

NON_DIGITS = re.compile(r"\D")


def normalize_whatsapp(value: str) -> str:
    """Ubah '0812-3456-7890', '+62 812 3456 7890', '812...' menjadi '6281234567890'.

    Raise ValidationError bila hasilnya bukan nomor ponsel Indonesia yang masuk akal.
    """
    digits = NON_DIGITS.sub("", value or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits

    if not digits.startswith("628") or not 10 <= len(digits) <= 15:
        raise ValidationError(
            "Masukkan nomor WhatsApp Indonesia yang valid, contoh 0812-3456-7890.",
            code="invalid_whatsapp",
        )
    return digits
