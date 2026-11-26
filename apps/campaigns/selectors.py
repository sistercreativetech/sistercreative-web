from django.db.models import Count, Q, QuerySet

from .models import Campaign, CampaignRecipient

Status = CampaignRecipient.Status


def _with_counts(queryset: QuerySet[Campaign]) -> QuerySet[Campaign]:
    return queryset.annotate(
        total_count=Count("recipients"),
        sent_count=Count("recipients", filter=Q(recipients__status=Status.SENT)),
        failed_count=Count("recipients", filter=Q(recipients__status=Status.FAILED)),
        pending_count=Count("recipients", filter=Q(recipients__status=Status.PENDING)),
    ).order_by("-created_at")


def campaigns_for(owner) -> QuerySet[Campaign]:
    """Kampanye milik member yang belum dihapus."""
    return Campaign.objects.filter(owner=owner, deleted_at__isnull=True)


def campaigns_with_counts(owner) -> QuerySet[Campaign]:
    return _with_counts(campaigns_for(owner))


def all_campaigns_with_counts() -> QuerySet[Campaign]:
    return _with_counts(Campaign.objects.select_related("owner"))
