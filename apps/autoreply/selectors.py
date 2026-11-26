from datetime import timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from .models import AutoReplyLog, AutoReplyRule


def rules_for(owner) -> QuerySet[AutoReplyRule]:
    return AutoReplyRule.objects.filter(owner=owner)


def rules_with_stats(owner) -> QuerySet[AutoReplyRule]:
    since = timezone.now() - timedelta(days=7)
    return (
        rules_for(owner)
        .annotate(
            replies_7d=Count(
                "logs",
                filter=Q(logs__created_at__gte=since, logs__status=AutoReplyLog.Status.QUEUED),
            )
        )
        .order_by("priority", "pk")
    )


def logs_for(owner) -> QuerySet[AutoReplyLog]:
    return AutoReplyLog.objects.filter(owner=owner).select_related("rule")


def replies_last_24h(owner) -> int:
    since = timezone.now() - timedelta(hours=24)
    return AutoReplyLog.objects.filter(
        owner=owner, created_at__gte=since, status=AutoReplyLog.Status.QUEUED
    ).count()
