from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse


EXEMPT_PATHS = (
    "/login",
    "/logout/",
    "/static/",
    "/admin/",
    "/api/auth/check/",
    "/api/auth/login/",
)


class LoginRequiredMiddleware:
    """Require authentication for all paths except exempt ones."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path
            if any(path.startswith(p) for p in EXEMPT_PATHS):
                return self.get_response(request)
            if path.startswith("/api/"):
                return JsonResponse(
                    {"detail": "Authentication credentials were not provided."},
                    status=401,
                )
            return redirect_to_login(
                request.get_full_path(), login_url=settings.LOGIN_URL
            )
        return self.get_response(request)