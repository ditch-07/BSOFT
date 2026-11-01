from decimal import Decimal

ZERO = Decimal("0.00")
DEFINITIONS = {
    "billed": "Billed = charges assigned to the selected semester.",
    "collected": "Collected = payments recorded for the selected semester.",
    "owed": "Owed = the sum of positive per-student balances; credits are excluded.",
    "credit": "Credit = the sum of per-student overpayments.",
    "net": "Net outstanding = Billed − Collected = Owed − Credit.",
}


def positive_balance_totals(rows):
    """Return per-student positive Owed and positive Credit from (charged, paid)."""
    owed = ZERO
    credit = ZERO
    for charged, paid in rows:
        balance = (charged or ZERO) - (paid or ZERO)
        if balance > 0:
            owed += balance
        elif balance < 0:
            credit -= balance
    return {"owed": owed, "credit": credit, "net": owed - credit}
