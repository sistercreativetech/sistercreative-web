from apps.accounts.models import User
from apps.portfolio.models import Project


def overview_stats() -> dict:
    members = User.objects.filter(is_staff=False)
    return {
        "pending_members": members.filter(status=User.Status.PENDING).count(),
        "active_members": members.filter(status=User.Status.ACTIVE).count(),
        "published_projects": Project.objects.filter(is_published=True).count(),
        "draft_projects": Project.objects.filter(is_published=False).count(),
    }
