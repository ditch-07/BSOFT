from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [
    # Authentication
    path("login/", auth_views.LoginView.as_view(template_name="school/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    # Dashboard
    path("", views.dashboard, name="dashboard"),
    
    # Reminders
    path("reminders/", views.reminders, name="reminders"),

    # Reports
    path("reports/", views.reports_index, name="reports_index"),
    path("reports/enrollment/", views.enrollment_report, name="enrollment_report"),
    path("reports/outstanding/", views.outstanding_report, name="outstanding_report"),
    path("reports/fee-audit/", views.fee_audit_report, name="fee_audit_report"),
    path("reports/payment-methods/", views.payment_methods_report, name="payment_methods_report"),
    path("reports/program-revenue/", views.program_revenue_report, name="program_revenue_report"),
    path("reports/daily-collections/", views.daily_collections_report, name="daily_collections_report"),
    path("reports/status-history/", views.status_history_report, name="status_history_report"),

    # Academic years
    path("academic-years/", views.academic_year_list, name="academic_year_list"),

    # Semesters
    path("semesters/", views.semester_list, name="semester_list"),
    path("semesters/new/", views.semester_create, name="semester_create"),
    path("semesters/<int:pk>/edit/", views.semester_edit, name="semester_edit"),

    # Fee structures (Program + Year Level + Semester)
    path(
        "semesters/<int:semester_id>/fee-structures/",
        views.fee_structure_list,
        name="fee_structure_list",
    ),
    path(
        "semesters/<int:semester_id>/fee-structures/new/",
        views.fee_structure_create,
        name="fee_structure_create",
    ),
    path(
        "semesters/<int:semester_id>/fee-structures/bulk/",
        views.bulk_fee_configuration,
        name="bulk_fee_configuration",
    ),
    path(
        "fee-structures/<int:pk>/edit/",
        views.fee_structure_edit,
        name="fee_structure_edit",
    ),

    # Programs (formerly Courses)
    path("programs/", views.program_list, name="program_list"),
    path("programs/new/", views.program_create, name="program_create"),

    # Students
    path("students/", views.student_list, name="student_list"),
    path("students/new/", views.student_create, name="student_create"),
    path("students/<int:pk>/edit/", views.student_edit, name="student_edit"),
    path("students/search/", views.student_search, name="student_search"),
    path("students/list-search/", views.student_list_search, name="student_list_search"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path(
        "students/<int:pk>/status/",
        views.student_status_change,
        name="student_status_change",
    ),

    # Student Archive
    path("students/archive/", views.archive_list, name="archive_list"),
    path("students/archive/search/", views.archive_search, name="archive_search"),
    path("students/archive/<int:pk>/", views.archive_detail, name="archive_detail"),

    # Payments
    path("payments/new/", views.payment_create, name="payment_create"),
    path("financial-records/", views.financial_records, name="financial_records"),

    # Time Override (Testing)
    path("time-override/", views.time_override_view, name="time_override"),

    # User Management (Admin only)
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),

    # Audit Log
    path("audit-log/", views.audit_log_list, name="audit_log_list"),

    # Backup & Restore (Superuser only)
    path("backups/", views.backup_index, name="backup_index"),
    path("backups/create/", views.backup_create, name="backup_create"),
    path("backups/download/<path:filename>/", views.backup_download, name="backup_download"),
    path("backups/restore/<path:filename>/", views.backup_restore, name="backup_restore"),
    path("backups/upload/", views.backup_upload, name="backup_upload"),
    path("backup/settings/", views.backup_settings, name="backup_settings"),

    path(
    "semesters/<int:semester_id>/progress/",
    views.bulk_progress_students,
    name="bulk_progress_students",
),
]
