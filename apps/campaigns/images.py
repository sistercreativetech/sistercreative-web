"""Gambar kampanye: diperkecil, EXIF dibuang, disimpan dengan nama acak."""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_SIDE = 1600
JPEG_QUALITY = 82


def campaign_image_path(instance, filename: str) -> str:
    # Nama acak tak tertebak; tidak memuat id member atau nama file asli.
    return f"campaigns/{uuid.uuid4().hex}.jpg"


def prepare_image(upload) -> ContentFile:
    """Kembalikan JPEG baru (maks 1600 px, tanpa EXIF/GPS) dari file unggahan."""
    upload.seek(0)
    with Image.open(upload) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            rgba = image.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((MAX_SIDE, MAX_SIDE))
        buffer = BytesIO()
        # Tanpa argumen exif=..., data EXIF (termasuk lokasi GPS) tidak ikut tersimpan.
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return ContentFile(buffer.getvalue(), name="gambar.jpg")
