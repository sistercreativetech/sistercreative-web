from django.db.models import Count, Q, QuerySet

from .models import Category, Project, Tag


def published_projects() -> QuerySet[Project]:
    return (
        Project.objects.filter(is_published=True)
        .select_related("category")
        .prefetch_related("tags")
    )


def featured_projects(limit: int = 3) -> QuerySet[Project]:
    return published_projects().filter(is_featured=True)[:limit]


def related_projects(project: Project, limit: int = 3) -> QuerySet[Project]:
    return published_projects().filter(category=project.category).exclude(pk=project.pk)[:limit]


def categories_with_projects() -> QuerySet[Category]:
    """Kategori yang punya minimal satu proyek terbit, untuk filter."""
    return Category.objects.annotate(
        published_count=Count("projects", filter=Q(projects__is_published=True))
    ).filter(published_count__gt=0)


def tags_with_projects() -> QuerySet[Tag]:
    return Tag.objects.filter(projects__is_published=True).distinct()
