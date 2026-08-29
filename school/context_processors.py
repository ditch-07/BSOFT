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