from django.db.models import Count, Q, QuerySet

from .models import Contact, ContactGroup, MessageTemplate


def contacts_for(owner) -> QuerySet[Contact]:
    return Contact.objects.filter(owner=owner).prefetch_related("groups")


def groups_for(owner) -> QuerySet[ContactGroup]:
    return ContactGroup.objects.filter(owner=owner).annotate(
        contact_count=Count("contacts", distinct=True),
        active_count=Count("contacts", filter=Q(contacts__is_opted_out=False), distinct=True),
    )


def templates_for(owner) -> QuerySet[MessageTemplate]:
    return MessageTemplate.objects.filter(owner=owner)


def member_overview(owner) -> dict:
    contacts = Contact.objects.filter(owner=owner)
    return {
        "contacts": contacts.count(),
        "opted_out": contacts.filter(is_opted_out=True).count(),
        "groups": ContactGroup.objects.filter(owner=owner).count(),
        "templates": MessageTemplate.objects.filter(owner=owner).count(),
    }
