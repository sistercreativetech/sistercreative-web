from django.db.models import Count, QuerySet

from apps.accounts.models import User
from apps.portfolio.models import Category, Project


def members() -> QuerySet[User]:
    return User.objects.filter(is_staff=False)


def pending_members(limit: int | None = None) -> QuerySet[User]:
    queryset = members().filter(status=User.Status.PENDING).order_by("date_joined")
    return queryset[:limit] if limit else queryset


def overview_stats() -> dict:
    member_qs = members()
    return {
        "pending_members": member_qs.filter(status=User.Status.PENDING).count(),
        "active_members": member_qs.filter(status=User.Status.ACTIVE).count(),
        "published_projects": Project.objects.filter(is_published=True).count(),
        "draft_projects": Project.objects.filter(is_published=False).count(),
    }


def all_projects() -> QuerySet[Project]:
    return Project.objects.select_related("category").prefetch_related("tags")


def categories_with_counts() -> QuerySet[Category]:
    return Category.objects.annotate(project_count=Count("projects"))
