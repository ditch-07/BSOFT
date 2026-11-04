@permission_required("school.view_student", raise_exception=True)
def archive_detail(request, pk):
    """Read-only student file: identity, academic history and money to date."""
    student = get_object_or_404(
        Student.objects.select_related("program", "intake_year"), pk=pk
    )
    today = get_current_date()

    enrollments = list(
        student.enrollments.select_related(
            "program", "semester", "semester__academic_year"
        ).order_by("semester__academic_year__name", "semester__number")
    )
    semester_ids = [enrollment.semester_id for enrollment in enrollments]

    years_attended = sorted({e.semester.academic_year.name for e in enrollments})
    join_year = student.intake_year.name

    completion_year = None
    expected_completion_year = None

    if student.status == Student.COMPLETED:
        if enrollments:
            completion_year = enrollments[-1].semester.academic_year.name
    else:
        try:
            start_year = int(student.intake_year.name)
            expected_completion_year = str(
                start_year + student.program.duration_years - 1
            )
        except (TypeError, ValueError):
            expected_completion_year = None

    # ---------------------------------------------------------
    # MONEY (batched: two aggregates for the whole page)
    # ---------------------------------------------------------

    charged_by_semester = {
        row["enrollment__semester_id"]: row["total"]
        for row in student.charges.filter(
            enrollment__semester_id__in=semester_ids
        )
        .values("enrollment__semester_id")
        .annotate(total=Sum("amount"))
    }
    paid_by_semester = {
        row["semester_id"]: row["total"]
        for row in student.payments.filter(semester_id__in=semester_ids)
        .values("semester_id")
        .annotate(total=Sum("amount"))
    }

    total_charged = (
        student.charges.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )
    total_paid = (
        student.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )

    semester_rows = []
    for enrollment in enrollments:
        semester = enrollment.semester
        charged = charged_by_semester.get(semester.pk) or Decimal("0")
        paid = paid_by_semester.get(semester.pk) or Decimal("0")
        semester_rows.append({
            "semester": semester,
            "year_level": enrollment.year_level,
            "enrollment": enrollment,
            "status": enrollment.get_status_display(),
            "status_raw": enrollment.status,
            "charged": charged,
            "paid": paid,
            "balance": charged - paid,
            "is_current": semester.start_date <= today <= semester.end_date,
        })

    payments = list(
        student.payments.select_related(
            "semester", "semester__academic_year"
        ).order_by("-payment_date", "-id")[:20]
    )
    payment_count = student.payments.count()
    status_logs = list(student.status_logs.all()[:10])

    current = current_enrollment(
        [e for e in enrollments if e.status == Enrollment.ACTIVE], today
    )

    # Money is only shown to people who may already see it elsewhere.
    show_financials = (
        request.user.has_perm("school.can_view_financial_reports")
        or request.user.has_perm("school.can_record_payments")
    )

    return render(request, "school/student_archive_detail.html", {
        "student": student,
        "semester_rows": semester_rows,
        "payments": payments,
        "payment_count": payment_count,
        "status_logs": status_logs,
        "years_attended": years_attended,
        "join_year": join_year,
        "completion_year": completion_year,
        "expected_completion_year": expected_completion_year,
        "total_charged": total_charged,
        "total_paid": total_paid,
        "balance": total_charged - total_paid,
        "current_enrollment": current,
        "show_financials": show_financials,
        "today": today,
    })
