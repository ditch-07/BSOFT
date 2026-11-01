"""Receipt number allocation.

Receipt numbers are the audit anchor for every payment, so they are
allocated by the server by default:

    RCP-YYYYMMDD-0001

The date segment is the *payment date*, not the date the row was created,
so a receipt book matches the day the money was taken. Numbers are scoped
per day and continue from the highest number already used that day.

Operators may still type a number from a pre-printed receipt book; the
model only allocates when the field is left blank.
"""
from datetime import date

RECEIPT_PREFIX = "RCP"


def receipt_prefix(on_date: date) -> str:
    """Return the receipt prefix used for a payment date."""
    return f"{RECEIPT_PREFIX}-{on_date:%Y%m%d}-"


def next_receipt_number(on_date: date | None = None) -> str:
    """Return the next unused receipt number for the given payment date."""
    from django.utils.dateparse import parse_date

    from school.models import Payment
    from school.utils.time_utils import get_current_date

    if isinstance(on_date, str):
        on_date = parse_date(on_date)
    on_date = on_date or get_current_date()
    prefix = receipt_prefix(on_date)
    used = Payment.objects.filter(
        receipt_number__startswith=prefix
    ).values_list("receipt_number", flat=True)

    highest = 0
    for number in used:
        suffix = number[len(prefix):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))

    return f"{prefix}{highest + 1:04d}"
