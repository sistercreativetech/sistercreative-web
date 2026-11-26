from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class AccountAdapter(DefaultAccountAdapter):
    """Arahkan admin ke dashboard dan member ke area member setelah login/daftar."""

    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_authenticated and user.is_staff:
            return reverse("dashboard:home")
        return reverse("members:home")
