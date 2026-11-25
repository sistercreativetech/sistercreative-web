from django.conf import settings


def site(request):
    """Info situs yang dipakai di semua template."""
    return {
        "site_name": settings.SITE_NAME,
        "contact_whatsapp": settings.CONTACT_WHATSAPP,
    }
