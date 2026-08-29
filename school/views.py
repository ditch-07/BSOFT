from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum, Count, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .utils.time_utils import get_current_datetime, get_current_date

from .forms import (
    AcademicYearForm,
    SemesterForm,
    ProgramForm,
    FeeStructureForm,
    FeeStructureItemFormSet,
    StudentForm,
    StudentStatusChangeForm,
    EnrollmentForm,
    PaymentForm,
    BulkFeeForm,
)

from .models import (
    AcademicYear,
    Semester,
    Program,
    FeeStructure,
    FeeStructureItem,
    Student,
    StudentStatusLog,
    Enrollment,
    StudentCharge,
    Payment,
    student_balance,
    semester_financials,
    unconfigured_fee_structures,
    outstanding_students,
    payment_methods_breakdown,
    program_revenue,
    daily_collections,
    enrollment_summary,
    student_status_history,
)

from school.reports import REPORTS


def create_academic_year_enrollments(student, start_semester, start_year_level):
    """
    Create enrollments and charges for all semesters in the academic year
    of `start_semester` from that semester onward.
    """
    academic_year = start_semester.academic_year
    semesters = Semester.objects.filter(
        academic_year=academic_year,
        number__gte=start_semester.number
    ).order_by('number')

    enrollments_created = 0
    current_year_level = start_year_level

    for sem in semesters:
        # Cap year level at program duration
        if current_year_level > student.program.duration_years:
            break

        enrollment, created = Enrollment.objects.get_or_create(
            student=student,
            semester=sem,
            defaults={
                'program': student.program,
                'year_level': current_year_level,
                'status': Enrollment.ACTIVE,
            }
        )
        if created:
            enrollments_created += 1

        fee_structure = FeeStructure.objects.filter(
            program=student.program,
            year_level=current_year_level,
            semester=sem
        ).prefetch_related('items').first()

        if fee_structure:
            for item in fee_structure.items.all():
                StudentCharge.objects.get_or_create(
                    student=student,
                    enrollment=enrollment,
                    fee_item=item,
                    defaults={'amount': item.amount}
                )

        # Year level stays the same for all semesters in the same academic year.
        # It only increments when moving to the next academic year (handled elsewhere).

    return enrollments_created


# ============================================================
# DASHBOARD
# ============================================================

@login_required
def dashboard(request):
    today = get_current_date()

    # --- Current academic period ---
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).first()
    current_semester = Semester.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
    ).select_related("academic_year").first()

    # --- Student count ---
    total_students = Student.objects.filter(status=Student.ACTIVE).count()

    # --- Financials for current semester ---
    if current_semester:
        # Use shared helper for semester financials
        fin = semester_financials(current_semester)
        total_charged = fin["charged"]
        total_paid = fin["paid"]
        outstanding = fin["outstanding"]
        collection_rate = fin["collection_rate"]

        # Students with balance & top outstanding
        outstanding_qs = outstanding_students(current_semester)
        students_with_balance = outstanding_qs.count()
        top_outstanding = outstanding_qs[:5]
    else:
        total_charged = total_paid = outstanding = Decimal("0")
        collection_rate = 0
        students_with_balance = 0
        top_outstanding = []

    # --- Expected revenue for the whole current academic year ---
    # (sum of everything billable to ACTIVE students across both semesters
    # of the current academic year, regardless of collection so far)
    expected_revenue_year = Decimal("0")
    if current_year:
        expected_revenue_year = StudentCharge.objects.filter(
            enrollment__semester__academic_year=current_year,
            enrollment__status=Enrollment.ACTIVE,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    recent_payments = Payment.objects.select_related(
        "student", "semester"
    ).order_by("-payment_date", "-id")[:10]

    today_payments = Payment.objects.filter(payment_date=today).select_related(
        "student", "semester"
    )
    today_total = today_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    upcoming_semester = (
        Semester.objects.filter(start_date__gt=today)
        .order_by("start_date")
        .first()
    )

    # Nudge the admin if the upcoming/current semester has programs with
    # no fee structure configured yet — charges can't be raised without one.
    unconfigured_fee_count = 0
    fee_setup_semester = current_semester or upcoming_semester
    if fee_setup_semester:
        unconfigured_fee_count = len(unconfigured_fee_structures(fee_setup_semester))

    # --- Auto-progression status ---
    # Find semesters that have ended but may have students not yet progressed
    ended_semesters = Semester.objects.filter(end_date__lt=today).order_by('-end_date')
    auto_progress_eligible = 0
    auto_progress_details = []
    for sem in ended_semesters:
        # Count active students in this ended semester
        active_count = Enrollment.objects.filter(
            semester=sem,
            status=Enrollment.ACTIVE,
            student__status=Student.ACTIVE,
        ).count()
        if active_count > 0:
            auto_progress_eligible += active_count
            # Check next semester
            next_sem = Semester.objects.filter(start_date__gt=sem.start_date).order_by('start_date').first()
            auto_progress_details.append({
                'semester': sem,
                'next_semester': next_sem,
                'active_students': active_count,
            })

    context = {
        "total_students": total_students,
        "current_year": current_year,
        "current_semester": current_semester,
        "total_charged": total_charged,
        "total_paid": total_paid,
        "outstanding": outstanding,
        "collection_rate": collection_rate,
        "students_with_balance": students_with_balance,
        "top_outstanding": top_outstanding,
        "expected_revenue_year": expected_revenue_year,
        "recent_payments": recent_payments,
        "today_payments": today_payments,
        "today_total": today_total,
        "upcoming_semester": upcoming_semester,
        "fee_setup_semester": fee_setup_semester,
        "unconfigured_fee_count": unconfigured_fee_count,
        "today": today,
        "auto_progress_eligible": auto_progress_eligible,
        "auto_progress_details": auto_progress_details,
    }
    return render(request, "school/dashboard.html", context)


# ============================================================
# FINANCIAL RECORDS
# ============================================================

@permission_required("school.can_view_financial_reports", raise_exception=True)
def financial_records(request):
    """
    Institution-wide financial records showing aggregate charged/paid/outstanding
    per semester, grouped by academic year.
    """
    from itertools import groupby

    year_filter = request.GET.get("academic_year", "")
    today = get_current_date()
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).first()
    default_year_id = str(current_year.pk) if current_year else ""
    selected_year_id = year_filter or default_year_id

    semesters_qs = Semester.objects.select_related("academic_year").order_by(
        "-academic_year__name", "number"
    )

    if selected_year_id:
        semesters_qs = semesters_qs.filter(academic_year_id=selected_year_id)

    semester_data = []
    for sem in semesters_qs:
        total_charged = StudentCharge.objects.filter(
            fee_item__fee_structure__semester=sem
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        total_paid = Payment.objects.filter(
            semester=sem
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        outstanding = total_charged - total_paid
        collection_rate = (total_paid / total_charged * 100) if total_charged > 0 else 0

        semester_data.append({
            "semester": sem,
            "academic_year": sem.academic_year,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "outstanding": outstanding,
            "collection_rate": collection_rate,
        })

    # Group by academic year and compute totals per year
    year_groups = []
    for year, semesters_iter in groupby(semester_data, key=lambda x: x["academic_year"]):
        semesters = list(semesters_iter)
        charged = sum(s["total_charged"] for s in semesters)
        paid = sum(s["total_paid"] for s in semesters)
        year_groups.append({
            "year": year,
            "semesters": semesters,
            "totals": {
                "charged": charged,
                "paid": paid,
                "outstanding": sum(s["outstanding"] for s in semesters),
                "collection_rate": (paid / charged * 100) if charged > 0 else 0,
            }
        })

    all_years = AcademicYear.objects.all().order_by("-name")

    selected_year = None
    if selected_year_id:
        selected_year = all_years.filter(pk=selected_year_id).first()

    grand_total_charged = sum(g["totals"]["charged"] for g in year_groups)
    grand_total_paid = sum(g["totals"]["paid"] for g in year_groups)
    grand_total_outstanding = sum(g["totals"]["outstanding"] for g in year_groups)
    grand_collection_rate = (
        (grand_total_paid / grand_total_charged * 100) if grand_total_charged > 0 else 0
    )

    context = {
        "year_groups": year_groups,
        "all_years": all_years,
        "selected_year_id": selected_year_id,
        "selected_year": selected_year,
        "current_year": current_year,
        "grand_total_charged": grand_total_charged,
        "grand_total_paid": grand_total_paid,
        "grand_total_outstanding": grand_total_outstanding,
        "grand_collection_rate": grand_collection_rate,
        "today": get_current_date(),
    }
    return render(request, "school/financial_records.html", context)


@permission_required("school.view_student", raise_exception=True)
def student_search(request):
    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({"students": []})

    students = (
        Student.objects.filter(status=Student.ACTIVE)
        .filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .order_by("last_name", "first_name")[:10]
    )

    data = []
    today = get_current_date()

    for student in students:
        # Changed from start_date__lte to end_date__gte to include upcoming semesters
        enrollment = (
            student.enrollments.filter(
                status=Enrollment.ACTIVE,
                semester__end_date__gte=today,
            )
            .select_related("program", "semester", "semester__academic_year")
            .order_by("semester__start_date")
            .first()
        )
        data.append(
            {
                "id": student.id,
                "student_number": student.student_number,
                "name": f"{student.first_name} {student.last_name}",
                "program": enrollment.program.name if enrollment else "Not enrolled",
                "semester": str(enrollment.semester) if enrollment else "No active semester",
            }
        )

    return JsonResponse({"students": data})


# ============================================================
# REPORTS
# ============================================================


@login_required
def reports_index(request):
    """Reports landing page - lists all available reports."""
    return render(request, "school/reports/index.html", {"reports": REPORTS})


def _get_filtered_semester(request, default_semester=None):
    """Helper to get selected semester from request, with default to current/upcoming."""
    today = get_current_date()
    semester_id = request.GET.get("semester")
    
    if semester_id:
        try:
            return Semester.objects.select_related("academic_year").get(pk=semester_id)
        except Semester.DoesNotExist:
            pass
    
    if default_semester:
        return default_semester
    
    # Default to current or upcoming semester
    current = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()
    if current:
        return current
    
    return Semester.objects.filter(start_date__gt=today).order_by("start_date").first()


def _get_filtered_year(request, default_year=None):
    """Helper to get selected academic year from request."""
    year_id = request.GET.get("academic_year")
    
    if year_id:
        try:
            return AcademicYear.objects.get(pk=year_id)
        except AcademicYear.DoesNotExist:
            pass
    
    if default_year:
        return default_year
    
    today = get_current_date()
    return AcademicYear.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()


def _get_filtered_program(request):
    """Helper to get selected program from request."""
    program_id = request.GET.get("program")
    if program_id:
        try:
            return Program.objects.get(pk=program_id)
        except Program.DoesNotExist:
            pass
    return None


def _export_csv_response(filename, headers, rows):
    """Helper to create CSV HttpResponse."""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


@permission_required("school.view_student", raise_exception=True)
def enrollment_report(request):
    """Student enrollment summary by program, intake year, and status."""
    program_filter = _get_filtered_program(request)
    intake_year_filter = request.GET.get("intake_year")
    status_filter = request.GET.get("status")
    export_format = request.GET.get("format")
    
    # Build queryset using helper
    data = enrollment_summary(
        program=program_filter,
        intake_year=intake_year_filter,
        status=status_filter,
    )
    
    # Add program/intake_year objects for display
    program_ids = set(d["program__id"] for d in data)
    intake_year_ids = set(d["intake_year__id"] for d in data)
    
    programs = {p.id: p for p in Program.objects.filter(id__in=program_ids)}
    intake_years = {y.id: y for y in AcademicYear.objects.filter(id__in=intake_year_ids)}
    
    for row in data:
        row["program_obj"] = programs.get(row["program__id"])
        row["intake_year_obj"] = intake_years.get(row["intake_year__id"])
    
    # CSV Export
    if export_format == "csv":
        headers = ["Program", "Program Code", "Intake Year", "Status", "Student Count"]
        rows = [
            [
                r["program_obj"].name if r["program_obj"] else "Unknown",
                r["program_obj"].code if r["program_obj"] else "",
                r["intake_year_obj"].name if r["intake_year_obj"] else "Unknown",
                dict(Student.STATUS_CHOICES).get(r["status"], r["status"]),
                r["count"],
            ]
            for r in data
        ]
        return _export_csv_response("enrollment_summary.csv", headers, rows)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(data, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    all_programs = Program.objects.filter(active=True).order_by("name")
    all_intake_years = AcademicYear.objects.all().order_by("-name")
    
    context = {
        "page_obj": page_obj,
        "program_filter": program_filter,
        "intake_year_filter": intake_year_filter,
        "status_filter": status_filter,
        "all_programs": all_programs,
        "all_intake_years": all_intake_years,
        "status_choices": Student.STATUS_CHOICES,
        "today": get_current_date(),
        "report": next((r for r in REPORTS if r["view"] == "enrollment_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/enrollment.html", context)


@permission_required("school.can_view_outstanding_reports", raise_exception=True)
def outstanding_report(request):
    """Students with outstanding balances for a semester."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()
    
    semester = _get_filtered_semester(request, current_semester)
    program_filter = _get_filtered_program(request)
    export_format = request.GET.get("format")
    
    students_qs = outstanding_students(semester)
    if program_filter:
        students_qs = students_qs.filter(program=program_filter)
    
    # CSV Export
    if export_format == "csv":
        headers = [
            "Student Number", "Name", "Program", "Semester",
            "Charged", "Paid", "Outstanding", "Collection %"
        ]
        rows = []
        for s in students_qs:
            charged = s.charged or Decimal("0")
            paid = s.paid or Decimal("0")
            rows.append([
                s.student_number,
                f"{s.first_name} {s.last_name}",
                s.program.name,
                str(semester),
                f"{charged:.2f}",
                f"{paid:.2f}",
                f"{charged - paid:.2f}",
                f"{(paid / charged * 100) if charged > 0 else 0:.1f}",
            ])
        return _export_csv_response(
            f"outstanding_balances_{semester.academic_year.name}_sem{semester.number}.csv",
            headers, rows
        )
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(students_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    # Compute totals for summary cards
    total_charged = sum(s.charged or Decimal("0") for s in students_qs)
    total_paid = sum(s.paid or Decimal("0") for s in students_qs)
    total_outstanding = total_charged - total_paid
    avg_outstanding = (total_outstanding / students_qs.count()) if students_qs.count() > 0 else Decimal("0")
    
    all_semesters = Semester.objects.select_related("academic_year").order_by(
        "-academic_year__name", "number"
    )
    all_programs = Program.objects.filter(active=True).order_by("name")
    
    context = {
        "semester": semester,
        "page_obj": page_obj,
        "program_filter": program_filter,
        "all_semesters": all_semesters,
        "all_programs": all_programs,
        "today": today,
        "total_charged": total_charged,
        "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "avg_outstanding": avg_outstanding,
        "total_students": students_qs.count(),
        "report": next((r for r in REPORTS if r["view"] == "outstanding_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/outstanding.html", context)


@permission_required("school.view_feestructure", raise_exception=True)
def fee_audit_report(request):
    """Programs/year-levels missing fee structure configurations."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()
    
    semester = _get_filtered_semester(request, current_semester)
    export_format = request.GET.get("format")
    
    missing = unconfigured_fee_structures(semester)
    
    # CSV Export
    if export_format == "csv":
        headers = ["Program", "Program Code", "Year Level", "Semester", "Academic Year"]
        rows = [
            [m["program"].name, m["program"].code, m["year_level"], str(semester), semester.academic_year.name]
            for m in missing
        ]
        return _export_csv_response(
            f"fee_audit_{semester.academic_year.name}_sem{semester.number}.csv",
            headers, rows
        )
    
    all_semesters = Semester.objects.select_related("academic_year").order_by(
        "-academic_year__name", "number"
    )
    
    context = {
        "semester": semester,
        "missing": missing,
        "all_semesters": all_semesters,
        "today": today,
        "report": next((r for r in REPORTS if r["view"] == "fee_audit_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/fee_audit.html", context)


@permission_required("school.can_view_financial_reports", raise_exception=True)
def payment_methods_report(request):
    """Payment breakdown by method for a semester."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()
    
    semester = _get_filtered_semester(request, current_semester)
    export_format = request.GET.get("format")
    
    breakdown = payment_methods_breakdown(semester)
    
    # Get display names for methods
    method_choices = dict(Payment.PAYMENT_METHODS)
    for item in breakdown:
        item["method_display"] = method_choices.get(item["method"], item["method"])
    
    # Compute totals for summary cards
    total_transactions = sum(item["count"] or 0 for item in breakdown)
    total_amount = sum(item["total"] for item in breakdown)
    
    # CSV Export
    if export_format == "csv":
        headers = ["Method", "Transaction Count", "Total Amount"]
        rows = [
            [item["method_display"], item["count"] or 0, f"{item['total']:.2f}"]
            for item in breakdown
        ]
        return _export_csv_response(
            f"payment_methods_{semester.academic_year.name}_sem{semester.number}.csv",
            headers, rows
        )
    
    all_semesters = Semester.objects.select_related("academic_year").order_by(
        "-academic_year__name", "number"
    )
    
    context = {
        "semester": semester,
        "breakdown": breakdown,
        "all_semesters": all_semesters,
        "today": today,
        "total_transactions": total_transactions,
        "total_amount": total_amount,
        "report": next((r for r in REPORTS if r["view"] == "payment_methods_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/payment_methods.html", context)


@permission_required("school.can_view_financial_reports", raise_exception=True)
def program_revenue_report(request):
    """Revenue comparison across programs for a semester."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()
    
    semester = _get_filtered_semester(request, current_semester)
    export_format = request.GET.get("format")
    
    revenue_data = program_revenue(semester)
    
    for item in revenue_data:
        charged = item["charged"] or Decimal("0")
        paid = item["paid"] or Decimal("0")
        item["outstanding"] = charged - paid
        item["collection_rate"] = (paid / charged * 100) if charged > 0 else 0
    
    # Compute totals for summary cards
    total_charged = sum(item["charged"] or Decimal("0") for item in revenue_data)
    total_paid = sum(item["paid"] or Decimal("0") for item in revenue_data)
    total_outstanding = sum(item["outstanding"] for item in revenue_data)
    overall_collection_rate = (total_paid / total_charged * 100) if total_charged > 0 else 0
    
    # CSV Export
    if export_format == "csv":
        headers = ["Program", "Program Code", "Charged", "Paid", "Outstanding", "Collection %"]
        rows = [
            [
                item["fee_item__fee_structure__program__name"],
                item["fee_item__fee_structure__program__code"],
                f"{item['charged']:.2f}",
                f"{item['paid']:.2f}",
                f"{item['outstanding']:.2f}",
                f"{item['collection_rate']:.1f}",
            ]
            for item in revenue_data
        ]
        return _export_csv_response(
            f"program_revenue_{semester.academic_year.name}_sem{semester.number}.csv",
            headers, rows
        )
    
    all_semesters = Semester.objects.select_related("academic_year").order_by(
        "-academic_year__name", "number"
    )
    
    context = {
        "semester": semester,
        "revenue_data": revenue_data,
        "all_semesters": all_semesters,
        "today": today,
        "total_charged": total_charged,
        "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "overall_collection_rate": overall_collection_rate,
        "report": next((r for r in REPORTS if r["view"] == "program_revenue_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/program_revenue.html", context)


@permission_required("school.can_view_financial_reports", raise_exception=True)
def daily_collections_report(request):
    """Daily collections / cashbook report."""
    today = get_current_date()
    date_filter = request.GET.get("date")
    
    if date_filter:
        try:
            from datetime import datetime
            filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
        except ValueError:
            filter_date = today
    else:
        filter_date = today
    
    export_format = request.GET.get("format")
    
    payments = daily_collections(filter_date)
    total = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    avg_transaction = (total / payments.count()) if payments.count() > 0 else Decimal("0")
    
    # CSV Export
    if export_format == "csv":
        headers = ["Receipt", "Student", "Student Number", "Semester", "Method", "Amount", "Reference", "Date"]
        rows = [
            [
                p.receipt_number,
                f"{p.student.first_name} {p.student.last_name}",
                p.student.student_number,
                str(p.semester),
                p.get_method_display(),
                f"{p.amount:.2f}",
                p.reference or "",
                p.payment_date.isoformat(),
            ]
            for p in payments
        ]
        rows.append(["", "", "", "", "TOTAL", f"{total:.2f}", "", ""])
        return _export_csv_response(
            f"daily_collections_{filter_date.isoformat()}.csv",
            headers, rows
        )
    
    context = {
        "filter_date": filter_date,
        "payments": payments,
        "total": total,
        "avg_transaction": avg_transaction,
        "today": today,
        "report": next((r for r in REPORTS if r["view"] == "daily_collections_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/daily_collections.html", context)


@permission_required("school.view_studentstatuslog", raise_exception=True)
def status_history_report(request):
    """Student status change history."""
    today = get_current_date()
    student_filter = request.GET.get("student")
    start_date_filter = request.GET.get("start_date")
    end_date_filter = request.GET.get("end_date")
    export_format = request.GET.get("format")
    
    student = None
    if student_filter:
        try:
            student = Student.objects.get(pk=student_filter)
        except Student.DoesNotExist:
            pass
    
    logs = student_status_history(
        student=student,
        start_date=start_date_filter,
        end_date=end_date_filter,
    )
    
    # CSV Export
    if export_format == "csv":
        headers = ["Date Changed", "Student", "Student Number", "Program", "Status", "Note"]
        rows = [
            [
                log.date_changed.strftime("%Y-%m-%d %H:%M"),
                f"{log.student.first_name} {log.student.last_name}",
                log.student.student_number,
                log.student.program.name,
                log.get_status_display(),
                log.note or "",
            ]
            for log in logs
        ]
        return _export_csv_response("status_history.csv", headers, rows)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    all_students = Student.objects.select_related("program").order_by("last_name", "first_name")
    
    context = {
        "page_obj": page_obj,
        "student_filter": student,
        "start_date_filter": start_date_filter,
        "end_date_filter": end_date_filter,
        "all_students": all_students,
        "today": today,
        "report": next((r for r in REPORTS if r["view"] == "status_history_report"), None),
        "reports": REPORTS,
    }
    return render(request, "school/reports/status_history.html", context)
    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({"students": []})

    students = (
        Student.objects.filter(status=Student.ACTIVE)
        .filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .order_by("last_name", "first_name")[:10]
    )

    data = []
    today = get_current_date()

    for student in students:
        # Changed from start_date__lte to end_date__gte to include upcoming semesters
        enrollment = (
            student.enrollments.filter(
                status=Enrollment.ACTIVE,
                semester__end_date__gte=today,
            )
            .select_related("program", "semester", "semester__academic_year")
            .order_by("semester__start_date")
            .first()
        )
        data.append(
            {
                "id": student.id,
                "student_number": student.student_number,
                "name": f"{student.first_name} {student.last_name}",
                "program": enrollment.program.name if enrollment else "Not enrolled",
                "semester": str(enrollment.semester) if enrollment else "No active semester",
            }
        )

    return JsonResponse({"students": data})

# ============================================================
# ACADEMIC YEARS
# ============================================================

@permission_required("school.view_academicyear", raise_exception=True)
def academic_year_list(request):
    years = AcademicYear.objects.all().order_by("-name")
    paginator = Paginator(years, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "school/academic_year_list.html", {
        "page_obj": page_obj,
        "today": get_current_date(),
    })


# ============================================================
# SEMESTERS
# (Fee structures are configured separately — see below — since a
# semester now covers several Program/Year-Level fee structures.)
# ============================================================

@permission_required("school.view_semester", raise_exception=True)
def semester_list(request):
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from .utils.time_utils import get_current_date

    today = get_current_date()
    all_semesters = Semester.objects.select_related('academic_year').order_by('-academic_year__name', 'number')

    # Partition by status
    active_sems = []
    upcoming_sems = []
    completed_sems = []

    for sem in all_semesters:
        status = sem.status  # uses frozen date via property
        if status == 'ACTIVE':
            active_sems.append(sem)
        elif status == 'UPCOMING':
            upcoming_sems.append(sem)
        else:
            completed_sems.append(sem)

    # Sort each group by start_date
    active_sems.sort(key=lambda s: s.start_date)
    upcoming_sems.sort(key=lambda s: s.start_date)
    completed_sems.sort(key=lambda s: s.start_date, reverse=True)  # most recent first

    # Paginate completed (3 per page)
    paginator = Paginator(completed_sems, 3)
    page = request.GET.get('completed_page', 1)
    try:
        completed_page_obj = paginator.page(page)
    except PageNotAnInteger:
        completed_page_obj = paginator.page(1)
    except EmptyPage:
        completed_page_obj = paginator.page(paginator.num_pages)

    context = {
        'active_semesters': active_sems,
        'upcoming_semesters': upcoming_sems,
        'completed_page_obj': completed_page_obj,
        'today': today,
    }
    return render(request, 'school/semester_list.html', context)


@permission_required("school.add_semester", raise_exception=True)
def semester_create(request):
    form = SemesterForm(request.POST or None)

    if form.is_valid():
        semester = form.save()
        messages.success(
            request,
            "Semester created. Now configure fee structures for it.",
        )
        return redirect("fee_structure_list", semester_id=semester.pk)

    return render(
        request,
        "school/semester_form.html",
        {
            "form": form,
            "title": "Create Semester",
            "back_url": "semester_list",
        },
    )


@permission_required("school.change_semester", raise_exception=True)
def semester_edit(request, pk):
    semester = get_object_or_404(Semester, pk=pk)
    form = SemesterForm(request.POST or None, instance=semester)

    if form.is_valid():
        form.save()
        messages.success(request, "Semester updated successfully.")
        return redirect("semester_list")

    return render(
        request,
        "school/semester_form.html",
        {
            "form": form,
            "title": f"Edit {semester}",
            "submit_label": "Update Semester",
            "back_url": "semester_list",
        },
    )


# ============================================================
# PROGRAMS (replaces Course)
# ============================================================

@permission_required("school.view_program", raise_exception=True)
def program_list(request):
    programs = Program.objects.all().order_by("name")
    paginator = Paginator(programs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "school/program_list.html", {"page_obj": page_obj})


@permission_required("school.add_program", raise_exception=True)
def program_create(request):
    form = ProgramForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request, "Program created successfully.")
        return redirect("program_list")

    return render(
        request,
        "school/program_create.html",
        {
            "form": form,
        },
    )


# ============================================================
# FEE STRUCTURES
# One FeeStructure = Program + Year Level + Semester.
# Must be set up before students can be charged for that
# program/year-level in that semester.
# ============================================================

@permission_required("school.view_feestructure", raise_exception=True)
def fee_structure_list(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)

    program_filter = request.GET.get("program", "")
    year_level_filter = request.GET.get("year_level", "")

    programs = Program.objects.filter(active=True)

    if program_filter:
        programs = programs.filter(pk=program_filter)

    existing = {
        (fs.program_id, fs.year_level): fs
        for fs in FeeStructure.objects.filter(semester=semester).prefetch_related("items")
    }

    max_year_level = 6
    if programs.exists():
        max_year_level = max(p.duration_years for p in programs)

    # Build year_level_choices for template (1 to max_year_level)
    year_level_choices = range(1, max_year_level + 1)

    rows = []
    for program in programs:
        year_levels = range(1, program.duration_years + 1)
        if year_level_filter and year_level_filter.isdigit():
            year_levels = [int(year_level_filter)]
        for year_level in year_levels:
            fs = existing.get((program.id, year_level))
            rows.append(
                {
                    "program": program,
                    "year_level": year_level,
                    "fee_structure": fs,
                    "total": (
                        sum((item.amount for item in fs.items.all()), Decimal("0"))
                        if fs
                        else None
                    ),
                }
            )

    # Paginate rows
    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    all_programs = Program.objects.filter(active=True)

    selected_program = None
    if program_filter:
        selected_program = all_programs.filter(pk=program_filter).first()

    return render(
        request,
        "school/fee_structure_list.html",
        {
            "semester": semester,
            "page_obj": page_obj,
            "program_filter": program_filter,
            "year_level_filter": year_level_filter,
            "all_programs": all_programs,
            "max_year_level": max_year_level,
            "year_level_choices": year_level_choices,
            "selected_program": selected_program,
        },
    )


@transaction.atomic
@permission_required("school.add_feestructure", raise_exception=True)
def fee_structure_create(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)
    fee_structure = FeeStructure(semester=semester)

    filter_program = request.GET.get("filter_program", request.GET.get("program", ""))
    filter_year_level = request.GET.get("filter_year_level", request.GET.get("year_level", ""))

    if request.method == "POST":
        form = FeeStructureForm(request.POST, instance=fee_structure)
        formset = FeeStructureItemFormSet(request.POST, instance=fee_structure)

        if form.is_valid():
            fee_structure = form.save(commit=False)
            fee_structure.semester = semester
            formset = FeeStructureItemFormSet(request.POST, instance=fee_structure)

            if formset.is_valid():
                fee_structure.save()
                formset.instance = fee_structure
                formset.save()
                messages.success(request, "Fee structure saved successfully.")
                redirect_url = reverse("fee_structure_list", args=[semester.pk])
                params = []
                if filter_program:
                    params.append(f"program={filter_program}")
                if filter_year_level:
                    params.append(f"year_level={filter_year_level}")
                if params:
                    redirect_url += "?" + "&".join(params)
                return redirect(redirect_url)
    else:
        initial = {}
        if request.GET.get("program"):
            initial["program"] = request.GET.get("program")
        if request.GET.get("year_level"):
            initial["year_level"] = request.GET.get("year_level")

        form = FeeStructureForm(instance=fee_structure, initial=initial)
        formset = FeeStructureItemFormSet(instance=fee_structure)

    return render(
        request,
        "school/fee_structure_form.html",
        {
            "form": form,
            "formset": formset,
            "semester": semester,
            "title": f"Configure Fees — {semester}",
            "back_url_name": "fee_structure_list",
            "back_semester_id": semester.pk,
            "filter_program": filter_program,
            "filter_year_level": filter_year_level,
        },
    )


@transaction.atomic
@permission_required("school.change_feestructure", raise_exception=True)
def fee_structure_edit(request, pk):
    fee_structure = get_object_or_404(FeeStructure, pk=pk)
    semester = fee_structure.semester

    filter_program = request.GET.get("program", "")
    filter_year_level = request.GET.get("year_level", "")

    if request.method == "POST":
        form = FeeStructureForm(request.POST, instance=fee_structure)
        formset = FeeStructureItemFormSet(request.POST, instance=fee_structure)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Fee structure updated successfully.")
            redirect_url = reverse("fee_structure_list", args=[semester.pk])
            params = []
            if filter_program:
                params.append(f"program={filter_program}")
            if filter_year_level:
                params.append(f"year_level={filter_year_level}")
            if params:
                redirect_url += "?" + "&".join(params)
            return redirect(redirect_url)
    else:
        form = FeeStructureForm(instance=fee_structure)
        formset = FeeStructureItemFormSet(instance=fee_structure)

    return render(
        request,
        "school/fee_structure_form.html",
        {
            "form": form,
            "formset": formset,
            "semester": semester,
            "title": f"Edit Fees — {fee_structure.program} Year {fee_structure.year_level}",
            "submit_label": "Update Fees",
            "back_url_name": "fee_structure_list",
            "back_semester_id": semester.pk,
            "filter_program": filter_program,
            "filter_year_level": filter_year_level,
        },
    )


# ============================================================
# BULK FEE CONFIGURATION
# ============================================================

@transaction.atomic
@permission_required("school.add_feestructure", raise_exception=True)
def bulk_fee_configuration(request, semester_id):
    """
    Bulk configure fee structures for multiple programs and year levels simultaneously.
    Creates or updates FeeStructure and FeeStructureItem entries.
    """
    semester = get_object_or_404(Semester, pk=semester_id)

    if request.method == "POST":
        form = BulkFeeForm(request.POST)
        if form.is_valid():
            programs = form.cleaned_data["programs"]
            year_levels = [int(yl) for yl in form.cleaned_data["year_levels"]]
            fee_name = form.cleaned_data["fee_name"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data["description"]

            created_count = 0
            updated_count = 0
            skipped_count = 0

            for program in programs:
                for year_level in year_levels:
                    # Skip year levels that exceed program duration
                    if year_level > program.duration_years:
                        skipped_count += 1
                        continue

                    # Get or create FeeStructure
                    fee_structure, fs_created = FeeStructure.objects.get_or_create(
                        program=program,
                        year_level=year_level,
                        semester=semester,
                    )

                    # Get or create FeeStructureItem
                    fee_item, item_created = FeeStructureItem.objects.get_or_create(
                        fee_structure=fee_structure,
                        name=fee_name,
                        defaults={
                            "amount": amount,
                            "description": description,
                        },
                    )

                    if item_created:
                        created_count += 1
                    else:
                        # Update existing item's amount and description
                        fee_item.amount = amount
                        fee_item.description = description
                        fee_item.save(update_fields=["amount", "description"])
                        updated_count += 1

            # Build success message
            message_parts = []
            if created_count:
                message_parts.append(f"{created_count} fee item(s) created")
            if updated_count:
                message_parts.append(f"{updated_count} fee item(s) updated")
            if skipped_count:
                message_parts.append(f"{skipped_count} combination(s) skipped (year level exceeds program duration)")

            if message_parts:
                messages.success(request, "Bulk fee configuration completed: " + "; ".join(message_parts) + ".")
            else:
                messages.warning(request, "No fee items were configured. Please check your selections.")

            return redirect("fee_structure_list", semester_id=semester.pk)
    else:
        form = BulkFeeForm()

    return render(
        request,
        "school/bulk_fee_form.html",
        {
            "form": form,
            "semester": semester,
            "title": f"Bulk Fee Configuration — {semester}",
            "back_url_name": "fee_structure_list",
            "back_semester_id": semester.pk,
        },
    )


# ============================================================
# STUDENTS
# ============================================================

@permission_required("school.view_student", raise_exception=True)
def student_list(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    program_filter = request.GET.get("program", "")
    year_level_filter = request.GET.get("year_level", "")
    current_semester_only = request.GET.get("current_semester", "")

    today = get_current_date()

    students = Student.objects.all()
    total_students = Student.objects.count()
    if query:
        students = students.filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    if program_filter:
        students = students.filter(program_id=program_filter)

    # --- Status filter logic ---
    if status_filter == "all":
        # No status filter - show all
        pass
    elif status_filter:
        # Filter by specific status
        students = students.filter(status=status_filter.upper())
    else:
        # Default: show only Active and Deferred
        students = students.filter(status__in=[Student.ACTIVE, Student.DEFERRED])

    # Filter by year level of active enrollment (current or upcoming)
    if year_level_filter:
        students = students.filter(
            enrollments__status=Enrollment.ACTIVE,
            enrollments__semester__end_date__gte=today,
            enrollments__year_level=year_level_filter
        ).distinct()

    if current_semester_only:
        current_sem = Semester.objects.filter(
            start_date__lte=today, end_date__gte=today
        ).first()
        if current_sem:
            students = students.filter(enrollments__semester=current_sem)

    # Program counts for filter pills
    program_counts = Student.objects.values("program__id", "program__name").annotate(
        count=Count("id")
    ).order_by("program__name")

    # Get status counts
    status_counts = Student.objects.values("status").annotate(
        count=Count("id")
    ).order_by("status")

    # Max year level for dropdown (based on program durations)
    max_year_level = Program.objects.aggregate(max_duration=Max("duration_years"))["max_duration"] or 6

    students = students.select_related("program", "intake_year").prefetch_related(
        "enrollments__semester"
    )
    filtered_count = students.count()
    paginator = Paginator(students, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "school/student_list.html",
        {
            "total_students": total_students,
            "filtered_count": filtered_count,
            "page_obj": page_obj,
            "query": query,
            "status_filter": status_filter,
            "program_filter": program_filter,
            "year_level_filter": year_level_filter,
            "current_semester_only": current_semester_only,
            "status_choices": Student.STATUS_CHOICES,
            "program_counts": program_counts,
            "status_counts": {s["status"]: s["count"] for s in status_counts},
            "max_year_level": max_year_level,
            "today": today,
        },
    )


@transaction.atomic
@permission_required("school.add_student", raise_exception=True)
def student_create(request):
    student_form = StudentForm(request.POST or None)

    today = get_current_date()
    # Offer the current semester AND any upcoming ones — registration
    # routinely happens before a semester starts, not just during it.
    semesters = Semester.objects.filter(
        end_date__gte=today
    ).select_related("academic_year").order_by("start_date")

    year_level_choices = range(1, 7)  # widest possible; template caps by program JS-side

    if request.method == "POST":
        semester_id = request.POST.get("semester")
        year_level = request.POST.get("year_level")

        if student_form.is_valid():
            if not semester_id:
                messages.error(request, "Please select a starting semester.")
            elif not year_level:
                messages.error(request, "Please select a starting year level.")
            else:
                try:
                    semester = Semester.objects.get(pk=semester_id)
                    year_level = int(year_level)
                except (Semester.DoesNotExist, ValueError):
                    messages.error(request, "Selected semester or year level is invalid.")
                    return render(
                        request,
                        "school/student_register.html",
                        {
                            "form": student_form,
                            "semesters": semesters,
                            "year_level_choices": year_level_choices,
                        },
                    )

                try:
                    enrollment = Enrollment(
                        student=None,  # set after student is saved, below
                        program=student_form.instance.program,
                        semester=semester,
                        year_level=year_level,
                        status=Enrollment.ACTIVE,
                    )
                    # Validate year_level against the chosen program's
                    # duration before we commit the student, so a bad
                    # selection doesn't leave an orphaned Student record.
                    if year_level > student_form.instance.program.duration_years:
                        raise ValidationError(
                            f"{student_form.instance.program} only runs for "
                            f"{student_form.instance.program.duration_years} year(s)."
                        )
                except ValidationError as e:
                    messages.error(request, " ".join(e.messages) if hasattr(e, "messages") else str(e))
                    return render(
                        request,
                        "school/student_register.html",
                        {
                            "form": student_form,
                            "semesters": semesters,
                            "year_level_choices": year_level_choices,
                        },
                    )

                student = student_form.save()
                enrollment.student = student
                enrollment.save()

                # Create enrollments and charges for all semesters in the academic year
                create_academic_year_enrollments(
                    student=student,
                    start_semester=semester,
                    start_year_level=year_level
                )

                StudentStatusLog.objects.create(
                    student=student,
                    status=Student.ACTIVE,
                    note="Initial registration.",
                )

                # Audit log
                from school.utils.audit import log_action
                log_action(
                    user=request.user,
                    action='REGISTER',
                    student=student,
                    summary=f"Registered student {student.first_name} {student.last_name}",
                    details={
                        'student_number': student.student_number,
                        'program': student.program.name,
                        'intake_year': student.intake_year.name,
                        'year_level': year_level,
                    },
                    category='STUDENT'
                )

                messages.success(request, "Student registered and enrolled successfully.")
                return redirect("student_detail", pk=student.pk)
        else:
            messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "school/student_register.html",
        {
            "form": student_form,
            "semesters": semesters,
            "year_level_choices": year_level_choices,
        },
    )


@permission_required("school.view_student", raise_exception=True)
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    today = get_current_date()
    
    # Current enrollment and year level
    current_enrollment = student.get_current_enrollment(today)
    current_year_level = current_enrollment.year_level if current_enrollment else None

    semesters = Semester.objects.select_related("academic_year")

    balances = []
    for semester in semesters:
        charged = (
            StudentCharge.objects.filter(
                student=student,
                fee_item__fee_structure__semester=semester,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        paid = (
            Payment.objects.filter(
                student=student,
                semester=semester,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

        if charged == 0 and paid == 0:
            continue  # skip semesters this student has no relationship to

        balances.append(
            {
                "semester": semester,
                "charged": charged,
                "paid": paid,
                "balance": charged - paid,
            }
        )

    payments = student.payments.select_related("semester")

    # Current academic year semester balances (with projection for unconfigured semesters)
    today = get_current_date()
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).first()
    semester_balances = []
    total_year_balance = Decimal("0")
    
    if current_year:
        enrollments = student.enrollments.filter(
            semester__academic_year=current_year, 
            status__in=[Enrollment.ACTIVE, Enrollment.COMPLETED]
        ).select_related("semester", "program").order_by("semester__number")
        
        for enrollment in enrollments:
            semester = enrollment.semester
            
            # Actual charges (from StudentCharge)
            charged = student.charges.filter(
                enrollment__semester=semester
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            
            paid = student.payments.filter(semester=semester).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0")
            
            # Projected charges (from FeeStructure) if no charges exist
            projected_charged = Decimal("0")
            if charged == 0:
                fee_structure = FeeStructure.objects.filter(
                    program=enrollment.program,
                    year_level=enrollment.year_level,
                    semester=semester
                ).prefetch_related("items").first()
                if fee_structure:
                    projected_charged = sum(
                        (item.amount for item in fee_structure.items.all()), 
                        Decimal("0")
                    )
            
            # Use projected if no actual charges
            effective_charged = charged if charged > 0 else projected_charged
            effective_balance = effective_charged - paid
            
            semester_balances.append({
                "semester": semester,
                "charged": charged,
                "projected_charged": projected_charged,
                "paid": paid,
                "balance": effective_balance,
                "is_projected": charged == 0 and projected_charged > 0,
            })
            total_year_balance += effective_balance

    return render(
        request,
        "school/student_detail.html",
        {
            "student": student,
            "balances": balances,
            "payments": payments,
            "semester_balances": semester_balances,
            "total_year_balance": total_year_balance,
            "current_year": current_year,
            "current_enrollment": current_enrollment,
            "current_year_level": current_year_level,
        },
    )


def cancel_unpaid_future_charges(student, user=None, today=None):
    """
    Deletes all StudentCharge records for a withdrawn student
    if the associated semester has not yet ended.
    """
    today = today or get_current_date()

    # Get all enrollments for semesters that are NOT ended (end_date >= today)
    active_enrollments = student.enrollments.filter(
        semester__end_date__gte=today,
        status=Enrollment.ACTIVE  # only active enrollments (not already completed)
    )

    # Delete all charges linked to these enrollments
    deleted_count, _ = StudentCharge.objects.filter(enrollment__in=active_enrollments).delete()

    if deleted_count > 0:
        # Log the adjustment
        from school.utils.audit import log_action
        log_action(
            user=user,
            action='WITHDRAWAL',
            student=student,
            summary=f"Cleared {deleted_count} future charges for withdrawn student",
            details={
                'semesters_affected': [e.semester_id for e in active_enrollments],
                'charges_removed': deleted_count,
            },
            category='FINANCIAL'
        )


@permission_required("school.change_student", raise_exception=True)
def student_status_change(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = StudentStatusChangeForm(request.POST or None, initial={"status": student.status})

    if form.is_valid():
        old_status = student.status
        new_status = form.cleaned_data["status"]
        student.status = new_status
        student.save(update_fields=["status"])

        # Handle withdrawal financials - remove unpaid charges for future/current semesters
        if new_status == Student.WITHDRAWN:
            cancel_unpaid_future_charges(student, user=request.user)

        StudentStatusLog.objects.create(
            student=student,
            status=student.status,
            note=form.cleaned_data["note"],
        )

        # Audit log for status change
        from school.utils.audit import log_action
        log_action(
            user=request.user,
            action='STATUS_CHANGE',
            student=student,
            summary=f"Status changed from {dict(Student.STATUS_CHOICES).get(old_status)} to {dict(Student.STATUS_CHOICES).get(new_status)}",
            details={
                'old_status': old_status,
                'new_status': new_status,
                'note': form.cleaned_data["note"],
            },
            category='STUDENT'
        )

        messages.success(request, f"Status updated to {student.get_status_display()}.")
        return redirect("student_detail", pk=student.pk)

    return render(
        request,
        "school/student_status_form.html",
        {
            "form": form,
            "student": student,
        },
    )


# ============================================================
# STUDENT ARCHIVE
# ============================================================

@permission_required("school.view_student", raise_exception=True)
def archive_list(request):
    """Searchable list of all students (all statuses) for archive access."""
    query = request.GET.get("q", "").strip()
    students = Student.objects.select_related("program", "intake_year")

    if query:
        students = students.filter(
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )

    students = students.order_by("last_name", "first_name")

    # Paginate 10 per page
    paginator = Paginator(students, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "school/student_archive_list.html", {
        "page_obj": page_obj,
        "query": query,
        "total": students.count(),
    })


@permission_required("school.view_student", raise_exception=True)
def archive_search(request):
    """Live search for student archive - returns JSON."""
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"students": []})

    students = Student.objects.filter(
        Q(student_number__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).order_by("last_name", "first_name")[:10]

    data = []
    for student in students:
        data.append({
            "id": student.id,
            "student_number": student.student_number,
            "name": f"{student.first_name} {student.last_name}",
            "program": student.program.name,
            "status": student.get_status_display(),
        })

    return JsonResponse({"students": data})


@permission_required("school.view_student", raise_exception=True)
def archive_detail(request, pk):
    """Read-only detail of a student's complete record."""
    student = get_object_or_404(Student.objects.select_related("program", "intake_year"), pk=pk)

    # --- Academic timeline ---
    enrollments = student.enrollments.select_related(
        "semester", "semester__academic_year", "program"
    ).order_by("semester__academic_year__name", "semester__number")

    # Years attended (distinct academic years)
    years_attended = sorted(set(e.semester.academic_year.name for e in enrollments))

    # Join year
    join_year = student.intake_year.name

    # Completion / expected completion
    completion_year = None
    expected_completion_year = None
    if student.status == Student.COMPLETED:
        last_enrollment = enrollments.last()
        if last_enrollment:
            completion_year = last_enrollment.semester.academic_year.name
    else:
        try:
            start_year = int(student.intake_year.name)
            expected_completion_year = str(start_year + student.program.duration_years - 1)
        except ValueError:
            expected_completion_year = "—"

    # --- Financial summary (all time) ---
    total_charged = student.charges.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_paid = student.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    balance = total_charged - total_paid

    # --- Semester-by-semester breakdown for display ---
    semester_breakdown = []
    for enrollment in enrollments:
        sem = enrollment.semester
        charged = student.charges.filter(enrollment=enrollment).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")
        paid = student.payments.filter(semester=sem).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")
        semester_breakdown.append({
            "semester": sem,
            "year_level": enrollment.year_level,
            "enrollment_status": enrollment.get_status_display(),
            "charged": charged,
            "paid": paid,
            "balance": charged - paid,
        })

    context = {
        "student": student,
        "enrollments": enrollments,
        "years_attended": years_attended,
        "join_year": join_year,
        "completion_year": completion_year,
        "expected_completion_year": expected_completion_year,
        "total_charged": total_charged,
        "total_paid": total_paid,
        "balance": balance,
        "semester_breakdown": semester_breakdown,
    }
    return render(request, "school/student_archive_detail.html", context)


# ============================================================
# PAYMENTS
# ============================================================

@transaction.atomic
@permission_required("school.can_record_payments", raise_exception=True)
def payment_create(request):
    student_id = request.GET.get("student") or request.POST.get("student_id")
    selected_semester_id = request.GET.get("semester") or request.POST.get("semester")

    student = None
    enrollments = []
    selected_enrollment = None
    today = get_current_date()

    if student_id:
        student = get_object_or_404(Student, pk=student_id, status=Student.ACTIVE)

        # Get all enrollments with financial data (charges, payments, or fee structure)
        enrollments_qs = student.enrollments.select_related(
            "program", "semester", "semester__academic_year"
        ).order_by("-semester__academic_year__name", "-semester__number")

        # Filter to enrollments that have charges, payments, OR a fee structure configured
        for e in enrollments_qs:
            has_charges = StudentCharge.objects.filter(enrollment=e).exists()
            has_payments = Payment.objects.filter(student=student, semester=e.semester).exists()
            has_fee_structure = FeeStructure.objects.filter(
                program=e.program,
                year_level=e.year_level,
                semester=e.semester
            ).exists()
            if has_charges or has_payments or has_fee_structure:
                enrollments.append(e)

        # Determine default semester using the new get_current_enrollment method
        default_enrollment = student.get_current_enrollment(today)
        
        # Ensure the default enrollment is in our filtered list (has financial data)
        if default_enrollment and default_enrollment not in enrollments:
            default_enrollment = None
        
        # Fallback: first enrollment from filtered list
        if not default_enrollment and enrollments:
            default_enrollment = enrollments[0]

        # Use selected semester if provided, otherwise default
        if selected_semester_id:
            try:
                selected_enrollment = next(
                    e for e in enrollments if str(e.semester.pk) == selected_semester_id
                )
            except StopIteration:
                selected_enrollment = default_enrollment
        else:
            selected_enrollment = default_enrollment

    form = PaymentForm(
        request.POST or None,
        semester_queryset=Semester.objects.filter(
            pk__in=[e.semester.pk for e in enrollments]
        ) if enrollments else Semester.objects.none(),
    )

    if request.method == "POST":
        if not student:
            messages.error(request, "Please select a student first.")
        elif not selected_enrollment:
            messages.error(request, "Please select a semester to record payment for.")
        elif form.is_valid():
            payment = form.save(commit=False)
            payment.student = student
            payment.semester = form.cleaned_data["semester"]
            payment.save()

            # Audit log
            from school.utils.audit import log_action
            log_action(
                user=request.user,
                action='PAYMENT',
                student=student,
                summary=f"Payment of {payment.amount} recorded for {payment.semester}",
                details={
                    'receipt': payment.receipt_number,
                    'amount': str(payment.amount),
                    'semester': str(payment.semester),
                    'method': payment.get_method_display(),
                    'reference': payment.reference,
                },
                category='FINANCIAL'
            )

            messages.success(request, "Payment recorded successfully.")
            return redirect(f"{reverse('payment_create')}?student={student.pk}&semester={payment.semester.pk}")

    charged = paid = balance = 0
    if selected_enrollment:
        charged = (
            student.charges.filter(
                fee_item__fee_structure__semester=selected_enrollment.semester
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        paid = (
            student.payments.filter(semester=selected_enrollment.semester).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        balance = charged - paid

    # Build enrollment data for template
    enrollment_data = []
    for e in enrollments:
        e_charged = (
            student.charges.filter(
                fee_item__fee_structure__semester=e.semester
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        e_paid = (
            student.payments.filter(semester=e.semester).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        e_balance = e_charged - e_paid
        enrollment_data.append({
            "enrollment": e,
            "charged": e_charged,
            "paid": e_paid,
            "balance": e_balance,
            "is_selected": selected_enrollment and e.semester.pk == selected_enrollment.semester.pk,
            "is_current": e.status == Enrollment.ACTIVE and e.semester.end_date >= today,
        })

    return render(
        request,
        "school/payment_create.html",
        {
            "form": form,
            "student": student,
            "enrollment": selected_enrollment,
            "enrollment_data": enrollment_data,
            "charged": charged,
            "paid": paid,
            "balance": balance,
        },
    )

@transaction.atomic
@require_POST
def bulk_progress_students(request, semester_id):
    """
    Progresses all active students from a source semester into the next upcoming semester.
    """
    source_semester = get_object_or_404(Semester, pk=semester_id)
    
    # Find the next chronological semester
    target_semester = (
        Semester.objects.filter(start_date__gt=source_semester.start_date)
        .order_by("start_date")
        .first()
    )

    if not target_semester:
        messages.error(request, "No upcoming semester found to progress students into.")
        return redirect("semester_list")

    # Get active enrollments from the source semester
    active_enrollments = Enrollment.objects.filter(
        semester=source_semester,
        status=Enrollment.ACTIVE,
        student__status=Student.ACTIVE,
    ).select_related("student", "program")

    enrolled_count = 0
    completed_count = 0

    for current in active_enrollments:
        student = current.student
        program = current.program

        # Calculate next year level
        if source_semester.number == 1:
            next_year_level = current.year_level
        else:
            next_year_level = current.year_level + 1

        # Check if student completed the program
        if next_year_level > program.duration_years:
            student.status = Student.COMPLETED
            student.save(update_fields=["status"])
            
            StudentStatusLog.objects.create(
                student=student,
                status=Student.COMPLETED,
                note=f"Completed {program.name} after {source_semester}.",
            )
            completed_count += 1
            continue

        # Create new Enrollment
        enrollment, created = Enrollment.objects.get_or_create(
            student=student,
            semester=target_semester,
            defaults={
                "program": program,
                "year_level": next_year_level,
                "status": Enrollment.ACTIVE,
            },
        )

        if created:
            enrolled_count += 1

            # Mark the old enrollment as completed
            current.status = Enrollment.COMPLETED
            current.save(update_fields=["status"])

            # Create enrollments and charges for all semesters in the target academic year
            create_academic_year_enrollments(
                student=student,
                start_semester=target_semester,
                start_year_level=next_year_level
            )

    messages.success(
        request,
        f"Progressed {enrolled_count} students to {target_semester}. "
        f"{completed_count} students marked as completed/graduated."
    )
    return redirect("semester_list")


@user_passes_test(lambda u: u.is_superuser)
def time_override_view(request):
    """
    View to set or clear the time override for testing.
    Only accessible when ENABLE_TIME_OVERRIDE is True.
    """
    from django.conf import settings
    
    if not getattr(settings, 'ENABLE_TIME_OVERRIDE', False):
        return redirect('dashboard')
    
    from school.models import TimeOverride
    from django.contrib import messages
    from django.utils import timezone
    from datetime import datetime
    
    frozen = TimeOverride.get_frozen_time()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'set':
            dt_str = request.POST.get('frozen_datetime')
            if dt_str:
                try:
                    dt = datetime.fromisoformat(dt_str)
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    TimeOverride.set_frozen_time(dt)
                    messages.success(request, f"Time frozen to {dt}")
                except ValueError:
                    messages.error(request, "Invalid date/time format.")
            else:
                messages.error(request, "Please select a date/time.")
        elif action == 'clear':
            TimeOverride.set_frozen_time(None)
            messages.success(request, "Time override cleared. Using real time.")
        return redirect('time_override')
    
    context = {
        'frozen': frozen,
        'frozen_iso': frozen.isoformat(timespec='minutes') if frozen else '',
    }
    return render(request, 'school/time_override.html', context)


# ============================================================
# USER MANAGEMENT (Admin only)
# ============================================================

@user_passes_test(lambda u: u.is_superuser)
def user_list(request):
    """List all users with their roles/groups."""
    from django.contrib.auth.models import User, Group
    
    users = User.objects.all().prefetch_related('groups').order_by('-is_superuser', 'username')
    
    context = {
        "users": users,
    }
    return render(request, "school/user_list.html", context)


@user_passes_test(lambda u: u.is_superuser)
def user_create(request):
    """Create a new user and assign to a group."""
    from django.contrib.auth.models import User, Group
    from django import forms
    
    class UserCreateForm(forms.Form):
        username = forms.CharField(max_length=150)
        password = forms.CharField(widget=forms.PasswordInput, help_text="Temporary password - user should change on first login")
        group = forms.ModelChoiceField(queryset=Group.objects.all(), required=False, help_text="Assign to a role group")
        is_staff = forms.BooleanField(required=False, help_text="Can access Django admin")
    
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                is_staff=form.cleaned_data["is_staff"],
            )
            group = form.cleaned_data["group"]
            if group:
                user.groups.add(group)
            messages.success(request, f"User '{user.username}' created successfully.")
            return redirect("user_list")
    else:
        form = UserCreateForm()
    
    context = {
        "form": form,
    }
    return render(request, "school/user_form.html", context)


# ============================================================
# AUDIT LOG
# ============================================================

@permission_required("school.view_auditlog", raise_exception=True)
def audit_log_list(request):
    """Audit trail list view with pagination."""
    from school.models import AuditLog
    
    logs = AuditLog.objects.select_related("user", "student").all()
    
    paginator = Paginator(logs, 7)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    context = {
        "page_obj": page_obj,
    }
    return render(request, "school/audit_log_list.html", context)