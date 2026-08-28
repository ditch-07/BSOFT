from django.conf import settings
from django.contrib.auth.views import redirect_to_login


EXEMPT_PATHS = ("/login/", "/logout/", "/static/", "/admin/")


class LoginRequiredMiddleware:
    """Require authentication for all paths except exempt ones."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path
            if not any(path.startswith(p) for p in EXEMPT_PATHS):
                return redirect_to_login(
                    request.get_full_path(), login_url=settings.LOGIN_URL
                )
        return self.get_response(request)