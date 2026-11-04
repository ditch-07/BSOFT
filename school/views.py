from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum, Count, Max, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST
from django.conf import settings

from .utils.receipts import next_receipt_number
from .utils.time_utils import get_current_datetime, get_current_date, get_working_semester

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
    StudentImportForm,
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
    current_enrollment,
    student_balance,
    semester_financials,
    unconfigured_fee_structures,
    outstanding_students,
    payment_methods_breakdown,
    program_revenue,
    daily_collections,
    enrollment_summary,
    student_status_history,
    students_with_missing_details,
    BackupConfig,
)

from school.reports import REPORTS
from school.reporting.registry import REPORTS as REPORT_SPECS, permitted_reports
from school.reporting.views import render_report
from school.utils.backups import (
    BackupError,
    create_backup,
    restore_backup,
    timestamped_name,
    verify_backup,
)

import os
from datetime import datetime

def create_charges_for_fee_structure(fee_structure):
    """
    Create missing StudentCharge records for all students who are
    enrolled in the fee structure's program/year-level/semester.

    Safe to run multiple times because get_or_create() prevents
    duplicate charges.
    """
    enrollments = (
        Enrollment.objects.filter(
            program=fee_structure.program,
            year_level=fee_structure.year_level,
            semester=fee_structure.semester,
            student__status=Student.ACTIVE,
        )
        .select_related("student")
    )

    charges_created = 0

    for enrollment in enrollments:
        for item in fee_structure.items.all():
            _, created = StudentCharge.objects.get_or_create(
                student=enrollment.student,
                enrollment=enrollment,
                fee_item=item,
                defaults={
                    "amount": item.amount,
                },
            )

            if created:
                charges_created += 1

    return charges_created


# ============================================================
# FEE SET-UP HELPERS
# ============================================================

def _active_programs():
    return list(Program.objects.filter(active=True).order_by("name"))


def enrolled_counts(semester):
    """Active students per (trade, course year) in a semester, batched."""
    rows = (
        Enrollment.objects.filter(
            semester=semester,
            student__status=Student.ACTIVE,
        )
        .values("program_id", "year_level")
        .annotate(count=Count("student_id", distinct=True))
    )
    return {(row["program_id"], row["year_level"]): row["count"] for row in rows}


def fee_progress(semester):
    """Return the trade x course-year grid plus set-up counts.

    A cell counts as set up only when its structure has at least one fee
    item. Queries stay constant regardless of how many trades exist.
    """
    programs = _active_programs()
    max_year = max((program.duration_years for program in programs), default=0)

    structures = (
        FeeStructure.objects.filter(semester=semester)
        .annotate(
            item_count=Count("items", distinct=True),
            total=Coalesce(Sum("items__amount"), Value(Decimal("0"))),
        )
    )
    structure_map = {
        (structure.program_id, structure.year_level): structure
        for structure in structures
    }
    counts = enrolled_counts(semester)

    cells = []
    rows = []
    for program in programs:
        row_cells = []
        for year_level in range(1, max_year + 1):
            if year_level > program.duration_years:
                row_cells.append({"year_level": year_level, "applicable": False})
                continue

            structure = structure_map.get((program.id, year_level))
            set_up = bool(structure and structure.item_count)
            cell = {
                "program": program,
                "year_level": year_level,
                "applicable": True,
                "fee_structure": structure,
                "set_up": set_up,
                "fee_count": structure.item_count if structure else 0,
                "total": structure.total if structure else Decimal("0"),
                "students": counts.get((program.id, year_level), 0),
            }
            row_cells.append(cell)
            cells.append(cell)
        rows.append({
            "program": program,
            "cells": row_cells,
            "has_needs": any(
                not cell["set_up"] for cell in row_cells if cell["applicable"]
            ),
            "has_set_up": any(
                cell["set_up"] for cell in row_cells if cell["applicable"]
            ),
        })

    set_up_count = sum(1 for cell in cells if cell["set_up"])
    waiting = sum(
        cell["students"] for cell in cells
        if not cell["set_up"] and cell["students"]
    )
    return {
        "programs": programs,
        "max_year": max_year,
        "rows": rows,
        "cells": cells,
        "set_up": set_up_count,
        "total": len(cells),
        "needs": len(cells) - set_up_count,
        "waiting": waiting,
    }


def next_fee_cell(semester, exclude_structure_pk=None):
    """First cell that still needs fees, optionally ignoring one structure."""
    for cell in fee_progress(semester)["cells"]:
        if cell["set_up"]:
            continue
        structure = cell["fee_structure"]
        if (
            exclude_structure_pk
            and structure
            and structure.pk == exclude_structure_pk
        ):
            continue
        return cell
    return None


def fee_progress_for_semesters(semesters):
    """Batched (set_up, total) progress for the semester list."""
    semesters = list(semesters)
    total = sum(program.duration_years for program in _active_programs())
    set_up = {semester.pk: 0 for semester in semesters}

    if semesters:
        rows = (
            FeeStructure.objects.filter(
                semester__in=semesters,
                program__active=True,
                items__isnull=False,
            )
            .values("semester_id")
            .annotate(count=Count("id", distinct=True))
        )
        for row in rows:
            set_up[row["semester_id"]] = min(row["count"], total)

    return {
        semester.pk: {
            "set_up": set_up[semester.pk],
            "total": total,
            "complete": total > 0 and set_up[semester.pk] >= total,
        }
        for semester in semesters
    }


@transaction.atomic
def copy_fee_structures(source, target):
    """Copy set-up fee structures into empty target cells.

    Never overwrites an existing set-up cell, skips inactive trades and
    years beyond a trade's duration, and charges already-enrolled students.
    """
    programs = {program.pk: program for program in _active_programs()}
    source_structures = (
        FeeStructure.objects.filter(semester=source, items__isnull=False)
        .select_related("program")
        .prefetch_related("items")
    )
    target_set_up = set(
        FeeStructure.objects.filter(semester=target, items__isnull=False)
        .values_list("program_id", "year_level")
    )

    copied = 0
    skipped = 0
    charges_created = 0

    for structure in source_structures:
        program = programs.get(structure.program_id)
        if not program or structure.year_level > program.duration_years:
            skipped += 1
            continue

        key = (structure.program_id, structure.year_level)
        if key in target_set_up:
            skipped += 1
            continue

        new_structure, _ = FeeStructure.objects.get_or_create(
            program_id=structure.program_id,
            year_level=structure.year_level,
            semester=target,
        )
        for item in structure.items.all():
            FeeStructureItem.objects.get_or_create(
                fee_structure=new_structure,
                name=item.name,
                defaults={
                    "amount": item.amount,
                    "description": item.description,
                },
            )

        charges_created += create_charges_for_fee_structure(new_structure)
        copied += 1

    return {
        "copied": copied,
        "skipped": skipped,
        "charges": charges_created,
    }


def _copy_sources(exclude_semester=None):
    """Semesters that already have at least one set-up fee structure."""
    queryset = (
        Semester.objects.filter(fee_structures__items__isnull=False)
        .select_related("academic_year")
        .distinct()
    )
    if exclude_semester:
        queryset = queryset.exclude(pk=exclude_semester.pk)
    return list(queryset.order_by("-start_date", "-number"))


def _grid_url(semester, program_id=None, year_level=None):
    url = reverse("fee_structure_list", args=[semester.pk])
    params = []
    if program_id:
        params.append(f"program={program_id}")
    if year_level:
        params.append(f"year={year_level}")
    if params:
        url += "?" + "&".join(params)
    if program_id and year_level:
        url += f"#fee-cell-{program_id}-{year_level}"
    return url


def _fee_locked(semester):
    return semester.status == "COMPLETED"


def _semester_label(semester):
    return f"{semester.academic_year.name} · Semester {semester.number}"


def _copy_message(source, result):
    copied = result["copied"]
    parts = [
        f"Copied {copied} set{'s' if copied != 1 else ''} of fees "
        f"from {_semester_label(source)}."
    ]
    if result["charges"]:
        charges = result["charges"]
        parts.append(f"{charges} student{'s' if charges != 1 else ''} charged.")
    if result["skipped"]:
        skipped = result["skipped"]
        parts.append(
            f"{skipped} already set up or not offered "
            f"{'were' if skipped != 1 else 'was'} left alone."
        )
    return " ".join(parts)


def _fee_item_queryset(fee_structure):
    return fee_structure.items.annotate(
        charged_count=Count("student_charges")
    )


def create_academic_year_enrollments(student, start_semester, start_year_level, program=None):
    """
    Create enrollments and charges for all semesters in the academic year
    of `start_semester` from that semester onward.
    """
    if program is None:
        program = student.program
    academic_year = start_semester.academic_year
    semesters = Semester.objects.filter(
        academic_year=academic_year,
        number__gte=start_semester.number
    ).order_by('number')

    enrollments_created = 0
    current_year_level = start_year_level

    for sem in semesters:
        # Cap year level at program duration
        if current_year_level > program.duration_years:
            break

        enrollment, created = Enrollment.objects.get_or_create(
            student=student,
            semester=sem,
            defaults={
                'program': program,
                'year_level': current_year_level,
                'status': Enrollment.ACTIVE,
            }
        )
        if created:
            enrollments_created += 1

        fee_structure = FeeStructure.objects.filter(
            program=program,
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
    from bisect import bisect_right
    from datetime import timedelta

    from django.db.models import OuterRef, Subquery

    from .utils.time_utils import get_working_semester

    today = get_current_date()
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
    ).first()
    financial_semester = get_working_semester(today)
    financial_semester_is_upcoming = bool(
        financial_semester and financial_semester.start_date > today
    )
    financial_year = (
        financial_semester.academic_year if financial_semester else current_year
    )
    show_financials = (
        request.user.has_perm("school.can_view_financial_reports")
        or request.user.has_perm("school.can_record_payments")
    )
    show_outstanding = request.user.has_perm("school.can_view_outstanding_reports")
    can_progress = request.user.has_perm("school.change_student")
    can_add_semester = request.user.has_perm("school.add_semester")
    can_add_fees = request.user.has_perm("school.add_feestructure")

    context = {
        "today": today,
        "yesterday": today - timedelta(days=1),
        "current_year": current_year,
        "financial_semester": financial_semester,
        "financial_semester_is_upcoming": financial_semester_is_upcoming,
        "financial_year": financial_year,
        "total_students": Student.objects.filter(status=Student.ACTIVE).count(),
        "show_financials": show_financials,
        "show_outstanding": show_outstanding,
        "semester_days_until": 0,
        "semester_week": 0,
        "semester_weeks": 0,
        "semester_percent": 0,
    }
    if financial_semester:
        duration = (financial_semester.end_date - financial_semester.start_date).days
        weeks = (duration + 7) // 7
        elapsed = (today - financial_semester.start_date).days
        context.update({
            "semester_days_until": max(0, -elapsed),
            "semester_week": min(weeks, elapsed // 7 + 1) if elapsed >= 0 else 0,
            "semester_weeks": weeks,
            "semester_percent": max(0, min(100, elapsed * 100 / max(1, duration))),
        })

    if show_financials:
        total_charged = total_paid = expected_revenue_year = Decimal("0")
        collection_rate = 0
        if financial_semester:
            fin = semester_financials(financial_semester)
            total_charged = fin["charged"]
            total_paid = fin["paid"]
            collection_rate = fin["collection_rate"]
            expected_revenue_year = StudentCharge.objects.filter(
                enrollment__semester__academic_year=financial_year,
                enrollment__status=Enrollment.ACTIVE,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        # Daily activity includes receipts for past semesters as well.
        today_payments = Payment.objects.filter(payment_date=today).aggregate(
            total=Sum("amount"), count=Count("pk")
        )
        context.update({
            "total_charged": total_charged,
            "total_paid": total_paid,
            "collection_rate": collection_rate,
            "collection_bar": max(0, min(100, collection_rate)),
            "expected_revenue_year": expected_revenue_year,
            "today_total": today_payments["total"] or Decimal("0"),
            "today_count": today_payments["count"],
            "recent_payments": Payment.objects.select_related(
                "student__program", "semester"
            ).order_by("-payment_date", "-id")[:8],
        })

    if show_outstanding:
        balances = []
        has_semester_charges = False
        if financial_semester:
            course_year = Enrollment.objects.filter(
                student_id=OuterRef("pk"),
                semester=financial_semester,
            ).order_by("pk").values("year_level")[:1]
            balances = list(
                outstanding_students(financial_semester)
                .select_related("program")
                .annotate(course_year=Subquery(course_year))
                .order_by("-balance", "pk")
            )
            # A positive balance already proves that charges exist.
            has_semester_charges = bool(balances) or StudentCharge.objects.filter(
                enrollment__semester=financial_semester,
            ).exists()
        top_outstanding = balances[:5]
        for student in top_outstanding:
            student.balance_percent = student.balance * 100 / balances[0].balance
        context.update({
            "outstanding": sum((student.balance for student in balances), Decimal("0")),
            "students_with_balance": len(balances),
            "top_outstanding": top_outstanding,
            "more_outstanding": max(0, len(balances) - len(top_outstanding)),
            "has_semester_charges": has_semester_charges,
        })

    next_steps = []
    semesters = None
    if can_progress or can_add_semester:
        active_counts = {
            row["semester_id"]: row["active_students"]
            for row in Enrollment.objects.filter(
                semester__end_date__lt=today,
                status=Enrollment.ACTIVE,
                student__status=Student.ACTIVE,
            ).order_by().values("semester_id").annotate(active_students=Count("pk"))
        }
        if active_counts:
            semesters = list(
                Semester.objects.select_related("academic_year").order_by("start_date", "pk")
            )
            start_dates = [semester.start_date for semester in semesters]
            # Equal start dates are not progression targets.
            for semester in sorted(semesters, key=lambda sem: (sem.end_date, sem.pk), reverse=True):
                active_students = active_counts.get(semester.pk)
                if not active_students:
                    continue
                next_index = bisect_right(start_dates, semester.start_date)
                next_semester = semesters[next_index] if next_index < len(semesters) else None
                if next_semester and can_progress:
                    next_steps.append({
                        "kind": "progress",
                        "semester": semester,
                        "next_semester": next_semester,
                        "active_students": active_students,
                    })
                elif next_semester is None and can_add_semester:
                    next_steps.append({
                        "kind": "missing_semester",
                        "semester": semester,
                        "active_students": active_students,
                    })

    if (
        current_year
        and (can_add_semester or can_add_fees)
        and 0 <= (current_year.end_date - today).days <= 30
    ):
        next_year = AcademicYear.objects.filter(
            start_date__gt=current_year.end_date,
        ).order_by("start_date", "pk").first()
        if next_year:
            next_semesters = (
                [semester for semester in semesters if semester.academic_year_id == next_year.pk]
                if semesters is not None
                else list(Semester.objects.filter(academic_year=next_year)
                          .select_related("academic_year").order_by("start_date", "pk"))
            )
            if can_add_semester and len({semester.number for semester in next_semesters}) < 2:
                next_steps.append({"kind": "year_semesters", "next_year": next_year})

            fee_semesters = [
                semester for semester in next_semesters
                if semester != financial_semester
            ]
            if can_add_fees and fee_semesters:
                applicable_pairs = {
                    (program_id, year_level)
                    for program_id, duration in Program.objects.filter(active=True)
                    .values_list("pk", "duration_years")
                    for year_level in range(1, duration + 1)
                }
                if applicable_pairs:
                    configured = defaultdict(set)
                    for semester_id, program_id, year_level in (
                        FeeStructure.objects.filter(
                            semester__in=fee_semesters,
                            items__isnull=False,
                        ).order_by().values_list("semester_id", "program_id", "year_level").distinct()
                    ):
                        configured[semester_id].add((program_id, year_level))
                    fee_view = (
                        "fee_structure_list"
                        if request.user.has_perm("school.view_feestructure")
                        else "fee_structure_create"
                    )
                    for semester in fee_semesters:
                        if applicable_pairs - configured[semester.pk]:
                            next_steps.append({
                                "kind": "year_fees",
                                "next_year": next_year,
                                "semester": semester,
                                "url": reverse(fee_view, kwargs={"semester_id": semester.pk}),
                            })

    context["next_steps"] = next_steps
    return render(request, "school/dashboard.html", context)


@login_required
def reminders(request):
    """Display reminders about students with missing details."""
    students = students_with_missing_details()
    paginator = Paginator(students, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    context = {
        "page_obj": page_obj,
        "total_reminders": students.count(),
    }
    return render(request, "school/reminders.html", context)


# ============================================================
# FINANCIAL RECORDS
# ============================================================

@permission_required("school.can_view_financial_reports", raise_exception=True)
def financial_records(request):
    """
    Institution-wide financial records showing aggregate charged/paid/outstanding
    per semester, grouped by academic year.
    """
    return render_report(request, "financial_records", "financial")

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
        
        # Count distinct students charged in this semester
        students_charged = StudentCharge.objects.filter(
            fee_item__fee_structure__semester=sem
        ).values('student').distinct().count()

        semester_data.append({
            "semester": sem,
            "academic_year": sem.academic_year,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "outstanding": outstanding,
            "collection_rate": collection_rate,
            "students_charged": students_charged,
        })

    # Group by academic year and compute totals per year
    year_groups = []
    for year, semesters_iter in groupby(semester_data, key=lambda x: x["academic_year"]):
        semesters = list(semesters_iter)
        charged = sum(s["total_charged"] for s in semesters)
        paid = sum(s["total_paid"] for s in semesters)
        students_charged = sum(s["students_charged"] for s in semesters)
        year_groups.append({
            "year": year,
            "semesters": semesters,
            "totals": {
                "charged": charged,
                "paid": paid,
                "outstanding": sum(s["outstanding"] for s in semesters),
                "collection_rate": (paid / charged * 100) if charged > 0 else 0,
                "students_charged": students_charged,
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

    statuses = [Student.ACTIVE]
    if request.GET.get("include_deferred") == "1":
        statuses.append(Student.DEFERRED)

    name_query = Q()
    for term in query.split():
        name_query &= Q(first_name__icontains=term) | Q(last_name__icontains=term)

    students = (
        Student.objects.filter(status__in=statuses)
        .select_related("program")
        .filter(
            Q(student_number__icontains=query)
            | name_query
        )
        .order_by("last_name", "first_name")[:8]
    )

    data = []
    today = get_current_date()
    can_record_payments = request.user.has_perm("school.can_record_payments")

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
        payment_url = None
        if can_record_payments and student.status == Student.ACTIVE:
            payment_url = f"{reverse('payment_create')}?student={student.pk}"
        data.append(
            {
                "id": student.id,
                "student_number": student.student_number,
                "name": f"{student.first_name} {student.last_name}",
                "program": (
                    enrollment.program.name
                    if enrollment
                    else student.program.name
                ),
                "semester": str(enrollment.semester) if enrollment else "No active semester",
                "course_year": enrollment.year_level if enrollment else None,
                "status": student.get_status_display(),
                "detail_url": reverse("student_detail", args=[student.pk]),
                "payment_url": payment_url,
            }
        )

    return JsonResponse({"students": data})


# ============================================================
# REPORTS
# ============================================================


@login_required
def reports_index(request):
    """Permission-aware reports hub with gated quick answers."""
    visible = permitted_reports(request.user)
    today = get_current_date()
    quick_answers = []
    working_semester = get_working_semester(today)
    if request.user.has_perm("school.can_view_financial_reports"):
        today_total = Payment.objects.filter(payment_date=today).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        quick_answers.append({"label": "Collected today", "value": f"${today_total:.2f}", "url": reverse("daily_collections_report") + "?date=" + today.isoformat()})
    if request.user.has_perm("school.can_view_outstanding_reports"):
        owing = outstanding_students(working_semester) if working_semester else Student.objects.none()
        totals = owing.aggregate(total=Sum("balance"))
        quick_answers.append({"label": "Owed this semester", "value": f"${totals['total'] or Decimal('0'):.2f}", "url": reverse("outstanding_report") + (f"?semester={working_semester.pk}" if working_semester else "")})
    if request.user.has_perm("school.view_feestructure"):
        missing = unconfigured_fee_structures(working_semester) if working_semester else []
        quick_answers.append({"label": "Fees still missing", "value": str(len(missing)), "url": reverse("fee_audit_report") + (f"?semester={working_semester.pk}" if working_semester else "")})
    if request.user.has_perm("school.view_student"):
        enrolled = Student.objects.filter(status=Student.ACTIVE).count()
        quick_answers.append({"label": "Enrolled students", "value": str(enrolled), "url": reverse("enrollment_report")})
    groups = []
    for group in ("Money", "People", "Setup"):
        group_reports = [spec for spec in visible if spec.group == group]
        if group_reports:
            groups.append({"name": group, "reports": group_reports})
    return render(request, "school/reports/index.html", {
        "reports": visible, "groups": groups, "quick_answers": quick_answers,
    })


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
    
    return get_working_semester(today)


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
    return render_report(request, "enrollment_report", "enrollment")
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
    return render_report(request, "outstanding_report", "outstanding")
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
    return render_report(request, "fee_audit_report", "fee-audit")
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
    return render_report(request, "payment_methods_report", "methods")
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
    return render_report(request, "program_revenue_report", "revenue")
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
    return render_report(request, "daily_collections_report", "daily")
    """Daily collections / cashbook report."""
    from datetime import datetime
    
    today = get_current_date()
    date_filter = request.GET.get("date")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    filter_date = today
    start_date = None
    end_date = None
    
    # Handle date range if provided
    if date_from and date_to:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            start_date = None
            end_date = None
    # Fall back to single date if provided
    elif date_filter:
        try:
            filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
        except ValueError:
            filter_date = today
    
    export_format = request.GET.get("format")
    
    # Get payments based on date range or single date
    if start_date and end_date:
        payments = daily_collections(start_date=start_date, end_date=end_date)
        display_date = f"{start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}"
    else:
        payments = daily_collections(filter_date)
        display_date = filter_date.strftime("%b %d, %Y")
    
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
        
        if start_date and end_date:
            filename = f"daily_collections_{start_date.isoformat()}_to_{end_date.isoformat()}.csv"
        else:
            filename = f"daily_collections_{filter_date.isoformat()}.csv"
        
        return _export_csv_response(filename, headers, rows)
    
    context = {
        "filter_date": filter_date,
        "date_from": date_from,
        "date_to": date_to,
        "display_date": display_date,
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
    return render_report(request, "status_history_report", "status-history")
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

    today = get_current_date()
    all_semesters = list(
        Semester.objects.select_related('academic_year').order_by(
            '-academic_year__name', 'number'
        )
    )

    progress = fee_progress_for_semesters(all_semesters)
    for semester in all_semesters:
        semester.fee_progress = progress[semester.pk]

    active_sems = []
    upcoming_sems = []
    completed_sems = []

    for semester in all_semesters:
        status = semester.status  # uses frozen date via property
        if status == 'ACTIVE':
            active_sems.append(semester)
        elif status == 'UPCOMING':
            upcoming_sems.append(semester)
        else:
            completed_sems.append(semester)

    active_sems.sort(key=lambda s: s.start_date)
    upcoming_sems.sort(key=lambda s: s.start_date)
    completed_sems.sort(key=lambda s: s.start_date, reverse=True)

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
    can_copy = request.user.has_perm("school.add_feestructure")
    copy_sources = _copy_sources() if can_copy else []

    if form.is_valid():
        semester = form.save()
        fees_mode = request.POST.get("fees_mode", "empty")
        source = next(
            (item for item in copy_sources
             if str(item.pk) == request.POST.get("copy_source")),
            None,
        )

        if fees_mode == "copy" and source and can_copy:
            result = copy_fee_structures(source, semester)
            if result["copied"]:
                messages.success(
                    request,
                    _copy_message(source, result) + " Check the amounts below.",
                )
            else:
                messages.warning(
                    request,
                    f"{_semester_label(source)} had no fees to copy. "
                    "Set them up below.",
                )
            return redirect(_grid_url(semester))

        messages.success(
            request,
            "Semester created. Set up fees for each trade and course year.",
        )
        return redirect(_grid_url(semester))

    default_copy_source = copy_sources[0] if copy_sources else None
    fees_mode_value = (
        request.POST.get("fees_mode")
        if request.method == "POST"
        else ("copy" if can_copy and copy_sources else "empty")
    )
    copy_source_value = (
        request.POST.get("copy_source")
        or (default_copy_source.pk if default_copy_source else "")
    )

    return render(
        request,
        "school/semester_form.html",
        {
            "form": form,
            "title": "New semester",
            "back_url": "semester_list",
            "can_copy": can_copy,
            "copy_sources": copy_sources,
            "default_copy_source": default_copy_source,
            "fees_mode_value": fees_mode_value,
            "copy_source_value": copy_source_value,
        },
    )


@permission_required("school.change_semester", raise_exception=True)
def semester_edit(request, pk):
    semester = get_object_or_404(Semester, pk=pk)

    # Prevent editing completed semesters
    if semester.status == 'COMPLETED':
        messages.error(request, "Completed semesters cannot be edited.")
        return redirect('semester_list')

    form = SemesterForm(request.POST or None, instance=semester)

    if form.is_valid():
        form.save()
        messages.success(request, "Semester updated.")
        return redirect("semester_list")

    return render(
        request,
        "school/semester_form.html",
        {
            "form": form,
            "semester": semester,
            "title": f"Edit {semester}",
            "submit_label": "Save dates",
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
    progress = fee_progress(semester)

    try:
        highlight_program = int(request.GET.get("program", ""))
    except (TypeError, ValueError):
        highlight_program = None
    try:
        highlight_year = int(request.GET.get("year", ""))
    except (TypeError, ValueError):
        highlight_year = None

    filter_value = request.GET.get("filter", "all")
    if filter_value not in ("all", "needs", "set-up"):
        filter_value = "all"

    next_cell = None
    if progress["needs"]:
        next_cell = next(
            (cell for cell in progress["cells"] if not cell["set_up"]),
            None,
        )

    return render(
        request,
        "school/fee_structure_list.html",
        {
            "semester": semester,
            "progress": progress,
            "rows": progress["rows"],
            "max_year": progress["max_year"],
            "year_range": range(1, progress["max_year"] + 1),
            "set_up_count": progress["set_up"],
            "total_cells": progress["total"],
            "needs_count": progress["needs"],
            "waiting_count": progress["waiting"],
            "set_up_pct": round(
                progress["set_up"] / progress["total"] * 100
            ) if progress["total"] else 0,
            "filter_value": filter_value,
            "highlight_program": highlight_program,
            "highlight_year": highlight_year,
            "next_cell": next_cell,
            "is_locked": _fee_locked(semester),
        },
    )


def _fee_names(semester):
    existing = set(
        FeeStructureItem.objects.filter(fee_structure__semester=semester)
        .values_list("name", flat=True)
    )
    return sorted(existing | {"Tuition", "Levy", "Accommodation"})


def _start_options(semester, exclude_pk=None):
    queryset = (
        FeeStructure.objects.filter(semester=semester, items__isnull=False)
        .select_related("program")
        .prefetch_related("items")
        .order_by("program__name", "year_level")
    )
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)

    options = []
    for structure in queryset:
        items = list(structure.items.all())
        total = sum((item.amount for item in items), Decimal("0"))
        options.append({
            "label": (
                f"{structure.program.name} · Course year "
                f"{structure.year_level} · ${total:,.2f}"
            ),
            "items": [
                {"name": item.name, "amount": str(item.amount)}
                for item in items
            ],
        })
    return options


@transaction.atomic
@permission_required("school.add_feestructure", raise_exception=True)
def fee_structure_create(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)

    if _fee_locked(semester):
        messages.error(request, "This semester is completed. Fees are locked.")
        return redirect("fee_structure_list", semester_id=semester.pk)

    if request.method == "POST":
        context_locked = request.POST.get("context_locked") == "1"
    else:
        context_locked = bool(
            request.GET.get("program") and request.GET.get("year_level")
        )

    locked_program = None
    locked_year = None
    if context_locked:
        program_id = request.POST.get("program") or request.GET.get("program")
        year_value = request.POST.get("year_level") or request.GET.get("year_level")
        locked_program = (
            Program.objects.filter(pk=program_id).first() if program_id else None
        )
        try:
            locked_year = int(year_value)
        except (TypeError, ValueError):
            locked_year = None

        if not locked_program or not locked_year:
            messages.error(request, "Choose a trade and course year first.")
            return redirect("fee_structure_list", semester_id=semester.pk)

        existing = FeeStructure.objects.filter(
            semester=semester,
            program=locked_program,
            year_level=locked_year,
        ).first()
        if existing and request.method == "GET":
            messages.info(request, "Those fees are already set up. Change them below.")
            return redirect("fee_structure_edit", pk=existing.pk)

    fee_structure = FeeStructure(semester=semester)
    if locked_program:
        fee_structure.program = locked_program
        fee_structure.year_level = locked_year

    if request.method == "POST":
        form = FeeStructureForm(request.POST, instance=fee_structure)
        formset = FeeStructureItemFormSet(request.POST, instance=fee_structure)

        form_valid = form.is_valid()
        formset_valid = formset.is_valid()

        if form_valid:
            selected_program = form.cleaned_data["program"]
            selected_year = form.cleaned_data["year_level"]
            duplicate = FeeStructure.objects.filter(
                semester=semester,
                program=selected_program,
                year_level=selected_year,
            ).first()

            if duplicate:
                messages.info(
                    request,
                    "Those fees are already set up. Change them below.",
                )
                return redirect("fee_structure_edit", pk=duplicate.pk)

        if form_valid and formset_valid:
            fee_structure = form.save(commit=False)
            fee_structure.semester = semester
            fee_structure.save()
            formset.instance = fee_structure
            formset.save()

            charges_created = create_charges_for_fee_structure(fee_structure)
            saved_message = (
                "Fees saved for "
                f"{fee_structure.program.name} Course year "
                f"{fee_structure.year_level}."
            )
            if charges_created:
                saved_message += (
                    f" {charges_created} student "
                    f"charge{'s' if charges_created != 1 else ''} created."
                )
            messages.success(request, saved_message)
            if request.POST.get("save_and_next"):
                next_cell = next_fee_cell(semester)
                if next_cell:
                    return redirect(
                        reverse(
                            "fee_structure_create",
                            args=[semester.pk],
                        )
                        + f"?program={next_cell['program'].pk}"
                        f"&year_level={next_cell['year_level']}"
                    )
            return redirect(_grid_url(
                semester,
                fee_structure.program_id,
                fee_structure.year_level,
            ))
    else:
        form = FeeStructureForm(instance=fee_structure)
        formset = FeeStructureItemFormSet(
            instance=fee_structure,
            initial=[{"name": "Tuition"}],
        )

    counts = enrolled_counts(semester)
    impact = None
    if locked_program and locked_year:
        impact = counts.get((locked_program.pk, locked_year), 0)

    return render(
        request,
        "school/fee_structure_form.html",
        {
            "form": form,
            "formset": formset,
            "semester": semester,
            "title": "Set up fees",
            "context_locked": context_locked,
            "locked_program": locked_program,
            "locked_year": locked_year,
            "impact": impact,
            "is_locked": False,
            "fee_names": _fee_names(semester),
            "start_options": _start_options(semester),
            "enrollment_counts": {
                f"{program_id}-{year_level}": count
                for (program_id, year_level), count in counts.items()
            },
            "program_years": {
                str(program.pk): program.duration_years
                for program in _active_programs()
            },
            "next_needs_cell": next_fee_cell(semester),
            "back_url": _grid_url(
                semester,
                locked_program.pk if locked_program else None,
                locked_year if locked_program else None,
            ),
        },
    )


@transaction.atomic
@permission_required("school.change_feestructure", raise_exception=True)
def fee_structure_edit(request, pk):
    fee_structure = get_object_or_404(
        FeeStructure.objects.select_related("semester", "program"),
        pk=pk,
    )
    semester = fee_structure.semester

    if _fee_locked(semester):
        if request.method == "POST":
            messages.error(request, "This semester is completed. Fees are locked.")
            return redirect("fee_structure_list", semester_id=semester.pk)

        locked_items = list(
            _fee_item_queryset(fee_structure).order_by("name")
        )
        return render(
            request,
            "school/fee_structure_form.html",
            {
                "form": None,
                "formset": None,
                "semester": semester,
                "fee_structure": fee_structure,
                "title": "Fees",
                "context_locked": True,
                "locked_program": fee_structure.program,
                "locked_year": fee_structure.year_level,
                "impact": enrolled_counts(semester).get(
                    (fee_structure.program_id, fee_structure.year_level), 0
                ),
                "is_locked": True,
                "items": locked_items,
                "locked_total": sum(
                    (item.amount for item in locked_items), Decimal("0")
                ),
                "back_url": _grid_url(
                    semester,
                    fee_structure.program_id,
                    fee_structure.year_level,
                ),
            },
        )

    if request.method == "POST":
        form = FeeStructureForm(request.POST, instance=fee_structure)
        formset = FeeStructureItemFormSet(
            request.POST,
            instance=fee_structure,
            queryset=_fee_item_queryset(fee_structure),
        )

        form_valid = form.is_valid()
        formset_valid = formset.is_valid()

        if form_valid and formset_valid:
            new_program = form.cleaned_data["program"]
            new_year = form.cleaned_data["year_level"]
            duplicate = (
                FeeStructure.objects.filter(
                    semester=semester,
                    program=new_program,
                    year_level=new_year,
                )
                .exclude(pk=fee_structure.pk)
                .first()
            )

            if duplicate:
                form.add_error(
                    None,
                    "Fees already exist for that trade and course year.",
                )
            else:
                changed_charged = 0
                for item_form in formset.forms:
                    data = getattr(item_form, "cleaned_data", None)
                    if not data or data.get("DELETE") or not item_form.instance.pk:
                        continue
                    amount = data.get("amount")
                    if (
                        amount is not None
                        and amount != item_form.instance.amount
                        and item_form.instance.student_charges.exists()
                    ):
                        changed_charged += 1

                form.save()
                formset.save()
                charges_created = create_charges_for_fee_structure(fee_structure)

                message = (
                    f"Fees updated for {new_program.name} Course year {new_year}."
                )
                if charges_created:
                    message += (
                        f" {charges_created} new student "
                        f"charge{'s' if charges_created != 1 else ''} created."
                    )
                if changed_charged:
                    message += (
                        f" {changed_charged} fee line"
                        f"{'s' if changed_charged != 1 else ''} already charged "
                        "keep their earlier amounts."
                    )

                messages.success(request, message)
                if request.POST.get("save_and_next"):
                    next_cell = next_fee_cell(semester)
                    if next_cell:
                        return redirect(
                            reverse(
                                "fee_structure_create",
                                args=[semester.pk],
                            )
                            + f"?program={next_cell['program'].pk}"
                            f"&year_level={next_cell['year_level']}"
                        )
                return redirect(_grid_url(
                    semester,
                    fee_structure.program_id,
                    fee_structure.year_level,
                ))
    else:
        form = FeeStructureForm(instance=fee_structure)
        formset = FeeStructureItemFormSet(
            instance=fee_structure,
            queryset=_fee_item_queryset(fee_structure),
        )

    return render(
        request,
        "school/fee_structure_form.html",
        {
            "form": form,
            "formset": formset,
            "semester": semester,
            "fee_structure": fee_structure,
            "title": "Fees",
            "context_locked": True,
            "locked_program": fee_structure.program,
            "locked_year": fee_structure.year_level,
            "impact": enrolled_counts(semester).get(
                (fee_structure.program_id, fee_structure.year_level), 0
            ),
            "is_locked": False,
            "fee_names": _fee_names(semester),
            "start_options": _start_options(semester, exclude_pk=fee_structure.pk),
            "enrollment_counts": {
                f"{program_id}-{year_level}": count
                for (program_id, year_level), count in enrolled_counts(semester).items()
            },
            "next_needs_cell": next_fee_cell(
                semester, exclude_structure_pk=fee_structure.pk
            ),
            "back_url": _grid_url(
                semester,
                fee_structure.program_id,
                fee_structure.year_level,
            ),
        },
    )


# ============================================================
# COPY FEES FROM ANOTHER SEMESTER
# ============================================================

@permission_required("school.add_feestructure", raise_exception=True)
def fee_structure_copy(request, semester_id):
    """Preview and copy set-up fees from another semester into empty cells."""
    semester = get_object_or_404(
        Semester.objects.select_related("academic_year"),
        pk=semester_id,
    )

    if _fee_locked(semester):
        messages.error(request, "This semester is completed. Fees are locked.")
        return redirect("fee_structure_list", semester_id=semester.pk)

    sources = _copy_sources(exclude_semester=semester)
    if not sources:
        messages.warning(
            request,
            "No other semester has fees set up yet. Set up fees for one trade "
            "and course year first, then copy them here.",
        )
        return redirect("fee_structure_list", semester_id=semester.pk)

    earlier = [s for s in sources if s.start_date < semester.start_date]
    default_source = earlier[0] if earlier else sources[0]
    requested = request.POST.get("source") or request.GET.get("source")
    source = next(
        (s for s in sources if str(s.pk) == str(requested)),
        default_source,
    )

    if request.method == "POST":
        result = copy_fee_structures(source, semester)
        messages.success(request, _copy_message(source, result))
        return redirect(_grid_url(semester))

    progress = fee_progress(semester)
    target_cells = {
        (cell["program"].pk, cell["year_level"]): cell
        for cell in progress["cells"]
    }
    source_structures = (
        FeeStructure.objects.filter(semester=source, items__isnull=False)
        .annotate(
            item_count=Count("items", distinct=True),
            total=Coalesce(Sum("items__amount"), Value(Decimal("0"))),
        )
        .select_related("program")
        .order_by("program__name", "year_level")
    )

    preview = []
    will_copy = already = unavailable = 0
    for structure in source_structures:
        target_cell = target_cells.get(
            (structure.program_id, structure.year_level)
        )
        if target_cell is None or not target_cell["applicable"]:
            state = "skip"
            unavailable += 1
        elif target_cell["set_up"]:
            state = "exists"
            already += 1
        else:
            state = "copy"
            will_copy += 1

        preview.append({
            "program_name": structure.program.name,
            "year_level": structure.year_level,
            "fee_count": structure.item_count,
            "total": structure.total,
            "state": state,
        })

    return render(
        request,
        "school/fee_structure_copy.html",
        {
            "semester": semester,
            "source": source,
            "sources": sources,
            "preview": preview,
            "will_copy": will_copy,
            "already": already,
            "unavailable": unavailable,
            "title": f"Copy fees into {semester}",
            "back_url": _grid_url(semester),
        },
    )


# ============================================================
# BULK FEE CONFIGURATION
# ============================================================

@permission_required("school.add_feestructure", raise_exception=True)
@transaction.atomic
def bulk_fee_configuration(request, semester_id):
    """Add or update one fee line across many trades and course years."""
    semester = get_object_or_404(
        Semester.objects.select_related("academic_year"),
        pk=semester_id,
    )

    if _fee_locked(semester):
        messages.error(request, "This semester is completed. Fees are locked.")
        return redirect("fee_structure_list", semester_id=semester.pk)

    if request.method == "POST":
        form = BulkFeeForm(request.POST)
        if form.is_valid():
            programs = form.cleaned_data["programs"]
            year_levels = [int(yl) for yl in form.cleaned_data["year_levels"]]
            fee_name = form.cleaned_data["fee_name"].strip()
            amount = form.cleaned_data["amount"]
            description = (form.cleaned_data["description"] or "").strip()

            added = changed = unchanged = 0
            skipped = 0
            changes_charged = 0
            charges_created = 0
            trade_years = 0

            for program in programs:
                for year_level in year_levels:
                    if year_level > program.duration_years:
                        skipped += 1
                        continue

                    trade_years += 1
                    fee_structure, _ = FeeStructure.objects.get_or_create(
                        program=program,
                        year_level=year_level,
                        semester=semester,
                    )

                    fee_item = (
                        fee_structure.items
                        .filter(name__iexact=fee_name)
                        .first()
                    )
                    if fee_item is None:
                        FeeStructureItem.objects.create(
                            fee_structure=fee_structure,
                            name=fee_name,
                            amount=amount,
                            description=description,
                        )
                        added += 1
                    elif (
                        fee_item.amount != amount
                        or (fee_item.description or "") != description
                    ):
                        if (
                            fee_item.amount != amount
                            and fee_item.student_charges.exists()
                        ):
                            changes_charged += 1
                        fee_item.amount = amount
                        fee_item.description = description
                        fee_item.save(update_fields=["amount", "description"])
                        changed += 1
                    else:
                        unchanged += 1

                    charges_created += create_charges_for_fee_structure(
                        fee_structure
                    )

            message = (
                f"{fee_name} applied to {trade_years} trade-year"
                f"{'s' if trade_years != 1 else ''}."
            )
            parts = []
            if added:
                parts.append(f"{added} new")
            if changed:
                parts.append(f"{changed} changed")
            if unchanged:
                parts.append(f"{unchanged} already had it")
            if parts:
                message += " " + ", ".join(parts) + "."
            if charges_created:
                message += (
                    f" {charges_created} student charge"
                    f"{'s' if charges_created != 1 else ''} created."
                )
            if changes_charged:
                message += (
                    f" {changes_charged} changed fee line"
                    f"{'s' if changes_charged != 1 else ''} were already "
                    "charged; those students keep their earlier amounts."
                )
            if skipped:
                message += (
                    f" {skipped} selected course year"
                    f"{'s' if skipped != 1 else ''} do not exist for the "
                    "chosen trades and were skipped."
                )

            messages.success(request, message)
            return redirect(_grid_url(semester))
    else:
        form = BulkFeeForm()

    programs_data = [
        {
            "id": program.pk,
            "name": program.name,
            "duration": program.duration_years,
        }
        for program in _active_programs()
    ]
    existing_items = defaultdict(dict)
    for item in (
        FeeStructureItem.objects
        .filter(fee_structure__semester=semester)
        .select_related("fee_structure")
    ):
        key = f"{item.fee_structure.program_id}-{item.fee_structure.year_level}"
        existing_items[key][item.name] = str(item.amount)

    max_year = max(
        (program["duration"] for program in programs_data),
        default=0,
    )

    return render(
        request,
        "school/bulk_fee_form.html",
        {
            "form": form,
            "semester": semester,
            "title": "Set one fee for many",
            "is_locked": False,
            "programs_data": programs_data,
            "max_year": max_year,
            "year_level_options": range(1, max_year + 1),
            "selected_programs": (
                form.data.getlist("programs") if form.is_bound else []
            ),
            "selected_years": (
                form.data.getlist("year_levels") if form.is_bound else []
            ),
            "fee_names": _fee_names(semester),
            "preview_json": {
                "programs": programs_data,
                "items": dict(existing_items),
                "students": {
                    f"{program_id}-{year_level}": count
                    for (program_id, year_level), count in enrolled_counts(
                        semester
                    ).items()
                },
            },
            "back_url": _grid_url(semester),
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

    today = get_current_date()

    students = Student.objects.all()
    total_students = Student.objects.count()
    if query:
        students = students.filter(
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )

    if program_filter:
        students = students.filter(program_id=program_filter)

    # --- Status filter logic ---
    if status_filter == "all":
        pass
    elif status_filter:
        students = students.filter(status=status_filter.upper())
    else:
        # Default: Active + Deferred
        students = students.filter(status__in=[Student.ACTIVE, Student.DEFERRED])

    # Year level filter
    if year_level_filter:
        students = students.filter(
            enrollments__status=Enrollment.ACTIVE,
            enrollments__semester__end_date__gte=today,
            enrollments__year_level=year_level_filter
        ).distinct()

    # Program counts for filter pills
    program_counts = Student.objects.values("program__id", "program__name").annotate(
        count=Count("id")
    ).order_by("program__name")

    status_counts = Student.objects.values("status").annotate(
        count=Count("id")
    ).order_by("status")

    max_year_level = Program.objects.aggregate(max_duration=Max("duration_years"))["max_duration"] or 6

    students = students.select_related("program", "intake_year").prefetch_related(
        "enrollments__semester"
    )
    filtered_count = students.count()
    paginator = Paginator(students, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "total_students": total_students,
        "filtered_count": filtered_count,
        "page_obj": page_obj,
        "query": query,
        "status_filter": status_filter,
        "program_filter": program_filter,
        "year_level_filter": year_level_filter,
        "status_choices": Student.STATUS_CHOICES,
        "program_counts": program_counts,
        "status_counts": {s["status"]: s["count"] for s in status_counts},
        "max_year_level": max_year_level,
        "today": today,
    }
    return render(request, "school/student_list.html", context)


@transaction.atomic
@permission_required("school.change_student", raise_exception=True)
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student_form = StudentForm(request.POST or None, instance=student)

    if request.method == "POST":
        if student_form.is_valid():
            student_form.save()
            messages.success(request, "Student details updated successfully.")
            return redirect("student_detail", pk=student.pk)
        else:
            messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "school/student_register.html",
        {
            "form": student_form,
            "student": student,
            "is_edit": True,
            "title": f"Edit Student — {student}",
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
                    start_year_level=year_level,
                    program=student_form.instance.program
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


@permission_required("school.add_student", raise_exception=True)
def student_import(request):
    """
    Bulk-import students from an uploaded .xlsx/.csv spreadsheet.

    Two phases, both POSTs to this same view:
      1. Upload + choose intake year/semester/year level/status -> parse the
         file, validate every row, and show a preview (nothing is saved yet).
      2. "Confirm import" -> re-create the already-validated rows (passed
         back as a hidden JSON field) as real Student + Enrollment records.
    """
    import json
    from school.utils.student_import import parse_student_spreadsheet, validate_rows

    if request.method == "POST" and request.POST.get("confirm") == "1":
        try:
            rows = json.loads(request.POST.get("rows_json", "[]"))
        except (ValueError, TypeError):
            rows = []

        try:
            intake_year = AcademicYear.objects.get(pk=request.POST.get("intake_year"))
            semester = Semester.objects.get(pk=request.POST.get("semester"))
            year_level = int(request.POST.get("year_level"))
        except (AcademicYear.DoesNotExist, Semester.DoesNotExist, TypeError, ValueError):
            messages.error(request, "Your import session expired or was invalid. Please upload the file again.")
            return redirect("student_import")

        status = request.POST.get("default_status") or Student.ACTIVE
        if status not in dict(Student.STATUS_CHOICES):
            status = Student.ACTIVE

        created_count = 0
        skipped = []
        with transaction.atomic():
            for row in rows:
                program = Program.objects.filter(pk=row.get("program_id")).first()
                if not program or not row.get("student_number"):
                    skipped.append(row.get("student_number", "?"))
                    continue
                if Student.objects.filter(student_number=row["student_number"]).exists():
                    skipped.append(row["student_number"])
                    continue

                student = Student.objects.create(
                    student_number=row["student_number"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    national_id="",
                    program=program,
                    intake_year=intake_year,
                    status=status,
                )
                create_academic_year_enrollments(
                    student=student,
                    start_semester=semester,
                    start_year_level=year_level,
                    program=program,
                )
                StudentStatusLog.objects.create(
                    student=student,
                    status=status,
                    note="Imported from spreadsheet.",
                )
                created_count += 1

        from school.utils.audit import log_action
        log_action(
            user=request.user,
            action='OTHER',
            summary=f"Bulk-imported {created_count} student(s) from spreadsheet",
            details={
                "count": created_count,
                "intake_year": intake_year.name,
                "semester": str(semester),
                "skipped": skipped,
            },
            category='STUDENT',
        )

        if skipped:
            messages.warning(
                request,
                f"Imported {created_count} student(s). Skipped {len(skipped)} row(s) "
                f"that were no longer valid (e.g. duplicate student number): "
                f"{', '.join(skipped)}.",
            )
        else:
            messages.success(request, f"Imported {created_count} student(s) successfully.")
        return redirect("student_list")

    form = StudentImportForm(request.POST or None, request.FILES or None)
    preview = None

    if request.method == "POST":
        if form.is_valid():
            try:
                parsed = parse_student_spreadsheet(form.cleaned_data["file"])
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, "school/student_import.html", {"form": form})

            if not parsed:
                messages.error(request, "No student rows were found in that file.")
                return render(request, "school/student_import.html", {"form": form})

            validated = validate_rows(parsed)
            valid_rows = [r for r in validated if not r["errors"]]
            invalid_rows = [r for r in validated if r["errors"]]

            rows_json = json.dumps([
                {
                    "student_number": r["student_number"],
                    "first_name": r["first_name"],
                    "last_name": r["last_name"],
                    "program_id": r["program"].id,
                    "program_code": r["program_code"],
                }
                for r in valid_rows
            ])

            preview = {
                "valid_rows": valid_rows,
                "invalid_rows": invalid_rows,
                "rows_json": rows_json,
                "intake_year": form.cleaned_data["intake_year"],
                "semester": form.cleaned_data["semester"],
                "year_level": form.cleaned_data["year_level"],
                "default_status": form.cleaned_data["default_status"],
                "valid_count": len(valid_rows),
                "invalid_count": len(invalid_rows),
            }
        else:
            messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "school/student_import.html",
        {"form": form, "preview": preview},
    )


@permission_required("school.view_student", raise_exception=True)
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    today = get_current_date()

    # ---------------------------------------------------------
    # Current enrollment and year level
    # ---------------------------------------------------------

    current_enrollment = student.get_current_enrollment(today)
    current_year_level = (
        current_enrollment.year_level
        if current_enrollment
        else None
    )

    # ---------------------------------------------------------
    # Current academic year (date-based, falling back to flag)
    # ---------------------------------------------------------

    current_year = (
        AcademicYear.objects
        .filter(
            start_date__lte=today,
            end_date__gte=today,
        )
        .first()
        or AcademicYear.objects.filter(is_current=True).first()
    )

    # ---------------------------------------------------------
    # Years available to this student: past, present, upcoming
    # ---------------------------------------------------------

    # Years the student actually belongs to (intake or any activity). These
    # define how far back the selector should go.
    student_year_ids = (
        set(student.enrollments.values_list(
            "semester__academic_year_id", flat=True
        ))
        | set(student.charges.values_list(
            "enrollment__semester__academic_year_id", flat=True
        ))
        | set(student.payments.values_list(
            "semester__academic_year_id", flat=True
        ))
    )

    if student.intake_year_id:
        student_year_ids.add(student.intake_year_id)

    year_ids = set(student_year_ids)

    if current_year:
        year_ids.add(current_year.pk)

    # The single upcoming academic year is only relevant to active students.
    upcoming_year = None
    if current_year and student.status == Student.ACTIVE:
        upcoming_year = (
            AcademicYear.objects
            .filter(start_date__gt=current_year.end_date)
            .order_by("start_date")
            .first()
        )
        if upcoming_year:
            year_ids.add(upcoming_year.pk)

    years = list(
        AcademicYear.objects
        .filter(pk__in=year_ids)
        .order_by("start_date")
    )

    # Don't offer years from before the student joined (e.g. a 2027 intake
    # shouldn't see the current 2026 pill).
    if student_year_ids:
        first_start = min(
            y.start_date for y in years if y.pk in student_year_ids
        )
        years = [y for y in years if y.end_date >= first_start]

    # ---------------------------------------------------------
    # Selected year: request parameter, else current year
    # ---------------------------------------------------------

    selected_year = None
    requested_year = request.GET.get("year")
    if requested_year:
        selected_year = next(
            (y for y in years if str(y.pk) == requested_year),
            None,
        )

    if selected_year is None and years:
        past_years = [y for y in years if y.end_date < today]
        future_years = [y for y in years if y.start_date > today]

        # Between semesters the calendar year may hold nothing for a student who
        # is already enrolled in (and paying for) the next academic year, so
        # open that year instead of a blank current year.
        enrollment_year = (
            current_enrollment.semester.academic_year
            if current_enrollment else None
        )
        current_year_has_activity = False
        if current_year in years:
            current_year_has_activity = (
                student.enrollments.filter(
                    semester__academic_year=current_year
                ).exists()
                or student.charges.filter(
                    enrollment__semester__academic_year=current_year
                ).exists()
                or student.payments.filter(
                    semester__academic_year=current_year
                ).exists()
            )

        if current_year_has_activity:
            selected_year = current_year
        elif enrollment_year in years:
            selected_year = enrollment_year
        elif current_year in years:
            selected_year = current_year
        elif past_years:
            selected_year = past_years[-1]
        elif future_years:
            selected_year = future_years[0]
        else:
            selected_year = years[0]

    selected_index = (
        years.index(selected_year) if selected_year in years else -1
    )
    previous_year = (
        years[selected_index - 1] if selected_index > 0 else None
    )
    next_year = (
        years[selected_index + 1]
        if 0 <= selected_index < len(years) - 1
        else None
    )

    # ---------------------------------------------------------
    # Every semester on the student's line, with its money
    # ---------------------------------------------------------

    semesters = list(
        Semester.objects
        .filter(academic_year__in=years)
        .select_related("academic_year")
        .order_by("start_date")
    )

    enrollments_by_semester = {
        e.semester_id: e
        for e in student.enrollments.select_related("program")
    }

    charges_by_semester = defaultdict(list)
    for charge in (
        student.charges
        .select_related("fee_item", "enrollment")
        .order_by("fee_item__name", "pk")
    ):
        charges_by_semester[charge.enrollment.semester_id].append(charge)

    payments_by_semester = defaultdict(list)
    for payment in student.payments.order_by("-payment_date", "-pk"):
        payments_by_semester[payment.semester_id].append(payment)

    fee_structures = {
        (fs.program_id, fs.year_level, fs.semester_id): fs
        for fs in (
            FeeStructure.objects
            .filter(semester__in=semesters)
            .annotate(item_count=Count("items"))
        )
    }

    rows_by_year = defaultdict(list)
    all_rows = []

    for semester in semesters:
        enrollment = enrollments_by_semester.get(semester.pk)
        charges = charges_by_semester.get(semester.pk, [])
        payments = payments_by_semester.get(semester.pk, [])

        charged = sum((c.amount for c in charges), Decimal("0"))
        paid = sum((p.amount for p in payments), Decimal("0"))
        balance = charged - paid

        fee_structure = None
        if enrollment:
            fee_structure = fee_structures.get(
                (enrollment.program_id, enrollment.year_level, semester.pk)
            )
        fee_configured = bool(fee_structure and fee_structure.item_count)

        if balance > 0:
            state = "owing"
        elif balance < 0:
            state = "credit"
        elif charged > 0:
            state = "paid"
        elif enrollment and not fee_configured:
            state = "unset"
        elif enrollment:
            state = "nocharge"
        else:
            state = "off"

        row = {
            "semester": semester,
            "enrollment": enrollment,
            "year_level": enrollment.year_level if enrollment else None,
            "program": enrollment.program if enrollment else student.program,
            "charges": charges,
            "payments": payments,
            "charged": charged,
            "paid": paid,
            "balance": balance,
            "credit": -balance if balance < 0 else Decimal("0"),
            "fee_structure": fee_structure,
            "fee_configured": fee_configured,
            "is_current": semester.start_date <= today <= semester.end_date,
            "is_past": semester.end_date < today,
            "is_future": semester.start_date > today,
            "state": state,
        }
        rows_by_year[semester.academic_year_id].append(row)
        all_rows.append(row)

    marker_row = next((r for r in all_rows if r["is_current"]), None)
    if marker_row:
        marker_row["marker"] = "Now"
    else:
        marker_row = next((r for r in all_rows if r["is_future"]), None)
        if marker_row:
            marker_row["marker"] = "Next"

    # ---------------------------------------------------------
    # The line: one segment per year, one station per semester
    # ---------------------------------------------------------

    state_priority = ["owing", "unset", "credit", "paid", "nocharge"]
    line = []
    for year in years:
        rows = rows_by_year[year.pk]
        states = {r["state"] for r in rows}
        line.append({
            "year": year,
            "rows": rows,
            "is_selected": year == selected_year,
            "is_current": year == current_year,
            "is_future": year.start_date > today,
            "owed": sum(
                (r["balance"] for r in rows if r["balance"] > 0),
                Decimal("0"),
            ),
            "state": next(
                (s for s in state_priority if s in states), "off"
            ),
        })

    completion_year = None
    if student.intake_year and student.program.duration_years:
        try:
            completion_year = (
                int(student.intake_year.name[:4])
                + student.program.duration_years - 1
            )
        except ValueError:
            completion_year = None

    track_continues = bool(
        completion_year
        and years
        and completion_year > years[-1].start_date.year
    )
    for segment in line:
        segment["is_final"] = (
            completion_year is not None
            and segment["year"].start_date.year == completion_year
        )

    # ---------------------------------------------------------
    # Statement for the selected year
    # ---------------------------------------------------------

    statement_rows = [
        r for r in rows_by_year[selected_year.pk] if (
            r["enrollment"] or r["charged"] or r["paid"] or r["is_current"]
        )
    ] if selected_year else []

    year_charged = sum((r["charged"] for r in statement_rows), Decimal("0"))
    year_paid = sum((r["paid"] for r in statement_rows), Decimal("0"))
    year_balance = year_charged - year_paid
    year_has_unset = any(r["state"] == "unset" for r in statement_rows)
    selected_semester_count = (
        len(rows_by_year[selected_year.pk]) if selected_year else 0
    )

    open_row = next(
        (r for r in statement_rows if r["is_current"]),
        None,
    ) or next(
        (r for r in statement_rows if r["state"] in ("owing", "unset")),
        None,
    )
    if open_row:
        open_row["open"] = True

    # ---------------------------------------------------------
    # What needs doing, most urgent first
    # ---------------------------------------------------------

    actions = []

    owing_rows = [r for r in all_rows if r["state"] == "owing"]
    owing_rows.sort(key=lambda r: (r["is_future"], r["semester"].start_date))
    for r in owing_rows:
        actions.append({"kind": "owing", "row": r})

    for r in all_rows:
        if r["state"] == "unset" and not r["is_past"]:
            actions.append({"kind": "unset", "row": r})
    for r in all_rows:
        if r["state"] == "unset" and r["is_past"]:
            actions.append({"kind": "unset", "row": r})

    contact_fields = [
        ("student_phone", "student phone"),
        ("guardian_name", "guardian name"),
        ("guardian_phone", "guardian phone"),
        ("address", "home address"),
    ]
    missing_details = [
        label for field, label in contact_fields
        if not (getattr(student, field) or "").strip()
    ]
    if missing_details:
        actions.append({"kind": "details", "missing": missing_details})

    for r in all_rows:
        if r["state"] == "credit":
            actions.append({"kind": "credit", "row": r})

    total_owed = sum(
        (r["balance"] for r in all_rows if r["balance"] > 0), Decimal("0")
    )
    total_credit = sum(
        (-r["balance"] for r in all_rows if r["balance"] < 0), Decimal("0")
    )
    owing_count = len(owing_rows)

    status_logs = list(student.status_logs.all()[:12])

    # ---------------------------------------------------------
    # Render
    # ---------------------------------------------------------

    template = (
        "school/partials/_student_journey.html"
        if request.headers.get("HX-Request") == "true"
        else "school/student_detail.html"
    )

    return render(
        request,
        template,
        {
            "student": student,
            "today": today,
            "years": years,
            "selected_year": selected_year,
            "previous_year": previous_year,
            "next_year": next_year,
            "line": line,
            "completion_year": completion_year,
            "track_continues": track_continues,
            "statement_rows": statement_rows,
            "year_charged": year_charged,
            "year_paid": year_paid,
            "year_balance": year_balance,
            "year_has_unset": year_has_unset,
            "selected_semester_count": selected_semester_count,
            "actions": actions,
            "missing_details": missing_details,
            "total_owed": total_owed,
            "total_credit": total_credit,
            "owing_count": owing_count,
            "status_logs": status_logs,
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


# ============================================================
# STUDENT LIST - SEARCH (JSON)
# ============================================================

@permission_required("school.view_student", raise_exception=True)
def student_list_search(request):
    """Live search for student list - returns all students (any status) matching query."""
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


# ============================================================
# PAYMENTS
# ============================================================

def _payment_terms(student, today):
    """Return the student's semesters with charged/paid/balance, newest first.

    Four queries in total regardless of how many semesters the student has:
    enrollments, charges, payments, and the fee structures that decide whether
    a semester is billable. A semester with no fees, no charges and no payments
    is left out because there is nothing to pay towards yet.
    """
    enrollments = list(
        student.enrollments.select_related(
            "program", "semester", "semester__academic_year"
        ).order_by("-semester__academic_year__name", "-semester__number")
    )
    if not enrollments:
        return []

    semester_ids = [enrollment.semester_id for enrollment in enrollments]

    charged_by_semester = {
        row["enrollment__semester_id"]: row["total"]
        for row in StudentCharge.objects.filter(
            student=student,
            enrollment__semester_id__in=semester_ids,
        )
        .values("enrollment__semester_id")
        .annotate(total=Sum("amount"))
    }
    paid_by_semester = {
        row["semester_id"]: row["total"]
        for row in Payment.objects.filter(
            student=student,
            semester_id__in=semester_ids,
        )
        .values("semester_id")
        .annotate(total=Sum("amount"))
    }
    billed_terms = {
        (row["semester"], row["year_level"])
        for row in FeeStructure.objects.filter(
            semester_id__in=semester_ids,
            program=student.program,
            items__isnull=False,
        ).values("semester", "year_level").distinct()
    }

    rows = []
    for enrollment in enrollments:
        semester = enrollment.semester
        charged = charged_by_semester.get(semester.pk) or Decimal("0")
        paid = paid_by_semester.get(semester.pk) or Decimal("0")

        rows.append({
            "enrollment": enrollment,
            "semester": semester,
            "charged": charged,
            "paid": paid,
            "balance": charged - paid,
            "is_current": semester.start_date <= today <= semester.end_date,
            "is_upcoming": semester.start_date > today,
            "billable": bool(charged) or bool(paid) or (
                (semester.pk, enrollment.year_level) in billed_terms
            ),
        })

    return rows


@transaction.atomic
@permission_required("school.can_record_payments", raise_exception=True)
def payment_create(request):
    """Take one payment against one semester of one student.

    The page answers three questions in order: who is paying, which semester the
    money belongs to, and how much was handed over. Every figure comes from the
    same charge and payment aggregates the student statement uses, so the
    balance shown here matches the account it is paid into.
    """
    student_id = request.GET.get("student") or request.POST.get("student_id")
    selected_semester_id = (
        request.GET.get("semester")
        or request.POST.get("semester")
    )
    recorded_id = request.GET.get("recorded")
    today = get_current_date()

    student = None
    term_rows = []
    skipped_terms = 0
    selected_term = None

    if student_id:
        student = get_object_or_404(
            Student.objects.select_related("program", "intake_year"),
            pk=student_id,
            status=Student.ACTIVE,
        )

        all_terms = _payment_terms(student, today)
        term_rows = [row for row in all_terms if row["billable"]]
        skipped_terms = len(all_terms) - len(term_rows)

        if selected_semester_id:
            selected_term = next(
                (
                    row for row in term_rows
                    if str(row["semester"].pk) == str(selected_semester_id)
                ),
                None,
            )

        # A rejected POST keeps the operator's own choice; a fresh page opens
        # on the semester the student is actually in.
        if selected_term is None and request.method != "POST":
            selected_term = next(
                (row for row in term_rows if row["is_current"]), None
            ) or (term_rows[0] if term_rows else None)

    semester_queryset = (
        Semester.objects.filter(pk__in=[row["semester"].pk for row in term_rows])
        if term_rows
        else Semester.objects.none()
    )

    form = PaymentForm(request.POST or None, semester_queryset=semester_queryset)

    if request.method == "POST":
        if not student:
            messages.error(request, "Choose a student before recording a payment.")
        elif not form.is_valid():
            messages.error(
                request,
                "This payment was not recorded. Check the highlighted fields.",
            )
        else:
            payment = form.save(commit=False)
            payment.student = student
            payment.save()

            from school.utils.audit import log_action

            log_action(
                user=request.user,
                action="PAYMENT",
                student=student,
                summary=(
                    f"Payment of {payment.amount} recorded for "
                    f"{payment.semester} (receipt {payment.receipt_number})"
                ),
                details={
                    "receipt": payment.receipt_number,
                    "amount": str(payment.amount),
                    "semester": str(payment.semester),
                    "method": payment.get_method_display(),
                    "reference": payment.reference,
                },
                category="FINANCIAL",
            )

            messages.success(
                request,
                f"Receipt {payment.receipt_number} recorded for "
                f"{student.first_name} {student.last_name}.",
            )

            # Redirect after POST so a refresh cannot record the same money twice.
            query = urlencode({
                "student": student.pk,
                "semester": payment.semester_id,
                "recorded": payment.pk,
            })
            return redirect(f"{reverse('payment_create')}?{query}")

    # ---------------------------------------------------------
    # CONFIRMATION
    # ---------------------------------------------------------

    recorded_payment = None
    if recorded_id and student:
        recorded_payment = (
            Payment.objects
            .filter(pk=recorded_id, student=student)
            .select_related("semester", "semester__academic_year")
            .first()
        )

    if recorded_payment and selected_term is None:
        selected_term = next(
            (
                row for row in term_rows
                if row["semester"].pk == recorded_payment.semester_id
            ),
            None,
        )

    for row in term_rows:
        row["is_selected"] = bool(
            selected_term and row["semester"].pk == selected_term["semester"].pk
        )

    # ---------------------------------------------------------
    # ACCOUNT FIGURES
    # ---------------------------------------------------------

    account_charged = Decimal("0")
    account_paid = Decimal("0")

    if student:
        account_charged = (
            student.charges.aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        account_paid = (
            student.payments.aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

    return render(
        request,
        "school/payment_create.html",
        {
            "form": form,
            "student": student,
            "term_rows": term_rows,
            "selected_term": selected_term,
            "skipped_terms": skipped_terms,
            "recorded_payment": recorded_payment,
            "account_charged": account_charged,
            "account_paid": account_paid,
            "account_balance": account_charged - account_paid,
            "today": today,
            "next_receipt": next_receipt_number(today),
        },
    )


@permission_required("school.change_student", raise_exception=True)
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
                start_year_level=next_year_level,
                program=program
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
    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    context = {
        "page_obj": page_obj,
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

        def clean_password(self):
            from django.contrib.auth.password_validation import validate_password

            password = self.cleaned_data["password"]
            validate_password(password)
            return password
    
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


# ============================================================
# BACKUP & RESTORE (Superuser only)
# ============================================================

@user_passes_test(lambda u: u.is_superuser)
def backup_index(request):
    """List all backups with size and date."""
    config = BackupConfig.get_config()
    backup_dir = config.get_backup_path()
    backups = []

    if os.path.exists(backup_dir):
        for filename in sorted(os.listdir(backup_dir), reverse=True):
            filepath = os.path.join(backup_dir, filename)
            if os.path.isfile(filepath) and filename.endswith('.sqlite3'):
                stat = os.stat(filepath)
                backups.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime),
                })

    context = {
        'backups': backups,
        'config': config,
        'backup_available': config.is_backup_available(),
        'backup_path': backup_dir,
    }
    return render(request, "school/backup_index.html", context)


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def backup_create(request):
    """Create a new backup of the current database."""
    config = BackupConfig.get_config()
    db_path = settings.DATABASES['default']['NAME']
    backup_dir = config.get_backup_path()

    backup_name = timestamped_name("backup")

    try:
        create_backup(db_path, os.path.join(backup_dir, backup_name))
    except BackupError as exc:
        messages.error(request, f"Backup failed: {exc}")
    else:
        messages.success(
            request, f"Backup created and verified: {backup_name}"
        )

    return redirect('backup_index')


@user_passes_test(lambda u: u.is_superuser)
def backup_download(request, filename):
    """Download a backup file."""
    config = BackupConfig.get_config()
    backup_dir = config.get_backup_path()
    # Sanitize filename to prevent directory traversal
    filename = os.path.basename(filename)
    filepath = os.path.join(backup_dir, filename)
    
    if not os.path.exists(filepath):
        messages.error(request, "Backup file not found.")
        return redirect('backup_index')
    
    response = FileResponse(open(filepath, 'rb'), as_attachment=True, filename=filename)
    return response


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def backup_restore(request, filename):
    """Restore a backup, creating a safety backup first."""
    config = BackupConfig.get_config()
    db_path = settings.DATABASES['default']['NAME']
    backup_dir = config.get_backup_path()

    # Sanitize filename
    filename = os.path.basename(filename)
    backup_path = os.path.join(backup_dir, filename)

    if not os.path.exists(backup_path):
        messages.error(request, "Backup file not found.")
        return redirect('backup_index')

    try:
        safety_path = restore_backup(backup_path, db_path)
    except BackupError as exc:
        messages.error(request, f"Restore failed: {exc}")
    else:
        safety_name = os.path.basename(safety_path) if safety_path else "none"
        messages.success(
            request,
            f"Database restored from {filename} and verified. "
            f"Safety backup: {safety_name}.",
        )

    return redirect('backup_index')


@user_passes_test(lambda u: u.is_superuser)
def backup_upload(request):
    """Upload a backup file from local machine."""
    if request.method != 'POST':
        return redirect('backup_index')
    
    config = BackupConfig.get_config()
    backup_dir = config.get_backup_path()
    
    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir, exist_ok=True)
        except Exception as e:
            messages.error(request, f"Cannot create backup directory: {e}")
            return redirect('backup_index')
    
    uploaded_file = request.FILES.get('backup_file')
    if not uploaded_file:
        messages.error(request, "No file selected.")
        return redirect('backup_index')
    
    # Validate file extension
    allowed_extensions = ('.sqlite3', '.db')
    if not uploaded_file.name.endswith(allowed_extensions):
        messages.error(request, "Invalid file type. Only .sqlite3 or .db files are allowed.")
        return redirect('backup_index')
    
    # Sanitize filename
    original_name = os.path.basename(uploaded_file.name)
    # Replace any problematic characters
    safe_name = "".join(c for c in original_name if c.isalnum() or c in ('-', '_', '.')).rstrip()
    if not safe_name:
        safe_name = f"uploaded_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    
    # Ensure it has the right extension
    if not safe_name.endswith(allowed_extensions):
        safe_name += '.sqlite3'
    
    backup_path = os.path.join(backup_dir, safe_name)
    
    # Handle duplicate names
    counter = 1
    base_name, ext = os.path.splitext(safe_name)
    while os.path.exists(backup_path):
        safe_name = f"{base_name}_{counter}{ext}"
        backup_path = os.path.join(backup_dir, safe_name)
        counter += 1
    
    try:
        with open(backup_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        ok, message = verify_backup(backup_path)
        if not ok:
            os.remove(backup_path)
            messages.error(request, f"Uploaded file rejected: {message}")
            return redirect('backup_index')

        messages.success(request, f"Backup uploaded and verified: {safe_name}")
    except Exception as e:
        messages.error(request, f"Upload failed: {e}")
    
    return redirect('backup_index')


from django import forms

class BackupSettingsForm(forms.ModelForm):
    class Meta:
        model = BackupConfig
        fields = ['backup_path', 'auto_backup_enabled', 'retention_days', 'strict_mode']
        widgets = {
            'backup_path': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '/path/to/backup'}),
            'retention_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'auto_backup_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'strict_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


@user_passes_test(lambda u: u.is_superuser)
def backup_settings(request):
    """View to update backup configuration."""
    config = BackupConfig.get_config()

    if request.method == 'POST':
        form = BackupSettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Backup settings updated.")
            return redirect('backup_settings')
    else:
        form = BackupSettingsForm(instance=config)

    return render(request, 'school/backup_settings.html', {
        'form': form,
        'config': config,
        'backup_available': config.is_backup_available(),
    })