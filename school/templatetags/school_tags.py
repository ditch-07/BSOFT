from django import template
from django.conf import settings
from django.urls import reverse

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using a variable key."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def sub(value, arg):
    """Subtract arg from value."""
    try:
        return value - arg
    except (ValueError, TypeError):
        return value


@register.filter
def mul(value, arg):
    """Multiply value by arg."""
    try:
        return value * arg
    except (ValueError, TypeError):
        return value


@register.filter
def div(value, arg):
    """Divide value by arg."""
    try:
        if arg == 0:
            return 0
        return value / arg
    except (ValueError, TypeError):
        return value


# Access rules without an @ prefix are Django permission codenames.
SIDEBAR_ROUTES = {
    "dashboard": ("Dashboard", "dashboard", "dashboard", "@login", ("dashboard",)),
    "students": (
        "Students", "students", "student_list", "school.view_student",
        ("student_list", "student_create", "student_import", "student_edit",
         "student_search", "student_list_search", "student_detail", "student_status_change"),
    ),
    "archive": (
        "Archive", "archive", "archive_list", "school.view_student",
        ("archive_list", "archive_search", "archive_detail"),
    ),
    "enrollment": (
        "Enrollment report", "enrollment", "enrollment_report", "school.view_student",
        ("enrollment_report",),
    ),
    "status-history": (
        "Status history", "history", "status_history_report", "school.view_studentstatuslog",
        ("status_history_report",),
    ),
    "financial-records": (
        "Financial records", "ledger", "financial_records", "school.can_view_financial_reports",
        ("financial_records",),
    ),
    "outstanding": (
        "Outstanding", "outstanding", "outstanding_report", "school.can_view_outstanding_reports",
        ("outstanding_report",),
    ),
    "daily-collections": (
        "Daily collections", "collections", "daily_collections_report", "school.can_view_financial_reports",
        ("daily_collections_report",),
    ),
    "payment-methods": (
        "Payment methods", "payment", "payment_methods_report", "school.can_view_financial_reports",
        ("payment_methods_report",),
    ),
    "revenue": (
        "Revenue", "revenue", "program_revenue_report", "school.can_view_financial_reports",
        ("program_revenue_report",),
    ),
    "academic-years": (
        "Academic years", "calendar", "academic_year_list", "school.view_academicyear",
        ("academic_year_list",),
    ),
    "semesters": (
        "Semesters", "semester", "semester_list", "school.view_semester",
        ("semester_list", "semester_create", "semester_edit"),
    ),
    "fees": (
        "Fees", "fees", "fee_structure_list", "@fees",
        ("fee_structure_list", "fee_structure_create", "fee_structure_edit",
         "fee_structure_copy", "bulk_fee_configuration"),
    ),
    "trades": (
        "Trades", "trade", "program_list", "school.view_program",
        ("program_list", "program_create"),
    ),
    "fee-audit": (
        "Fee audit", "search", "fee_audit_report", "school.view_feestructure",
        ("fee_audit_report",),
    ),
    "users": (
        "Users", "users", "user_list", "@superuser", ("user_list", "user_create"),
    ),
    "audit-trail": (
        "Audit trail", "audit", "audit_log_list", "school.view_auditlog", ("audit_log_list",),
    ),
    "backups": (
        "Backups", "backup", "backup_index", "@superuser",
        ("backup_index", "backup_settings", "backup_create", "backup_download",
         "backup_restore", "backup_upload"),
    ),
    "administration": ("Administration", "shield", "admin:index", "@staff", ()),
    "time-override": (
        "Time override", "clock", "time_override", "@time-override", ("time_override",),
    ),
    "reports": ("Reports index", "reports", "reports_index", "@login", ("reports_index",)),
}

SIDEBAR_GROUPS = (
    ("people", "People", ("students", "archive", "enrollment", "status-history")),
    ("money", "Money", ("financial-records", "outstanding", "daily-collections", "payment-methods", "revenue")),
    ("academics", "Academics", ("academic-years", "semesters", "fees", "trades", "fee-audit")),
    ("system", "System", ("users", "audit-trail", "backups", "administration", "time-override")),
)


@register.inclusion_tag("school/_sidebar.html", takes_context=True)
def sidebar_navigation(context):
    """Build only permitted links; never query school data from navigation."""
    request = context.get("request")
    user = getattr(request, "user", None) or context.get("user")
    if not user or not user.is_authenticated:
        return {"sidebar_groups": [], "sidebar_dashboard": None, "sidebar_reports": None}

    match = getattr(request, "resolver_match", None)
    current_name = getattr(match, "url_name", "") or ""
    in_admin = "admin" in (getattr(match, "namespaces", ()) or ())
    semester = context.get("nav_semester")
    time_enabled = context.get(
        "ENABLE_TIME_OVERRIDE", getattr(settings, "ENABLE_TIME_OVERRIDE", False)
    )
    links = {}
    for key, (label, icon, route, access, owners) in SIDEBAR_ROUTES.items():
        args = ()
        if access == "@fees":
            if semester and user.has_perm("school.view_feestructure"):
                args = (semester.pk,)
            elif user.has_perm("school.view_semester"):
                route = "semester_list"
            else:
                continue
        elif access == "@superuser":
            if not user.is_superuser:
                continue
        elif access == "@staff":
            if not user.is_staff:
                continue
        elif access == "@time-override":
            if not (user.is_superuser and time_enabled):
                continue
        elif access != "@login" and not user.has_perm(access):
            continue
        links[key] = {
            "id": key,
            "label": label,
            "icon": icon,
            "route": route,
            "url": reverse(route, args=args),
            "url_names": owners,
            "active": in_admin if key == "administration" else not in_admin and current_name in owners,
        }

    groups = []
    for key, label, item_ids in SIDEBAR_GROUPS:
        items = [links[item_id] for item_id in item_ids if item_id in links]
        if not items:
            continue
        active = any(item["active"] for item in items)
        groups.append({
            "id": key,
            "label": label,
            "items": items,
            "active": active,
            "open": active or key != "system",
        })
    return {
        "sidebar_dashboard": links["dashboard"],
        "sidebar_groups": groups,
        "sidebar_reports": links["reports"],
        "sidebar_storage_key": f"school:sidebar:v1:{user.pk}",
    }
