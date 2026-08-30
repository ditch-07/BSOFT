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


def get_current_time():
    """
    Returns the time part of current datetime.
    """
    return get_current_datetime().time()