from django.db import transaction
from django.utils.text import slugify

from .models import Project, Tag


def parse_tag_names(text: str) -> list[str]:
    """'n8n, Google Sheets ,n8n' -> ['n8n', 'Google Sheets'].

    Urutan dipertahankan, tanpa duplikat (dibandingkan lewat slug).
    """
    seen, names = set(), []
    for raw in (text or "").split(","):
        name = " ".join(raw.split())[:40]
        key = slugify(name)
        if name and key and key not in seen:
            seen.add(key)
            names.append(name)
    return names


@transaction.atomic
def set_project_tags(project: Project, text: str) -> None:
    tags = []
    for name in parse_tag_names(text):
        tag = Tag.objects.filter(slug=slugify(name)).first() or Tag.objects.create(name=name)
        tags.append(tag)
    project.tags.set(tags)


def tags_as_text(project: Project) -> str:
    return ", ".join(project.tags.values_list("name", flat=True)) if project.pk else ""
