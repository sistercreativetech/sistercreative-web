"""Logika perubahan status member. Dipakai Django admin dan dashboard."""

from django.db import transaction
from django.utils import timezone

from .models import User


@transaction.atomic
def set_member_status(user: User, status: str, *, by: User | None = None) -> User:
    if status not in User.Status.values:
        raise ValueError(f"Status tidak dikenal: {status}")
    user.status = status
    # Member yang ditolak/dinonaktifkan tidak bisa login sama sekali.
    user.is_active = status in {User.Status.PENDING, User.Status.ACTIVE}
    user.status_changed_at = timezone.now()
    user.status_changed_by = by
    user.save(update_fields=["status", "is_active", "status_changed_at", "status_changed_by"])
    return user


def approve_member(user: User, *, by: User | None = None) -> User:
    return set_member_status(user, User.Status.ACTIVE, by=by)


def reject_member(user: User, *, by: User | None = None) -> User:
    return set_member_status(user, User.Status.REJECTED, by=by)


def suspend_member(user: User, *, by: User | None = None) -> User:
    return set_member_status(user, User.Status.SUSPENDED, by=by)
