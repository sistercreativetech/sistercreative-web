from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import EmailCampaign, EmailRecipient, MailingList, Subscriber

Recipient = EmailRecipient


def lists_with_counts():
    return MailingList.objects.annotate(
        subscribed_count=Count(
            "subscribers", filter=Q(subscribers__status=Subscriber.Status.SUBSCRIBED)
        )
    ).order_by("name")


def subscribers(*, query: str = "", status: str = "", mailing_list=None):
    queryset = Subscriber.objects.prefetch_related("lists")
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(name__icontains=query))
    if status in Subscriber.Status.values:
        queryset = queryset.filter(status=status)
    if mailing_list is not None:
        queryset = queryset.filter(lists=mailing_list)
    return queryset


def campaigns_with_counts():
    return EmailCampaign.objects.annotate(
        total_count=Count("recipients"),
        sent_count=Count("recipients", filter=Q(recipients__status=Recipient.Status.SENT)),
        failed_count=Count("recipients", filter=Q(recipients__status=Recipient.Status.FAILED)),
    ).order_by("-created_at", "-pk")


def target_subscribers(campaign: EmailCampaign, *, now=None):
    """Pelanggan aktif yang dituju kampanye (tanpa duplikat)."""
    queryset = Subscriber.objects.filter(status=Subscriber.Status.SUBSCRIBED)
    if not campaign.send_to_all:
        queryset = queryset.filter(lists__in=campaign.lists.all())
    if campaign.skip_recent_days:
        since = (now or timezone.now()) - timedelta(days=campaign.skip_recent_days)
        queryset = queryset.exclude(last_emailed_at__gte=since)
    return queryset.distinct().order_by("pk")


def emails_used_since(since) -> int:
    """Email terkirim sejak `since` + yang sedang diproses n8n (dihitung batas harian)."""
    return Recipient.objects.filter(
        Q(status=Recipient.Status.SENT, sent_at__gte=since) | Q(status=Recipient.Status.QUEUED)
    ).count()
