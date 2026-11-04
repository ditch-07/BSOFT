@permission_required("school.view_student", raise_exception=True)
def archive_list(request):
    """Every student file, including the ones no longer active."""
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip().upper()
    program_filter = request.GET.get("program", "").strip()
    intake_filter = request.GET.get("intake", "").strip()

    valid_statuses = {value for value, _ in Student.STATUS_CHOICES}
    if status_filter not in valid_statuses:
        status_filter = ""

    today = get_current_date()
    students = Student.objects.select_related("program", "intake_year")

    if query:
        students = students.filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if status_filter:
        students = students.filter(status=status_filter)
    if program_filter:
        students = students.filter(program_id=program_filter)
    if intake_filter:
        students = students.filter(intake_year__name=intake_filter)

    students = students.order_by("last_name", "first_name")

    status_counts = {
        row["status"]: row["count"]
        for row in Student.objects.values("status").annotate(count=Count("id"))
    }
    program_counts = (
        Student.objects.values("program__id", "program__name")
        .annotate(count=Count("id"))
        .order_by("program__name")
    )
    intake_years = (
        AcademicYear.objects.filter(students__isnull=False)
        .distinct()
        .order_by("-name")
    )

    filtered_count = students.count()
    page_obj = Paginator(students, 20).get_page(request.GET.get("page"))

    # One query for the whole page instead of get_current_enrollment() per row.
    page_students = list(page_obj)
    enrollments_by_student = defaultdict(list)
    for enrollment in (
        Enrollment.objects.filter(
            student__in=page_students,
            status=Enrollment.ACTIVE,
        )
        .select_related("semester")
        .order_by("-semester__academic_year__name", "-semester__number")
    ):
        enrollments_by_student[enrollment.student_id].append(enrollment)

    for student in page_students:
        student.current_enrollment = current_enrollment(
            enrollments_by_student.get(student.pk, []), today
        )

    return render(request, "school/student_archive_list.html", {
        "page_obj": page_obj,
        "query": query,
        "status_filter": status_filter,
        "program_filter": program_filter,
        "intake_filter": intake_filter,
        "status_choices": Student.STATUS_CHOICES,
        "status_counts": status_counts,
        "program_counts": program_counts,
        "intake_years": intake_years,
        "total_students": sum(status_counts.values()),
        "filtered_count": filtered_count,
        "today": today,
    })
