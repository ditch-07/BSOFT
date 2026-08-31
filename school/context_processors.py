from django.conf import settings
from school.models import BackupConfig


def time_override_enabled(request):
    return {
        'ENABLE_TIME_OVERRIDE': getattr(settings, 'ENABLE_TIME_OVERRIDE', False),
    }


def backup_config(request):
    config = BackupConfig.get_config()
    return {
        'backup_config': config,
        'backup_available': config.is_backup_available(),
    }


def reminders_count(request):
    """Add reminders count to context for all templates."""
    if request.user.is_authenticated:
        from school.models import students_with_missing_details
        try:
            count = students_with_missing_details().count()
            return {'reminders_count': count}
        except Exception:
            return {'reminders_count': 0}
    return {'reminders_count': 0}