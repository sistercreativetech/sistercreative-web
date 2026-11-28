"""Menyusun isi email per pelanggan (HTML + teks biasa).

Isi kampanye adalah teks biasa yang di-escape oleh template; admin tidak
menempel HTML mentah, sehingga tidak ada markup yang bisa disisipkan.
"""

import re
from dataclasses import dataclass

from django.conf import settings
from django.template.loader import render_to_string

from apps.contacts.messages import render_message

from .models import EmailCampaign

VARIABLE = re.compile(r"\{([a-zA-Z_]+)\}")
VARIABLES = {
    "nama": "Nama lengkap pelanggan",
    "nama_depan": "Kata pertama dari nama pelanggan",
}
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str


def unknown_variables(*texts: str) -> list[str]:
    seen = []
    for text in texts:
        for name in VARIABLE.findall(text or ""):
            if name not in VARIABLES and name not in seen:
                seen.append(name)
    return seen


def paragraphs(body: str) -> list[str]:
    body = (body or "").replace("\r\n", "\n").strip()
    return [p.strip() for p in PARAGRAPH_BREAK.split(body) if p.strip()]


def absolute(path: str) -> str:
    return settings.SITE_URL.rstrip("/") + path


def render_email(campaign: EmailCampaign, *, name: str, unsubscribe_url: str) -> RenderedEmail:
    subject = " ".join(render_message(campaign.subject, name=name).split())
    body = render_message(campaign.body, name=name)
    context = {
        "subject": subject,
        "paragraphs": paragraphs(body),
        "button_label": campaign.button_label,
        "button_url": campaign.button_url,
        "unsubscribe_url": unsubscribe_url,
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
    }
    return RenderedEmail(
        subject=subject,
        html=render_to_string("emails/campaign.html", context),
        text=render_to_string("emails/campaign.txt", context).strip() + "\n",
    )
