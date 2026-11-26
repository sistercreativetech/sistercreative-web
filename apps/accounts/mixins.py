from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


class StaffRequiredMixin(AccessMixin):
    """Hanya admin (is_staff). Tamu diarahkan ke login, member biasa mendapat 403."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            raise PermissionDenied("Halaman ini khusus admin.")
        return super().dispatch(request, *args, **kwargs)


class ApprovedMemberRequiredMixin(AccessMixin):
    """Member yang sudah disetujui (admin juga boleh). Yang menunggu diarahkan ke halaman status."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        if not (user.is_staff or user.is_approved_member):
            return redirect("members:pending")
        return super().dispatch(request, *args, **kwargs)
