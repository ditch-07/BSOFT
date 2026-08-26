from django.urls import path

from . import views


urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

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
    path("students/search/", views.student_search, name="student_search"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path(
        "students/<int:pk>/status/",
        views.student_status_change,
        name="student_status_change",
    ),

    # Payments
    path("payments/new/", views.payment_create, name="payment_create"),
    path("financial-records/", views.financial_records, name="financial_records"),

    # Time Override (Testing)
    path("time-override/", views.time_override_view, name="time_override"),

    path(
    "semesters/<int:semester_id>/progress/",
    views.bulk_progress_students,
    name="bulk_progress_students",
),
]
