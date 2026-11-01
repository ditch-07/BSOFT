from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.defaults import permission_denied


def nuxt_app(request):
    index_path = (
        settings.BASE_DIR / "frontend" / ".output" / "public" / "index.html"
    )
    if not index_path.is_file():
        return HttpResponse(
            "The Vue frontend has not been generated. Run `npm run generate` "
            "from the frontend directory.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    return HttpResponse(
        index_path.read_text(encoding="utf-8"),
        content_type="text/html; charset=utf-8",
    )


def api_permission_denied(request, exception):
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"detail": "You do not have permission to perform this action."},
            status=403,
        )

    return permission_denied(request, exception)
