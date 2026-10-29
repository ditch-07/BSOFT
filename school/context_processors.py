from django.conf import settings
from django.core.cache import cache

from school.models import BackupConfig
from school.utils.time_utils import (
    get_current_date,
    get_current_datetime,
    get_working_semester,
)


NAVIGATION_CACHE_KEY = "school:navigation-summary:v1"
NAVIGATION_CACHE_SECONDS = 45


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


def navigation_summary(request):
    empty = {
        "reminders_count": 0,
        "nav_semester": None,
        "nav_semester_is_upcoming": False,
        "nav_testing_date": None,
        "nav_fee_count": 0,
        "nav_attention_count": 0,
    }
    if not request.user.is_authenticated:
        return empty

    try:
        summary = cache.get(NAVIGATION_CACHE_KEY)
        if summary is None:
            from school.models import (
                TimeOverride,
                students_with_missing_details,
                unconfigured_fee_structures,
            )

            today = get_current_date()
            semester = get_working_semester(today)
            is_upcoming = bool(semester and semester.start_date > today)

            testing_date = None
            if getattr(settings, "ENABLE_TIME_OVERRIDE", False):
                frozen = TimeOverride.get_frozen_time()
                if frozen is not None:
                    testing_date = get_current_datetime().date()

            summary = {
                "semester": semester,
                "is_upcoming": is_upcoming,
                "testing_date": testing_date,
                "fee_count": (
                    len(unconfigured_fee_structures(semester)) if semester else 0
                ),
                "reminders_count": students_with_missing_details().count(),
            }
            cache.set(
                NAVIGATION_CACHE_KEY,
                summary,
                NAVIGATION_CACHE_SECONDS,
            )

        can_add_fees = request.user.has_perm("school.add_feestructure")
        fee_count = summary["fee_count"] if can_add_fees else 0
        return {
            "reminders_count": summary["reminders_count"],
            "nav_semester": summary["semester"],
            "nav_semester_is_upcoming": summary["is_upcoming"],
            "nav_testing_date": summary["testing_date"],
            "nav_fee_count": summary["fee_count"],
            "nav_attention_count": summary["reminders_count"] + fee_count,
        }
    except Exception:
        return empty
