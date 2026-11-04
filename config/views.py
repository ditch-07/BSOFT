from django.http import JsonResponse
from django.views.defaults import permission_denied


def api_permission_denied(request, exception):
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"detail": "You do not have permission to perform this action."},
            status=403,
        )

    return permission_denied(request, exception)
