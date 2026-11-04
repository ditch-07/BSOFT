from django.urls import path
from django.contrib.auth import views as auth_views

from . import api, views


urlpatterns = [
    # Authentication
    path("login/", auth_views.LoginView.as_view(template_name="school/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

# JSON API endpoints
    path("api/auth/check/", api.api_auth_check_public, name="api_auth_check"),
    path("api/auth/login/", api.api_auth_login, name="api_auth_login"),
    path("api/auth/logout/", api.api_auth_logout, name="api_auth_logout"),
    path("api/dashboard/", api.api_dashboard, name="api_dashboard"),
    path("api/programs/", api.api_program_list, name="api_program_list"),
    path("api/programs/create/", api.api_program_create, name="api_program_create"),
    path("api/programs/<int:pk>/", api.api_program_detail, name="api_program_detail"),
    path("api/programs/<int:pk>/edit/", api.api_program_update, name="api_program_update"),
    path("api/academic-years/", api.api_academic_year_list, name="api_academic_year_list"),
    path("api/academic-years/create/", api.api_academic_year_create, name="api_api_academic_year_create"),
    path("api/academic-years/<int:pk>/", api.api_academic_year_detail, name="api_academic_year_detail"),
    path("api/academic-years/<int:pk>/edit/", api.api_academic_year_update, name="api_academic_year_update"),
    path("api/semesters/", api.api_semester_list, name="api_semester_list"),
    path("api/semesters/create/", api.api_semester_create, name="api_semester_create"),
    path("api/semesters/<int:pk>/", api.api_semester_detail, name="api_semester_detail"),
    path("api/semesters/<int:pk>/edit/", api.api_semester_update, name="api_semester_update"),
    path("api/semesters/<int:semester_id>/fee-structures/", api.api_fee_structure_list, name="api_fee_structure_list"),
    path("api/semesters/<int:semester_id>/fee-structures/create/", api.api_fee_structure_create, name="api_fee_structure_create"),
    path("api/fee-structures/<int:pk>/edit/", api.api_fee_structure_update, name="api_fee_structure_update"),
    path("api/semesters/<int:semester_id>/fee-structures/bulk/", api.api_bulk_fee_configuration, name="api_bulk_fee_configuration"),
    path("api/students/", api.api_student_list, name="api_student_list"),
    path("api/students/search/", api.api_student_search, name="api_student_search"),
    path("api/students/create/", api.api_student_create, name="api_student_create"),
    path("api/students/import/preview/", api.api_student_import_preview, name="api_student_import_preview"),
    path("api/students/import/confirm/", api.api_student_import_confirm, name="api_student_import_confirm"),
    path("api/students/<int:pk>/", api.api_student_detail, name="api_student_detail"),
    path("api/students/<int:pk>/patch/", api.api_student_patch, name="api_student_patch"),
    path("api/students/<int:pk>/status/", api.api_student_status_change, name="api_student_status_change"),
    path("api/archive/students/", api.api_archive_list, name="api_archive_list"),
    path("api/archive/students/<int:pk>/", api.api_archive_detail, name="api_archive_detail"),

    # Payments API
    path("api/payments/", api.api_payment_list, name="api_payment_list"),
    path("api/payments/create/", api.api_payment_create, name="api_payment_create"),
    path("api/payments/<int:pk>/", api.api_payment_detail, name="api_payment_detail"),
    path("api/payments/<int:pk>/receipt/", api.api_payment_receipt, name="api_payment_receipt"),
    path("api/financial-records/", api.api_financial_records, name="api_financial_records"),
    path("api/students/<int:pk>/payment-history/", api.api_student_payment_history, name="api_student_payment_history"),
    path("api/students/<int:student_id>/balance/<int:semester_id>/", api.api_student_balance, name="api_student_balance"),
    path("api/students/<int:student_id>/enrollments-for-payment/", api.api_student_enrollments_for_payment, name="api_student_enrollments_for_payment"),

    # Reports API
    path("api/reports/", api.api_reports_index, name="api_reports_index"),
    path("api/reports/enrollment/", api.api_enrollment_report, name="api_enrollment_report"),
    path("api/reports/outstanding/", api.api_outstanding_report, name="api_outstanding_report"),
    path("api/reports/fee-audit/", api.api_fee_audit_report, name="api_fee_audit_report"),
    path("api/reports/payment-methods/", api.api_payment_methods_report, name="api_payment_methods_report"),
    path("api/reports/program-revenue/", api.api_program_revenue_report, name="api_program_revenue_report"),
    path("api/reports/daily-collections/", api.api_daily_collections_report, name="api_daily_collections_report"),
    path("api/reports/status-history/", api.api_status_history_report, name="api_status_history_report"),

    # Reminders API
    path("api/reminders/", api.api_reminders, name="api_reminders"),

    # Administration API
    path("api/users/", api.api_user_list, name="api_user_list"),
    path("api/users/create/", api.api_user_create, name="api_user_create"),
    path("api/users/<int:pk>/", api.api_user_update, name="api_user_update"),
    path("api/audit-logs/", api.api_audit_log_list, name="api_audit_log_list"),
    path("api/backups/", api.api_backup_list, name="api_backup_list"),
    path("api/backups/create/", api.api_backup_create, name="api_backup_create"),
    path("api/backups/download/<path:filename>/", api.api_backup_download, name="api_backup_download"),
    path("api/backups/restore/<path:filename>/", api.api_backup_restore, name="api_backup_restore"),
    path("api/backups/upload/", api.api_backup_upload, name="api_backup_upload"),
    path("api/backup/settings/", api.api_backup_settings, name="api_backup_settings"),
    path("api/time-override/", api.api_time_override, name="api_time_override"),

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
        "semesters/<int:semester_id>/fee-structures/copy/",
        views.fee_structure_copy,
        name="fee_structure_copy",
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
    path("students/import/", views.student_import, name="student_import"),
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
