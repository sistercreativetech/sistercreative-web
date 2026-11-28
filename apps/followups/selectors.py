from datetime import timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from .models import FollowUpEnrollment, FollowUpMessage, FollowUpSequence, FollowUpStep

# Pesan yang masih "dalam antrean" lebih lama dari ini dianggap macet dan tidak memakan kuota.
PENDING_COUNTS_FOR = timedelta(hours=6)


def sequences_for(owner) -> QuerySet[FollowUpSequence]:
    return FollowUpSequence.objects.filter(owner=owner)


def sequences_with_stats(owner) -> QuerySet[FollowUpSequence]:
    active = FollowUpEnrollment.Status.ACTIVE
    return sequences_for(owner).annotate(
        step_count=Count("steps", distinct=True),
        active_count=Count("enrollments", filter=Q(enrollments__status=active), distinct=True),
        total_count=Count("enrollments", distinct=True),
    )


def steps_for(owner) -> QuerySet[FollowUpStep]:
    return FollowUpStep.objects.filter(sequence__owner=owner).select_related("sequence")


def enrollments_for(owner) -> QuerySet[FollowUpEnrollment]:
    return FollowUpEnrollment.objects.filter(sequence__owner=owner).select_related(
        "sequence", "next_step"
    )


def messages_for(owner) -> QuerySet[FollowUpMessage]:
    return FollowUpMessage.objects.filter(owner=owner).select_related(
        "enrollment__sequence", "step"
    )


def messages_used_since(owner, since) -> int:
    """Pesan follow-up yang terkirim sejak `since` + yang masih antre (untuk kuota harian)."""
    recent = timezone.now() - PENDING_COUNTS_FOR
    return (
        FollowUpMessage.objects.filter(owner=owner)
        .filter(
            Q(status=FollowUpMessage.Status.SENT, sent_at__gte=since)
            | Q(status=FollowUpMessage.Status.PENDING, created_at__gte=recent)
        )
        .count()
    )
