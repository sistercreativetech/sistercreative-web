from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from PIL import Image

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]


def validate_image_upload(file, max_bytes=None):
    """Batasi ukuran & tipe gambar. Format dicek dari isi file, bukan hanya ekstensi."""
    limit = max_bytes or settings.MAX_IMAGE_UPLOAD_BYTES
    if file.size > limit:
        raise ValidationError(
            f"Ukuran gambar maksimal {filesizeformat(limit)}.", code="file_too_large"
        )

    position = file.tell() if hasattr(file, "tell") else None
    try:
        with Image.open(file) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        raise ValidationError("File bukan gambar yang valid.", code="invalid_image") from exc
    finally:
        if position is not None:
            file.seek(position)

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Format gambar harus JPG, PNG, atau WebP.", code="invalid_format")
