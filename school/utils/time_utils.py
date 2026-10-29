"""
Time utilities for the application.
Provides helpers that respect the time override for testing.
"""
from datetime import datetime
from django.utils import timezone
from django.conf import settings


def get_current_datetime():
    """
    Returns either the frozen datetime or real now.
    """
    if getattr(settings, 'ENABLE_TIME_OVERRIDE', False):
        from school.models import TimeOverride
        frozen = TimeOverride.get_frozen_time()
        if frozen is not None:
            if timezone.is_naive(frozen):
                frozen = timezone.make_aware(frozen)
            return frozen
    return timezone.now()


def get_current_date():
    """
    Returns the date part of current datetime.
    """
    return get_current_datetime().date()


def get_working_semester(today=None):
    """Return the current semester, otherwise the next future one, or None."""
    from school.models import Semester

    if today is None:
        today = get_current_date()
    semesters = Semester.objects.select_related("academic_year").order_by(
        "start_date", "pk"
    )
    current = semesters.filter(start_date__lte=today, end_date__gte=today).first()
    if current is not None:
        return current
    return semesters.filter(start_date__gt=today).first()


def get_current_time():
    """
    Returns the time part of current datetime.
    """
    return get_current_datetime().time()