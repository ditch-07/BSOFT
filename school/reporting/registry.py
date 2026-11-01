from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSpec:
    slug: str
    title: str
    question: str
    description: str
    view: str
    permission: str
    group: str
    orientation: str
    filename_stem: str


REPORTS = (
    ReportSpec("financial", "Financial records", "How did each semester do?", "Billed, collected, owed and credit by academic year.", "financial_records", "school.can_view_financial_reports", "Money", "landscape", "financial_records"),
    ReportSpec("enrollment", "Enrollment summary", "Who is enrolled?", "Students by trade, intake year and status.", "enrollment_report", "school.view_student", "People", "landscape", "enrollment_summary"),
    ReportSpec("outstanding", "Outstanding balances", "Who still owes fees?", "Students owing for a selected course year and semester.", "outstanding_report", "school.can_view_outstanding_reports", "Money", "landscape", "outstanding_balances"),
    ReportSpec("fee-audit", "Fee setup check", "Are fees set up?", "Trades and course years still missing fee items.", "fee_audit_report", "school.view_feestructure", "Setup", "portrait", "fee_setup_check"),
    ReportSpec("payment-methods", "Payment methods", "How are people paying?", "Payment totals and transaction counts by method.", "payment_methods_report", "school.can_view_financial_reports", "Money", "portrait", "payment_methods"),
    ReportSpec("program-revenue", "Revenue by trade", "Which trades are paying?", "Billed, collected, owed and credit by trade.", "program_revenue_report", "school.can_view_financial_reports", "Money", "landscape", "revenue_by_trade"),
    ReportSpec("daily-collections", "Daily collections", "What was collected?", "Receipts and cash-up totals for a date or date range.", "daily_collections_report", "school.can_view_financial_reports", "Money", "landscape", "daily_collections"),
    ReportSpec("status-history", "Status history", "What changed?", "Student status updates with notes and dates.", "status_history_report", "school.view_studentstatuslog", "People", "landscape", "status_history"),
)

REPORT_BY_VIEW = {spec.view: spec for spec in REPORTS}


def permitted_reports(user):
    return tuple(spec for spec in REPORTS if user.has_perm(spec.permission))
