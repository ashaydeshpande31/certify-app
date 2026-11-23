"""Demo mode: visitors can try the whole app without signing in. Every action works except the
final send, which needs a real Google sign-in (Certify sends from the user's own Gmail)."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

GUEST_PREFIX = "guest_"
GUEST_MAX_ITEMS = 3          # events and updates a demo visitor may create
GUEST_LIFETIME = timedelta(hours=24)

OWNER_CONTACT_URL = getattr(settings, "OWNER_CONTACT_URL", "https://www.linkedin.com/in/ashay-deshpande-554683387")

BLOCK_MESSAGE = (
    "Sign in required. This is a demo, so nothing was sent. Certify sends from your own Gmail, "
    "and the app is still in Google's test mode, so to use it for real, contact the owner to add "
    "your Gmail address as a test user, then sign in with Google."
)


def is_guest(user):
    return bool(user and user.is_authenticated and user.username.startswith(GUEST_PREFIX))


def guest_context(request):
    """Template variables: is_guest and the owner's contact link."""
    return {"is_guest": is_guest(getattr(request, "user", None)), "owner_contact_url": OWNER_CONTACT_URL}


def guest_block_json(extra=None):
    data = {"guest": True, "stop": True, "error": BLOCK_MESSAGE, "sent": 0, "failed": 0, "remaining": 1,
            "sent_total": 0, "failed_total": 0, "total": 0, "used_24h": 0, "daily_limit": 0}
    if extra:
        data.update(extra)
    return data


def _clean_old_guests():
    User = get_user_model()
    User.objects.filter(username__startswith=GUEST_PREFIX, date_joined__lt=timezone.now() - GUEST_LIFETIME).delete()


@require_POST
def try_demo(request):
    """Start a throw-away demo account for this browser."""
    if is_guest(request.user):
        return redirect("home")
    if request.user.is_authenticated:
        return redirect("home")
    _clean_old_guests()
    User = get_user_model()
    user = User(username=GUEST_PREFIX + secrets.token_hex(6))
    user.set_unusable_password()
    user.save()
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("home")


def sign_in(request):
    """Leave the demo (if in it) and go to the Google sign-in."""
    if is_guest(request.user):
        logout(request)
    return redirect("/accounts/google/login/?process=login")
