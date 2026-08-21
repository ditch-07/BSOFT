from django.urls import path

from . import views


urlpatterns = [

    # Dashboard
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),

    # Academic years
    path(
        "academic-years/",
        views.academic_year_list,
        name="academic_year_list",
    ),

    path(
        "academic-years/new/",
        views.academic_year_create,
        name="academic_year_create",
    ),

    # Semesters
    path(
        "semesters/",
        views.semester_list,
        name="semester_list",
    ),

    path(
        "semesters/new/",
        views.semester_create,
        name="semester_create",
    ),
    # Semesters
path("semesters/", views.semester_list, name="semester_list"),
path("semesters/new/", views.semester_create, name="semester_create"),
path("semesters/<int:pk>/edit/", views.semester_edit, name="semester_edit"),  # ← new

    # Students
    path(
        "students/",
        views.student_list,
        name="student_list",
    ),

    path(
        "students/new/",
        views.student_create,
        name="student_create",
    ),

    path(
        "students/<int:pk>/",
        views.student_detail,
        name="student_detail",
    ),
path(
    "courses/",
    views.course_list,
    name="course_list",
),

path(
    "courses/new/",
    views.course_create,
    name="course_create",
),
 
    # Payments
    path(
        "payments/new/",
        views.payment_create,
        name="payment_create",
    ),
    path(
    "students/search/",
    views.student_search,
    name="student_search",
),
]