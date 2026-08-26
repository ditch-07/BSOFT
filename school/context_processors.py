from django.conf import settings


def time_override_enabled(request):
    return {
        'ENABLE_TIME_OVERRIDE': getattr(settings, 'ENABLE_TIME_OVERRIDE', False)
    }