import json
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.core import signing
from django.core.signing import BadSignature
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .forms import (
    AcademicYearForm,
    BulkFeeForm,
    FeeStructureForm,
    FeeStructureItemForm,
    PaymentForm,
    ProgramForm,
    SemesterForm,
    StudentImportForm,
    StudentForm,
    StudentStatusChangeForm,
)
from school.utils.backups import (
    BackupError,
    create_backup,
    restore_backup,
    timestamped_name,
    verify_backup,
)

from .models import (
    AcademicYear,
    AuditLog,
    BackupConfig,
    Enrollment,
    FeeStructure,
    FeeStructureItem,
    Payment,
    Program,
    Semester,
    Student,
    StudentCharge,
    StudentStatusLog,
    TimeOverride,
    semester_financials,
    student_balance,
    outstanding_students,
    payment_methods_breakdown,
    program_revenue,
    daily_collections,
    enrollment_summary,
    student_status_history,
    students_with_missing_details,
    unconfigured_fee_structures,
)
from .utils.time_utils import get_current_date, get_working_semester
from .views import cancel_unpaid_future_charges, create_academic_year_enrollments
from .reports import REPORTS


def _parse_json_body(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
            return body if isinstance(body, dict) else {}
        except (TypeError, ValueError):
            return {}
    return request.POST.copy() if hasattr(request, "POST") else {}


def _auth_user_payload(user):
    permission_codes = (
        "view_student",
        "add_student",
        "change_student",
        "view_studentstatuslog",
        "can_view_financial_reports",
        "can_view_outstanding_reports",
        "can_record_payments",
        "view_academicyear",
        "view_semester",
        "view_feestructure",
        "add_feestructure",
        "view_program",
        "view_auditlog",
    )
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "permissions": {
            code: user.has_perm(f"school.{code}") for code in permission_codes
        },
    }


def _student_payload(student):
    current_enrollment = student.get_current_enrollment()
    return {
        "id": student.id,
        "student_number": student.student_number,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "name": f"{student.first_name} {student.last_name}".strip(),
        "status": student.status,
        "status_display": student.get_status_display(),
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "gender": student.gender,
        "guardian_name": student.guardian_name,
        "guardian_phone": student.guardian_phone,
        "student_phone": student.student_phone,
        "address": student.address,
        "national_id": student.national_id,
        "program": {
            "id": student.program.id,
            "name": student.program.name,
            "code": student.program.code,
        } if student.program else None,
        "intake_year": student.intake_year.name if student.intake_year else None,
        "intake_year_id": student.intake_year_id,
        "current_semester": str(current_enrollment.semester) if current_enrollment else None,
        "current_year_level": current_enrollment.year_level if current_enrollment else None,
        "enrollments": [
            {
                "id": enrollment.id,
                "semester": str(enrollment.semester),
                "year_level": enrollment.year_level,
                "status": enrollment.status,
                "program": enrollment.program.name if enrollment.program else None,
            }
            for enrollment in student.enrollments.select_related("semester", "semester__academic_year", "program")
        ],
    }


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_dashboard(request):
    """Return the permission-aware dashboard summary used by Nuxt."""
    today = get_current_date()
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
    ).first()
    financial_semester = get_working_semester(today)
    financial_year = (
        financial_semester.academic_year if financial_semester else current_year
    )
    total_students = Student.objects.filter(status=Student.ACTIVE).count()
    can_view_financials = (
        request.user.has_perm("school.can_view_financial_reports")
        or request.user.has_perm("school.can_record_payments")
    )
    can_view_outstanding = request.user.has_perm(
        "school.can_view_outstanding_reports"
    )
    today_payments = {"total": 0, "count": 0}
    recent_payments = []
    financials = None

    if can_view_financials:
        today_payments = Payment.objects.filter(payment_date=today).aggregate(
            total=Sum("amount"),
            count=Count("pk"),
        )
        today_payments["total"] = today_payments["total"] or 0
        if financial_semester:
            semester_totals = semester_financials(financial_semester)
            expected_revenue = StudentCharge.objects.filter(
                enrollment__semester__academic_year=financial_year,
                enrollment__status=Enrollment.ACTIVE,
            ).aggregate(total=Sum("amount"))["total"] or 0
            financials = {
                "charged": float(semester_totals["charged"]),
                "paid": float(semester_totals["paid"]),
                "outstanding": float(semester_totals["outstanding"]),
                "collection_rate": float(semester_totals["collection_rate"]),
                "expected_revenue_year": float(expected_revenue),
            }

        recent_payments = [
            {
                "id": payment.id,
                "student_id": payment.student_id,
                "student_name": (
                    f"{payment.student.first_name} {payment.student.last_name}".strip()
                ),
                "student_number": payment.student.student_number,
                "program": payment.student.program.name if payment.student.program else "",
                "method": payment.get_method_display(),
                "payment_date": payment.payment_date.isoformat(),
                "amount": float(payment.amount),
                "student_active": payment.student.status == Student.ACTIVE,
            }
            for payment in Payment.objects.select_related(
                "student__program"
            ).order_by("-payment_date", "-id")[:8]
        ]

    outstanding_summary = None
    if can_view_outstanding and financial_semester:
        balances = outstanding_students(financial_semester)
        balance_totals = balances.aggregate(
            total=Sum("balance"),
            count=Count("pk"),
        )
        top_balances = list(balances.select_related("program")[:5])
        max_balance = top_balances[0].balance if top_balances else 0
        outstanding_summary = {
            "total": float(balance_totals["total"] or 0),
            "students_count": balance_totals["count"],
            "has_charges": bool(balance_totals["count"]) or StudentCharge.objects.filter(
                enrollment__semester=financial_semester,
            ).exists(),
            "students": [
                {
                    "id": student.id,
                    "name": f"{student.first_name} {student.last_name}".strip(),
                    "student_number": student.student_number,
                    "program": student.program.name if student.program else "",
                    "balance": float(student.balance),
                    "balance_percent": (
                        float(student.balance * 100 / max_balance) if max_balance else 0
                    ),
                }
                for student in top_balances
            ],
        }

    semester_payload = None
    if financial_semester:
        elapsed = (today - financial_semester.start_date).days
        duration = (financial_semester.end_date - financial_semester.start_date).days
        semester_payload = {
            "name": str(financial_semester),
            "academic_year": financial_semester.academic_year.name,
            "number": financial_semester.number,
            "start_date": financial_semester.start_date.isoformat(),
            "end_date": financial_semester.end_date.isoformat(),
            "is_upcoming": financial_semester.start_date > today,
            "days_until": max(0, -elapsed),
            "week": min((duration + 7) // 7, elapsed // 7 + 1) if elapsed >= 0 else 0,
            "weeks": (duration + 7) // 7,
            "progress_percent": max(0, min(100, elapsed * 100 / max(1, duration))),
        }

    payload = {
        "total_students": total_students,
        "today": today.isoformat(),
        "current_year": current_year.name if current_year else None,
        "current_semester": semester_payload["name"] if semester_payload else None,
        "semester": semester_payload,
        "can_view_financials": can_view_financials,
        "can_view_outstanding": can_view_outstanding,
        "today_total": float(today_payments["total"]),
        "today_count": today_payments["count"],
        "financials": financials,
        "recent_payments": recent_payments,
        "outstanding": outstanding_summary,
    }
    return JsonResponse(payload)


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_program_list(request):
    programs = Program.objects.filter(active=True).order_by("name")
    return JsonResponse({
        "count": programs.count(),
        "results": [
            {"id": program.id, "name": program.name, "code": program.code, "duration_years": program.duration_years}
            for program in programs
        ],
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_academic_year_list(request):
    years = AcademicYear.objects.order_by("-name")
    return JsonResponse({
        "count": years.count(),
        "results": [{
            "id": year.id,
            "name": year.name,
            "start_date": year.start_date.isoformat() if year.start_date else None,
            "end_date": year.end_date.isoformat() if year.end_date else None,
            "is_current": year.is_current,
        } for year in years],
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_semester_list(request):
    semesters = Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number")
    return JsonResponse({
        "count": semesters.count(),
        "results": [{
            "id": semester.id,
            "name": str(semester),
            "academic_year": semester.academic_year.name,
            "academic_year_id": semester.academic_year_id,
            "number": semester.number,
            "start_date": semester.start_date.isoformat() if semester.start_date else None,
            "end_date": semester.end_date.isoformat() if semester.end_date else None,
            "status": semester.status,
        } for semester in semesters],
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_academic_year_detail(request, pk):
    year = get_object_or_404(AcademicYear, pk=pk)
    return JsonResponse({
        "id": year.id,
        "name": year.name,
        "start_date": year.start_date.isoformat() if year.start_date else None,
        "end_date": year.end_date.isoformat() if year.end_date else None,
        "is_current": year.is_current,
    })


@login_required
@permission_required("school.add_academicyear", raise_exception=True)
def api_academic_year_create(request):
    payload = _parse_json_body(request)
    form = AcademicYearForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    year = form.save()
    return JsonResponse({
        "id": year.id,
        "name": year.name,
        "start_date": year.start_date.isoformat() if year.start_date else None,
        "end_date": year.end_date.isoformat() if year.end_date else None,
        "is_current": year.is_current,
    }, status=201)


@login_required
@permission_required("school.change_academicyear", raise_exception=True)
def api_academic_year_update(request, pk):
    year = get_object_or_404(AcademicYear, pk=pk)
    payload = _parse_json_body(request)
    form = AcademicYearForm(payload, instance=year)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    year = form.save()
    return JsonResponse({
        "id": year.id,
        "name": year.name,
        "start_date": year.start_date.isoformat() if year.start_date else None,
        "end_date": year.end_date.isoformat() if year.end_date else None,
        "is_current": year.is_current,
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_program_detail(request, pk):
    program = get_object_or_404(Program, pk=pk)
    return JsonResponse({
        "id": program.id,
        "code": program.code,
        "name": program.name,
        "description": program.description,
        "duration_years": program.duration_years,
        "category": program.category,
        "active": program.active,
    })


@login_required
@permission_required("school.add_program", raise_exception=True)
def api_program_create(request):
    payload = _parse_json_body(request)
    form = ProgramForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    program = form.save()
    return JsonResponse({
        "id": program.id,
        "code": program.code,
        "name": program.name,
        "description": program.description,
        "duration_years": program.duration_years,
        "category": program.category,
        "active": program.active,
    }, status=201)


@login_required
@permission_required("school.change_program", raise_exception=True)
def api_program_update(request, pk):
    program = get_object_or_404(Program, pk=pk)
    payload = _parse_json_body(request)
    form = ProgramForm(payload, instance=program)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    program = form.save()
    return JsonResponse({
        "id": program.id,
        "code": program.code,
        "name": program.name,
        "description": program.description,
        "duration_years": program.duration_years,
        "category": program.category,
        "active": program.active,
    })


@login_required
@permission_required("school.view_semester", raise_exception=True)
def api_semester_detail(request, pk):
    semester = get_object_or_404(Semester.objects.select_related("academic_year"), pk=pk)
    return JsonResponse({
        "id": semester.id,
        "name": str(semester),
        "academic_year_id": semester.academic_year_id,
        "academic_year": semester.academic_year.name,
        "number": semester.number,
        "start_date": semester.start_date.isoformat() if semester.start_date else None,
        "end_date": semester.end_date.isoformat() if semester.end_date else None,
        "status": semester.status,
    })


@login_required
@permission_required("school.add_semester", raise_exception=True)
def api_semester_create(request):
    payload = _parse_json_body(request)
    form = SemesterForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    semester = form.save()
    return JsonResponse({
        "id": semester.id,
        "name": str(semester),
        "academic_year_id": semester.academic_year_id,
        "academic_year": semester.academic_year.name,
        "number": semester.number,
        "start_date": semester.start_date.isoformat() if semester.start_date else None,
        "end_date": semester.end_date.isoformat() if semester.end_date else None,
        "status": semester.status,
    }, status=201)


@login_required
@permission_required("school.change_semester", raise_exception=True)
def api_semester_update(request, pk):
    semester = get_object_or_404(Semester, pk=pk)
    payload = _parse_json_body(request)
    form = SemesterForm(payload, instance=semester)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    semester = form.save()
    return JsonResponse({
        "id": semester.id,
        "name": str(semester),
        "academic_year_id": semester.academic_year_id,
        "academic_year": semester.academic_year.name,
        "number": semester.number,
        "start_date": semester.start_date.isoformat() if semester.start_date else None,
        "end_date": semester.end_date.isoformat() if semester.end_date else None,
        "status": semester.status,
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_student_list(request):
    query = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    program_filter = request.GET.get("program")
    year_level_filter = request.GET.get("year_level")
    page_number = request.GET.get("page", "1")

    students = Student.objects.select_related("program", "intake_year")

    if query:
        students = students.filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    if program_filter:
        if program_filter.isdecimal():
            students = students.filter(program_id=program_filter)
        else:
            students = students.none()

    if year_level_filter:
        students = students.filter(
            enrollments__status=Enrollment.ACTIVE,
            enrollments__semester__end_date__gte=get_current_date(),
            enrollments__year_level=year_level_filter,
        ).distinct()

    if status_filter in ["all", ""]:
        if not status_filter:
            students = students.filter(status__in=[Student.ACTIVE, Student.DEFERRED])
    else:
        students = students.filter(status=status_filter.upper())

    students = students.order_by("last_name", "first_name")
    paginator = Paginator(students, 20)
    page_obj = paginator.get_page(page_number)

    items = []
    for student in page_obj.object_list:
        current_enrollment = student.get_current_enrollment()
        items.append(
            {
                "id": student.id,
                "student_number": student.student_number,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "name": f"{student.first_name} {student.last_name}".strip(),
                "status": student.status,
                "status_display": student.get_status_display(),
                "program": student.program.name if student.program else None,
                "program_code": student.program.code if student.program else None,
                "intake_year": student.intake_year.name if student.intake_year else None,
                "current_semester": str(current_enrollment.semester) if current_enrollment else None,
            }
        )

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": items,
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_student_search(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"students": []})

    students = (
        Student.objects.filter(status=Student.ACTIVE)
        .filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .order_by("last_name", "first_name")[:8]
    )
    return JsonResponse({
        "students": [
            {
                "id": student.id,
                "student_number": student.student_number,
                "first_name": student.first_name,
                "last_name": student.last_name,
            }
            for student in students
        ],
    })


@login_required
@permission_required("school.view_feestructure", raise_exception=True)
def api_fee_structure_list(request, semester_id):
    semester = get_object_or_404(Semester.objects.select_related("academic_year"), pk=semester_id)
    fee_structures = FeeStructure.objects.filter(semester=semester).select_related("program").prefetch_related("items").order_by("program__name", "year_level")

    results = []
    for fee_structure in fee_structures:
        results.append({
            "id": fee_structure.id,
            "program": {
                "id": fee_structure.program_id,
                "name": fee_structure.program.name,
                "code": fee_structure.program.code,
            },
            "year_level": fee_structure.year_level,
            "semester": {
                "id": semester.id,
                "name": str(semester),
            },
            "total": sum((item.amount for item in fee_structure.items.all()), Decimal("0")),
            "items": [{
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "amount": float(item.amount),
            } for item in fee_structure.items.all()],
        })

    return JsonResponse({
        "semester": {
            "id": semester.id,
            "name": str(semester),
            "number": semester.number,
            "academic_year": semester.academic_year.name,
        },
        "count": len(results),
        "results": results,
    })


@login_required
@permission_required("school.add_feestructure", raise_exception=True)
def api_fee_structure_create(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)
    payload = _parse_json_body(request)
    form = FeeStructureForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    fee_structure = form.save(commit=False)
    fee_structure.semester = semester
    fee_structure.save()

    items = payload.get("items") or []
    for item in items:
        form_item = FeeStructureItemForm(item)
        if not form_item.is_valid():
            return JsonResponse({"errors": {"items": form_item.errors.get_json_data()}}, status=400)
        FeeStructureItem.objects.create(
            fee_structure=fee_structure,
            name=form_item.cleaned_data["name"],
            description=form_item.cleaned_data.get("description", ""),
            amount=form_item.cleaned_data["amount"],
        )

    return JsonResponse({
        "id": fee_structure.id,
        "program_id": fee_structure.program_id,
        "year_level": fee_structure.year_level,
        "semester_id": fee_structure.semester_id,
    }, status=201)


@login_required
@permission_required("school.change_feestructure", raise_exception=True)
def api_fee_structure_update(request, pk):
    fee_structure = get_object_or_404(FeeStructure.objects.select_related("semester", "program"), pk=pk)
    payload = _parse_json_body(request)
    form = FeeStructureForm(payload, instance=fee_structure)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    fee_structure = form.save()

    items = payload.get("items") or []
    existing_items = {item.id: item for item in fee_structure.items.all()}
    for item in items:
        item_id = item.get("id")
        if item_id and item_id in existing_items:
            target = existing_items[item_id]
            target.name = item.get("name", target.name)
            target.description = item.get("description", target.description)
            target.amount = item.get("amount", target.amount)
            target.save()
        else:
            FeeStructureItem.objects.create(
                fee_structure=fee_structure,
                name=item["name"],
                description=item.get("description", ""),
                amount=item["amount"],
            )

    deleted_ids = payload.get("delete_item_ids") or []
    if deleted_ids:
        fee_structure.items.filter(id__in=deleted_ids).delete()

    return JsonResponse({
        "id": fee_structure.id,
        "program_id": fee_structure.program_id,
        "year_level": fee_structure.year_level,
        "semester_id": fee_structure.semester_id,
    })


@login_required
@permission_required("school.add_feestructure", raise_exception=True)
def api_bulk_fee_configuration(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)
    payload = _parse_json_body(request)
    form = BulkFeeForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    programs = form.cleaned_data["programs"]
    year_levels = [int(value) for value in form.cleaned_data["year_levels"]]
    fee_name = form.cleaned_data["fee_name"]
    amount = form.cleaned_data["amount"]
    description = form.cleaned_data["description"]

    created_count = updated_count = skipped_count = charges_created = 0
    for program in programs:
        for year_level in year_levels:
            if year_level > program.duration_years:
                skipped_count += 1
                continue

            fee_structure, _ = FeeStructure.objects.get_or_create(
                program=program,
                year_level=year_level,
                semester=semester,
            )
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
                fee_item.amount = amount
                fee_item.description = description
                fee_item.save(update_fields=["amount", "description"])
                updated_count += 1

            matching_enrollments = Enrollment.objects.filter(
                program=program,
                year_level=year_level,
                semester=semester,
                student__status=Student.ACTIVE,
            )
            for enrollment in matching_enrollments:
                _, charge_created = StudentCharge.objects.get_or_create(
                    student=enrollment.student,
                    enrollment=enrollment,
                    fee_item=fee_item,
                    defaults={"amount": fee_item.amount},
                )
                if charge_created:
                    charges_created += 1

    return JsonResponse({
        "semester_id": semester.id,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "charges_created": charges_created,
    })


@login_required
@permission_required("school.add_student", raise_exception=True)
def api_student_create(request):
    payload = _parse_json_body(request)
    form = StudentForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    semester_id = payload.get("semester") or request.POST.get("semester")
    year_level = payload.get("year_level") or request.POST.get("year_level")

    if not semester_id:
        return JsonResponse({"errors": {"semester": ["Please select a starting semester."]}}, status=400)
    if not year_level:
        return JsonResponse({"errors": {"year_level": ["Please select a starting year level."]}}, status=400)

    try:
        semester = Semester.objects.get(pk=semester_id)
        year_level = int(year_level)
    except (Semester.DoesNotExist, ValueError):
        return JsonResponse({"errors": {"semester": ["Selected semester or year level is invalid."]}}, status=400)

    program = form.instance.program
    if year_level > program.duration_years:
        return JsonResponse({"errors": {"year_level": [f"{program} only runs for {program.duration_years} year(s)."]}}, status=400)

    with transaction.atomic():
        student = form.save()
        enrollment = Enrollment.objects.create(
            student=student,
            program=program,
            semester=semester,
            year_level=year_level,
            status=Enrollment.ACTIVE,
        )
        create_academic_year_enrollments(
            student=student,
            start_semester=semester,
            start_year_level=year_level,
            program=program,
        )
        StudentStatusLog.objects.create(
            student=student,
            status=Student.ACTIVE,
            note="Initial registration.",
        )

    payload_data = _student_payload(student)
    payload_data["enrollment_id"] = enrollment.id
    return JsonResponse(payload_data, status=201)


@login_required
@permission_required("school.add_student", raise_exception=True)
@require_POST
def api_student_import_preview(request):
    from school.utils.student_import import parse_student_spreadsheet, validate_rows

    form = StudentImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({
            "errors": form.errors.get_json_data(),
        }, status=400)

    try:
        parsed_rows = parse_student_spreadsheet(form.cleaned_data["file"])
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    if not parsed_rows:
        return JsonResponse({"detail": "No student rows were found in that file."}, status=400)

    validated_rows = validate_rows(parsed_rows)
    intake_year = form.cleaned_data["intake_year"]
    semester = form.cleaned_data["semester"]
    year_level = int(form.cleaned_data["year_level"])
    default_status = form.cleaned_data["default_status"]
    for row in validated_rows:
        if row["program"] and year_level > row["program"].duration_years:
            row["errors"].append(
                f"{row['program']} only runs for {row['program'].duration_years} year(s)."
            )

    valid_rows = [
        {
            "row_number": row["row_number"],
            "student_number": row["student_number"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "program_id": row["program"].id,
            "program_code": row["program_code"],
            "program_name": row["program"].name,
        }
        for row in validated_rows
        if not row["errors"]
    ]
    invalid_rows = [
        {
            "row_number": row["row_number"],
            "student_number": row["student_number"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "program_code": row["program_code"],
            "errors": row["errors"],
        }
        for row in validated_rows
        if row["errors"]
    ]
    token = signing.dumps({
        "rows": valid_rows,
        "intake_year_id": intake_year.id,
        "semester_id": semester.id,
        "year_level": year_level,
        "default_status": default_status,
    }, compress=True)

    return JsonResponse({
        "preview_id": token,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "valid_count": len(valid_rows),
        "invalid_count": len(invalid_rows),
        "intake_year": intake_year.name,
        "semester": str(semester),
        "year_level": year_level,
        "default_status": default_status,
    })


@login_required
@permission_required("school.add_student", raise_exception=True)
@require_POST
def api_student_import_confirm(request):
    payload = _parse_json_body(request)
    preview_id = payload.get("preview_id")
    if not isinstance(preview_id, str) or not preview_id:
        return JsonResponse({"detail": "Import preview is missing. Upload the spreadsheet again."}, status=400)

    try:
        preview = signing.loads(preview_id, max_age=3600)
    except BadSignature:
        return JsonResponse({"detail": "Import preview expired or is invalid. Upload the spreadsheet again."}, status=400)

    if not isinstance(preview, dict) or not isinstance(preview.get("rows"), list):
        return JsonResponse({"detail": "Import preview is invalid. Upload the spreadsheet again."}, status=400)

    intake_year = AcademicYear.objects.filter(pk=preview.get("intake_year_id")).first()
    semester = Semester.objects.filter(
        pk=preview.get("semester_id"),
        academic_year_id=preview.get("intake_year_id"),
    ).first()
    try:
        year_level = int(preview.get("year_level"))
    except (TypeError, ValueError):
        year_level = 0
    status = preview.get("default_status")
    if (
        not intake_year
        or not semester
        or year_level < 1
        or status not in dict(Student.STATUS_CHOICES)
    ):
        return JsonResponse({"detail": "Import settings are no longer valid. Upload the spreadsheet again."}, status=400)

    from school.utils.student_import import validate_rows

    validated_rows = validate_rows(preview["rows"])
    invalid_rows = [
        row for row in validated_rows
        if any(
            not error.startswith(f"Student number '{row.get('student_number', '')}' already exists.")
            for error in row["errors"]
        )
        or not row.get("program")
        or year_level > row["program"].duration_years
    ]
    if invalid_rows:
        return JsonResponse({
            "detail": "Some preview rows are no longer valid. Upload the spreadsheet again.",
        }, status=400)

    created_count = 0
    skipped = []

    with transaction.atomic():
        for row in validated_rows:
            student_number = row.get("student_number", "")
            if Student.objects.filter(student_number=student_number).exists():
                skipped.append(student_number or "?")
                continue
            program = row.get("program")

            student = Student.objects.create(
                student_number=student_number,
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
            action="OTHER",
            summary=f"Bulk-imported {created_count} student(s) from spreadsheet",
            details={
                "count": created_count,
                "intake_year": intake_year.name,
                "semester": str(semester),
                "skipped": skipped,
            },
            category="STUDENT",
        )

    return JsonResponse({
        "created_count": created_count,
        "skipped": skipped,
        "skipped_count": len(skipped),
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("program", "intake_year"), pk=pk)
    return JsonResponse(_student_payload(student))


@login_required
@permission_required("school.change_student", raise_exception=True)
def api_student_patch(request, pk):
    student = get_object_or_404(Student, pk=pk)
    payload = _parse_json_body(request)

    if not payload:
        return JsonResponse({"errors": {"detail": ["No update data was provided."]}}, status=400)

    current_values = {
        "student_number": student.student_number,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "national_id": student.national_id,
        "date_of_birth": student.date_of_birth,
        "gender": student.gender,
        "guardian_name": student.guardian_name,
        "guardian_phone": student.guardian_phone,
        "student_phone": student.student_phone,
        "address": student.address,
        "program": student.program_id,
        "intake_year": student.intake_year_id,
        "status": student.status,
    }
    merged = {**current_values, **payload}
    form = StudentForm(merged, instance=student)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    student = form.save()
    return JsonResponse(_student_payload(student))


@login_required
@permission_required("school.change_student", raise_exception=True)
def api_student_status_change(request, pk):
    student = get_object_or_404(Student, pk=pk)
    payload = _parse_json_body(request)
    form = StudentStatusChangeForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    old_status = student.status
    new_status = form.cleaned_data["status"]
    student.status = new_status
    student.save(update_fields=["status"])

    if new_status == Student.WITHDRAWN:
        cancel_unpaid_future_charges(student, user=request.user)

    StudentStatusLog.objects.create(
        student=student,
        status=new_status,
        note=form.cleaned_data["note"],
    )

    return JsonResponse({
        "id": student.id,
        "status": student.status,
        "status_display": student.get_status_display(),
        "old_status": old_status,
        "note": form.cleaned_data["note"],
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_archive_list(request):
    query = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip().upper()
    program_filter = (request.GET.get("program") or "").strip()
    intake_filter = (request.GET.get("intake") or "").strip()
    students = Student.objects.select_related("program", "intake_year")

    if status_filter in {value for value, _ in Student.STATUS_CHOICES}:
        students = students.filter(status=status_filter)
    if query:
        students = students.filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if program_filter:
        if program_filter.isdecimal():
            students = students.filter(program_id=program_filter)
        else:
            students = students.none()
    if intake_filter:
        students = students.filter(intake_year__name=intake_filter)

    students = students.order_by("last_name", "first_name")
    status_counts = {
        row["status"]: row["count"]
        for row in Student.objects.values("status").annotate(count=Count("id"))
    }
    paginator = Paginator(students, 20)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    return JsonResponse({
        "count": paginator.count,
        "total": sum(status_counts.values()),
        "status_counts": {
            value: status_counts.get(value, 0)
            for value, _ in Student.STATUS_CHOICES
        },
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "programs": [
            {"id": program.id, "name": program.name, "count": program.student_count}
            for program in Program.objects.filter(students__isnull=False)
            .annotate(student_count=Count("students"))
            .order_by("name")
        ],
        "intake_years": list(
            AcademicYear.objects.filter(students__isnull=False)
            .values_list("name", flat=True)
            .distinct()
            .order_by("-name")
        ),
        "results": [
            {
                "id": student.id,
                "student_number": student.student_number,
                "name": f"{student.first_name} {student.last_name}".strip(),
                "status": student.status,
                "status_display": student.get_status_display(),
                "program": student.program.name if student.program else None,
                "intake_year": student.intake_year.name if student.intake_year else None,
            }
            for student in page_obj.object_list
        ],
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_archive_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("program", "intake_year"), pk=pk)
    return JsonResponse(_student_payload(student))


# ============================================================
# PAYMENTS API
# ============================================================

@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_payment_list(request):
    """List payments with optional filters and pagination."""
    student_id = request.GET.get("student")
    semester_id = request.GET.get("semester")
    method = request.GET.get("method")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    page_number = request.GET.get("page", "1")

    payments = Payment.objects.select_related("student", "semester", "semester__academic_year")

    if student_id:
        payments = payments.filter(student_id=student_id)

    if semester_id:
        payments = payments.filter(semester_id=semester_id)

    if method:
        payments = payments.filter(method=method)

    if date_from:
        payments = payments.filter(payment_date__gte=date_from)

    if date_to:
        payments = payments.filter(payment_date__lte=date_to)

    payments = payments.order_by("-payment_date", "-id")
    paginator = Paginator(payments, 20)
    page_obj = paginator.get_page(page_number)

    results = []
    for payment in page_obj.object_list:
        results.append({
            "id": payment.id,
            "receipt_number": payment.receipt_number,
            "student": {
                "id": payment.student.id,
                "student_number": payment.student.student_number,
                "name": f"{payment.student.first_name} {payment.student.last_name}",
            },
            "semester": {
                "id": payment.semester.id,
                "name": str(payment.semester),
                "academic_year": payment.semester.academic_year.name,
            },
            "amount": float(payment.amount),
            "payment_date": payment.payment_date.isoformat(),
            "method": payment.method,
            "method_display": payment.get_method_display(),
            "reference": payment.reference,
            "notes": payment.notes,
            "created_at": payment.created_at.isoformat(),
        })

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
    })


@login_required
@permission_required("school.can_record_payments", raise_exception=True)
def api_payment_create(request):
    """Record a new payment."""
    if request.method != "POST":
        return JsonResponse({"errors": {"detail": ["Only POST method is allowed."]}}, status=405)

    payload = _parse_json_body(request)

    # Validate required fields
    student_id = payload.get("student")
    semester_id = payload.get("semester")
    amount = payload.get("amount")
    payment_date = payload.get("payment_date")
    method = payload.get("method", Payment.CASH)

    errors = {}
    if not student_id:
        errors["student"] = ["Student is required."]
    if not semester_id:
        errors["semester"] = ["Semester is required."]
    if not amount:
        errors["amount"] = ["Amount is required."]
    if not payment_date:
        errors["payment_date"] = ["Payment date is required."]

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        student = Student.objects.get(pk=student_id)
        semester = Semester.objects.get(pk=semester_id)
        amount = Decimal(str(amount))
        parsed_date = parse_date(str(payment_date))
        if parsed_date is None:
            return JsonResponse(
                {"errors": {"payment_date": ["Invalid payment date."]}}, status=400
            )
        payment_date = parsed_date
    except Student.DoesNotExist:
        return JsonResponse({"errors": {"student": ["Student not found."]}}, status=400)
    except Semester.DoesNotExist:
        return JsonResponse({"errors": {"semester": ["Semester not found."]}}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"errors": {"amount": ["Invalid amount."]}}, status=400)

    # Validate student is active
    if student.status != Student.ACTIVE:
        return JsonResponse({"errors": {"student": ["Student must be active to record payments."]}}, status=400)

    # Validate amount is positive
    if amount <= 0:
        return JsonResponse({"errors": {"amount": ["Amount must be greater than zero."]}}, status=400)

    # Validate payment method
    valid_methods = [choice[0] for choice in Payment.PAYMENT_METHODS]
    if method not in valid_methods:
        return JsonResponse({"errors": {"method": ["Invalid payment method."]}}, status=400)

    # Validate student has enrollment in the semester
    enrollment = Enrollment.objects.filter(
        student=student,
        semester=semester,
        status=Enrollment.ACTIVE,
    ).first()

    if not enrollment:
        return JsonResponse({"errors": {"semester": ["Student is not actively enrolled in this semester."]}}, status=400)

    with transaction.atomic():
        payment = Payment.objects.create(
            student=student,
            semester=semester,
            amount=amount,
            payment_date=payment_date,
            method=method,
            reference=payload.get("reference", ""),
            notes=payload.get("notes", ""),
            # An empty value makes the model allocate the next receipt number.
            receipt_number=(payload.get("receipt_number") or "").strip(),
        )

        # Audit log
        from school.utils.audit import log_action
        log_action(
            user=request.user,
            action="PAYMENT",
            student=student,
            summary=f"Payment of {payment.amount} recorded for {payment.semester}",
            details={
                "receipt": payment.receipt_number,
                "amount": str(payment.amount),
                "semester": str(payment.semester),
                "method": payment.get_method_display(),
                "reference": payment.reference,
            },
            category="FINANCIAL",
        )

    return JsonResponse({
        "id": payment.id,
        "receipt_number": payment.receipt_number,
        "student": {
            "id": payment.student.id,
            "student_number": payment.student.student_number,
            "name": f"{payment.student.first_name} {payment.student.last_name}",
        },
        "semester": {
            "id": payment.semester.id,
            "name": str(payment.semester),
            "academic_year": payment.semester.academic_year.name,
        },
        "amount": float(payment.amount),
        "payment_date": payment.payment_date.isoformat(),
        "method": payment.method,
        "method_display": payment.get_method_display(),
        "reference": payment.reference,
        "notes": payment.notes,
        "created_at": payment.created_at.isoformat(),
    }, status=201)


@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_payment_detail(request, pk):
    """Get payment detail including receipt data."""
    payment = get_object_or_404(
        Payment.objects.select_related("student", "semester", "semester__academic_year"),
        pk=pk
    )

    # Get student balance for this semester
    balance = student_balance(payment.student, payment.semester)

    return JsonResponse({
        "id": payment.id,
        "receipt_number": payment.receipt_number,
        "student": {
            "id": payment.student.id,
            "student_number": payment.student.student_number,
            "first_name": payment.student.first_name,
            "last_name": payment.student.last_name,
            "name": f"{payment.student.first_name} {payment.student.last_name}",
            "program": {
                "id": payment.student.program.id,
                "name": payment.student.program.name,
                "code": payment.student.program.code,
            } if payment.student.program else None,
        },
        "semester": {
            "id": payment.semester.id,
            "name": str(payment.semester),
            "number": payment.semester.number,
            "academic_year": payment.semester.academic_year.name,
            "academic_year_id": payment.semester.academic_year_id,
        },
        "amount": float(payment.amount),
        "payment_date": payment.payment_date.isoformat(),
        "method": payment.method,
        "method_display": payment.get_method_display(),
        "reference": payment.reference,
        "notes": payment.notes,
        "created_at": payment.created_at.isoformat(),
        "student_balance": float(balance),
    })


@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_payment_receipt(request, pk):
    """Get receipt data for printing/display."""
    payment = get_object_or_404(
        Payment.objects.select_related("student", "semester", "semester__academic_year", "student__program"),
        pk=pk
    )

    # Calculate charged/paid/balance for this student in this semester
    charged = (
        StudentCharge.objects.filter(
            student=payment.student,
            fee_item__fee_structure__semester=payment.semester,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )
    paid = (
        Payment.objects.filter(
            student=payment.student,
            semester=payment.semester,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )
    balance = charged - paid

    return JsonResponse({
        "receipt_number": payment.receipt_number,
        "payment_date": payment.payment_date.isoformat(),
        "amount": float(payment.amount),
        "method": payment.method,
        "method_display": payment.get_method_display(),
        "reference": payment.reference,
        "notes": payment.notes,
        "student": {
            "student_number": payment.student.student_number,
            "first_name": payment.student.first_name,
            "last_name": payment.student.last_name,
            "name": f"{payment.student.first_name} {payment.student.last_name}",
            "program": payment.student.program.name if payment.student.program else None,
        },
        "semester": {
            "name": str(payment.semester),
            "academic_year": payment.semester.academic_year.name,
        },
        "financials": {
            "charged": float(charged),
            "paid": float(paid),
            "balance": float(balance),
        },
    })


# ============================================================
# FINANCIAL RECORDS API
# ============================================================

@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_financial_records(request):
    """Institution-wide financial records by academic year and semester."""
    from itertools import groupby

    year_filter = request.GET.get("academic_year", "")
    today = get_current_date()
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
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
        collection_rate = (float(total_paid) / float(total_charged) * 100) if total_charged > 0 else 0.0

        students_charged = StudentCharge.objects.filter(
            fee_item__fee_structure__semester=sem
        ).values("student").distinct().count()

        semester_data.append({
            "semester": {
                "id": sem.id,
                "name": str(sem),
                "number": sem.number,
                "academic_year": sem.academic_year.name,
            },
            "total_charged": float(total_charged),
            "total_paid": float(total_paid),
            "outstanding": float(outstanding),
            "collection_rate": round(collection_rate, 1),
            "students_charged": students_charged,
        })

    # Group by academic year
    year_groups = []
    for year, semesters_iter in groupby(semester_data, key=lambda x: x["semester"]["academic_year"]):
        semesters = list(semesters_iter)
        charged = sum(s["total_charged"] for s in semesters)
        paid = sum(s["total_paid"] for s in semesters)
        outstanding = sum(s["outstanding"] for s in semesters)
        year_groups.append({
            "year": semesters[0]["semester"]["academic_year"],
            "semesters": semesters,
            "totals": {
                "charged": charged,
                "paid": paid,
                "outstanding": outstanding,
                "collection_rate": round((paid / charged * 100) if charged > 0 else 0.0, 1),
                "students_charged": sum(s["students_charged"] for s in semesters),
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
        round(grand_total_paid / grand_total_charged * 100, 1) if grand_total_charged > 0 else 0.0
    )

    return JsonResponse({
        "year_groups": year_groups,
        "all_years": [
            {"id": y.id, "name": y.name} for y in all_years
        ],
        "selected_year_id": selected_year_id,
        "selected_year": selected_year.name if selected_year else None,
        "current_year": current_year.name if current_year else None,
        "grand_total_charged": grand_total_charged,
        "grand_total_paid": grand_total_paid,
        "grand_total_outstanding": grand_total_outstanding,
        "grand_collection_rate": grand_collection_rate,
    })


# ============================================================
# STUDENT PAYMENT HISTORY & BALANCE API
# ============================================================

@login_required
@permission_required("school.view_student", raise_exception=True)
def api_student_payment_history(request, pk):
    """Get student's payment history and semester balances."""
    student = get_object_or_404(Student.objects.select_related("program", "intake_year"), pk=pk)
    today = get_current_date()

    # Get all semesters with charges or payments for this student
    semesters = (
        Semester.objects
        .select_related("academic_year")
        .order_by("-academic_year__name", "-number")
    )

    balances = []
    for semester in semesters:
        charged = (
            StudentCharge.objects.filter(
                student=student,
                fee_item__fee_structure__semester=semester,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        )

        paid = (
            Payment.objects.filter(
                student=student,
                semester=semester,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        )

        if charged == 0 and paid == 0:
            continue

        balances.append({
            "semester": {
                "id": semester.id,
                "name": str(semester),
                "number": semester.number,
                "academic_year": semester.academic_year.name,
            },
            "charged": float(charged),
            "paid": float(paid),
            "balance": float(charged - paid),
        })

    # Payment history
    payments = Payment.objects.filter(student=student).select_related("semester", "semester__academic_year").order_by("-payment_date", "-id")

    payment_list = []
    for payment in payments:
        payment_list.append({
            "id": payment.id,
            "receipt_number": payment.receipt_number,
            "payment_date": payment.payment_date.isoformat(),
            "semester": {
                "id": payment.semester.id,
                "name": str(payment.semester),
                "academic_year": payment.semester.academic_year.name,
            },
            "method": payment.method,
            "method_display": payment.get_method_display(),
            "amount": float(payment.amount),
            "reference": payment.reference,
            "notes": payment.notes,
        })

    # Current academic year balances
    current_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
    ).first()

    semester_balances = []
    total_year_balance = Decimal("0")

    if current_year:
        enrollments = student.enrollments.filter(
            semester__academic_year=current_year,
            status__in=[Enrollment.ACTIVE, Enrollment.COMPLETED],
        ).select_related("semester", "program").order_by("semester__number")

        for enrollment in enrollments:
            semester = enrollment.semester

            charged = (
                StudentCharge.objects.filter(
                    student=student,
                    enrollment=enrollment,
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            )

            paid = (
                Payment.objects.filter(
                    student=student,
                    semester=semester,
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            )

            balance = charged - paid

            semester_balances.append({
                "semester": {
                    "id": semester.id,
                    "name": str(semester),
                    "number": semester.number,
                    "academic_year": semester.academic_year.name,
                },
                "year_level": enrollment.year_level,
                "charged": float(charged),
                "paid": float(paid),
                "balance": float(balance),
            })

            total_year_balance += balance

    return JsonResponse({
        "student": _student_payload(student),
        "balances": balances,
        "payments": payment_list,
        "semester_balances": semester_balances,
        "total_year_balance": float(total_year_balance),
        "current_year": current_year.name if current_year else None,
    })


# ============================================================
# STUDENT BALANCE FOR PAYMENT FORM
# ============================================================

@login_required
@permission_required("school.can_record_payments", raise_exception=True)
def api_student_balance(request, student_id, semester_id):
    """Get student's charged/paid/balance for a specific semester (for payment form)."""
    student = get_object_or_404(Student, pk=student_id)
    semester = get_object_or_404(Semester, pk=semester_id)

    charged = (
        StudentCharge.objects.filter(
            student=student,
            fee_item__fee_structure__semester=semester,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )

    paid = (
        Payment.objects.filter(
            student=student,
            semester=semester,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )

    balance = charged - paid

    return JsonResponse({
        "student_id": student.id,
        "semester_id": semester.id,
        "charged": float(charged),
        "paid": float(paid),
        "balance": float(balance),
    })


@login_required
@permission_required("school.can_record_payments", raise_exception=True)
def api_student_enrollments_for_payment(request, student_id):
    """Get student's enrollments that have charges or fee structures (for payment form semester dropdown)."""
    student = get_object_or_404(Student, pk=student_id)
    today = get_current_date()

    enrollments_qs = (
        student.enrollments
        .select_related("program", "semester", "semester__academic_year")
        .order_by("-semester__academic_year__name", "-semester__number")
    )

    results = []
    for enrollment in enrollments_qs:
        has_charges = StudentCharge.objects.filter(enrollment=enrollment).exists()
        has_payments = Payment.objects.filter(student=student, semester=enrollment.semester).exists()
        has_fee_structure = FeeStructure.objects.filter(
            program=enrollment.program,
            year_level=enrollment.year_level,
            semester=enrollment.semester,
        ).exists()

        if has_charges or has_payments or has_fee_structure:
            charged = (
                StudentCharge.objects.filter(
                    student=student,
                    fee_item__fee_structure__semester=enrollment.semester,
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            )
            paid = (
                Payment.objects.filter(
                    student=student,
                    semester=enrollment.semester,
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            )

            results.append({
                "id": enrollment.id,
                "semester": {
                    "id": enrollment.semester.id,
                    "name": str(enrollment.semester),
                    "number": enrollment.semester.number,
                    "academic_year": enrollment.semester.academic_year.name,
                },
                "program": {
                    "id": enrollment.program.id,
                    "name": enrollment.program.name,
                    "code": enrollment.program.code,
                },
                "year_level": enrollment.year_level,
                "status": enrollment.status,
                "charged": float(charged),
                "paid": float(paid),
                "balance": float(charged - paid),
                "is_current": (
                    enrollment.status == Enrollment.ACTIVE
                    and enrollment.semester.end_date >= today
                ),
            })

    return JsonResponse({
        "student_id": student.id,
        "enrollments": results,
    })


# ============================================================
# REPORTS API
# ============================================================

@login_required
@permission_required("school.view_student", raise_exception=True)
def api_reports_index(request):
    """List all available reports for the Nuxt frontend."""
    return JsonResponse({
        "reports": REPORTS,
    })


@login_required
@permission_required("school.view_student", raise_exception=True)
def api_enrollment_report(request):
    """Student enrollment summary by program, intake year, and status."""
    program_filter = request.GET.get("program")
    intake_year_filter = request.GET.get("intake_year")
    status_filter = request.GET.get("status")
    page_number = request.GET.get("page", "1")

    # Use existing helper
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

    paginator = Paginator(data, 25)
    page_obj = paginator.get_page(page_number)

    results = []
    for row in page_obj.object_list:
        program_obj = row.get("program_obj")
        intake_year_obj = row.get("intake_year_obj")
        results.append({
            "program": {
                "id": program_obj.id if program_obj else None,
                "name": program_obj.name if program_obj else "Unknown",
                "code": program_obj.code if program_obj else "",
            },
            "intake_year": {
                "id": intake_year_obj.id if intake_year_obj else None,
                "name": intake_year_obj.name if intake_year_obj else "Unknown",
            },
            "status": row["status"],
            "status_display": dict(Student.STATUS_CHOICES).get(row["status"], row["status"]),
            "count": row["count"],
        })

    all_programs = Program.objects.filter(active=True).order_by("name")
    all_intake_years = AcademicYear.objects.all().order_by("-name")

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "filters": {
            "program": program_filter,
            "intake_year": intake_year_filter,
            "status": status_filter,
        },
        "all_programs": [
            {"id": p.id, "name": p.name, "code": p.code} for p in all_programs
        ],
        "all_intake_years": [
            {"id": y.id, "name": y.name} for y in all_intake_years
        ],
        "status_choices": [
            {"value": v, "label": l} for v, l in Student.STATUS_CHOICES
        ],
    })


@login_required
@permission_required("school.can_view_outstanding_reports", raise_exception=True)
def api_outstanding_report(request):
    """Students with outstanding balances for a semester."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()

    semester_id = request.GET.get("semester")
    program_filter = request.GET.get("program")
    page_number = request.GET.get("page", "1")

    # Get semester
    if semester_id:
        try:
            semester = Semester.objects.select_related("academic_year").get(pk=semester_id)
        except Semester.DoesNotExist:
            semester = current_semester
    else:
        semester = current_semester

    if not semester:
        return JsonResponse({
            "count": 0,
            "page": 1,
            "pages": 1,
            "results": [],
            "semester": None,
            "totals": {
                "total_charged": 0,
                "total_paid": 0,
                "total_outstanding": 0,
                "avg_outstanding": 0,
                "total_students": 0,
            },
        })

    students_qs = outstanding_students(semester)
    if program_filter:
        students_qs = students_qs.filter(program_id=program_filter)

    total_charged = sum(s.charged or Decimal("0") for s in students_qs)
    total_paid = sum(s.paid or Decimal("0") for s in students_qs)
    total_outstanding = total_charged - total_paid
    avg_outstanding = (total_outstanding / students_qs.count()) if students_qs.count() > 0 else Decimal("0")

    paginator = Paginator(students_qs, 25)
    page_obj = paginator.get_page(page_number)

    results = []
    for s in page_obj.object_list:
        charged = s.charged or Decimal("0")
        paid = s.paid or Decimal("0")
        results.append({
            "id": s.id,
            "student_number": s.student_number,
            "name": f"{s.first_name} {s.last_name}",
            "program": s.program.name,
            "program_code": s.program.code,
            "charged": float(charged),
            "paid": float(paid),
            "outstanding": float(charged - paid),
            "collection_rate": float((paid / charged * 100) if charged > 0 else 0),
        })

    all_semesters = Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number")
    all_programs = Program.objects.filter(active=True).order_by("name")

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "semester": {
            "id": semester.id,
            "name": str(semester),
            "academic_year": semester.academic_year.name,
        },
        "filters": {
            "semester": str(semester.id),
            "program": program_filter,
        },
        "totals": {
            "total_charged": float(total_charged),
            "total_paid": float(total_paid),
            "total_outstanding": float(total_outstanding),
            "avg_outstanding": float(avg_outstanding),
            "total_students": students_qs.count(),
        },
        "all_semesters": [
            {"id": s.id, "name": str(s), "academic_year": s.academic_year.name} for s in all_semesters
        ],
        "all_programs": [
            {"id": p.id, "name": p.name, "code": p.code} for p in all_programs
        ],
    })


@login_required
@permission_required("school.view_feestructure", raise_exception=True)
def api_fee_audit_report(request):
    """Programs/year-levels missing fee structure configurations."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()

    semester_id = request.GET.get("semester")

    if semester_id:
        try:
            semester = Semester.objects.select_related("academic_year").get(pk=semester_id)
        except Semester.DoesNotExist:
            semester = current_semester
    else:
        semester = current_semester

    if not semester:
        return JsonResponse({
            "semester": None,
            "missing": [],
            "all_semesters": [],
        })

    missing = unconfigured_fee_structures(semester)

    missing_data = []
    for item in missing:
        missing_data.append({
            "program": {
                "id": item["program"].id,
                "name": item["program"].name,
                "code": item["program"].code,
            },
            "year_level": item["year_level"],
        })

    all_semesters = Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number")

    return JsonResponse({
        "semester": {
            "id": semester.id,
            "name": str(semester),
            "number": semester.number,
            "academic_year": semester.academic_year.name,
        },
        "missing": missing_data,
        "all_semesters": [
            {"id": s.id, "name": str(s), "academic_year": s.academic_year.name} for s in all_semesters
        ],
    })


@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_payment_methods_report(request):
    """Payment breakdown by method for a semester."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()

    semester_id = request.GET.get("semester")

    if semester_id:
        try:
            semester = Semester.objects.select_related("academic_year").get(pk=semester_id)
        except Semester.DoesNotExist:
            semester = current_semester
    else:
        semester = current_semester

    if not semester:
        return JsonResponse({
            "semester": None,
            "breakdown": [],
            "totals": {
                "total_transactions": 0,
                "total_amount": 0,
            },
            "all_semesters": [],
        })

    breakdown = payment_methods_breakdown(semester)

    method_choices = dict(Payment.PAYMENT_METHODS)
    breakdown_data = []
    for item in breakdown:
        breakdown_data.append({
            "method": item["method"],
            "method_display": method_choices.get(item["method"], item["method"]),
            "count": item["count"] or 0,
            "total": float(item["total"]),
        })

    total_transactions = sum(item["count"] or 0 for item in breakdown)
    total_amount = sum(item["total"] for item in breakdown)

    all_semesters = Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number")

    return JsonResponse({
        "semester": {
            "id": semester.id,
            "name": str(semester),
            "academic_year": semester.academic_year.name,
        },
        "breakdown": breakdown_data,
        "totals": {
            "total_transactions": total_transactions,
            "total_amount": float(total_amount),
        },
        "all_semesters": [
            {"id": s.id, "name": str(s), "academic_year": s.academic_year.name} for s in all_semesters
        ],
    })


@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_program_revenue_report(request):
    """Revenue comparison across programs for a semester."""
    today = get_current_date()
    current_semester = Semester.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()

    semester_id = request.GET.get("semester")

    if semester_id:
        try:
            semester = Semester.objects.select_related("academic_year").get(pk=semester_id)
        except Semester.DoesNotExist:
            semester = current_semester
    else:
        semester = current_semester

    if not semester:
        return JsonResponse({
            "semester": None,
            "revenue_data": [],
            "totals": {
                "total_charged": 0,
                "total_paid": 0,
                "total_outstanding": 0,
                "overall_collection_rate": 0,
            },
            "all_semesters": [],
        })

    revenue_data = program_revenue(semester)

    revenue_results = []
    for item in revenue_data:
        charged = item["charged"] or Decimal("0")
        paid = item["paid"] or Decimal("0")
        outstanding = charged - paid
        collection_rate = (float(paid) / float(charged) * 100) if charged > 0 else 0
        revenue_results.append({
            "program": {
                "id": item["fee_item__fee_structure__program__id"],
                "name": item["fee_item__fee_structure__program__name"],
                "code": item["fee_item__fee_structure__program__code"],
            },
            "charged": float(charged),
            "paid": float(paid),
            "outstanding": float(outstanding),
            "collection_rate": round(collection_rate, 1),
        })

    total_charged = sum(item["charged"] or Decimal("0") for item in revenue_data)
    total_paid = sum(item["paid"] or Decimal("0") for item in revenue_data)
    total_outstanding = sum((item["charged"] or Decimal("0")) - (item["paid"] or Decimal("0")) for item in revenue_data)
    overall_collection_rate = (float(total_paid) / float(total_charged) * 100) if total_charged > 0 else 0

    all_semesters = Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number")

    return JsonResponse({
        "semester": {
            "id": semester.id,
            "name": str(semester),
            "academic_year": semester.academic_year.name,
        },
        "revenue_data": revenue_results,
        "totals": {
            "total_charged": float(total_charged),
            "total_paid": float(total_paid),
            "total_outstanding": float(total_outstanding),
            "overall_collection_rate": round(overall_collection_rate, 1),
        },
        "all_semesters": [
            {"id": s.id, "name": str(s), "academic_year": s.academic_year.name} for s in all_semesters
        ],
    })


@login_required
@permission_required("school.can_view_financial_reports", raise_exception=True)
def api_daily_collections_report(request):
    """Daily collections / cashbook report."""
    from datetime import datetime

    today = get_current_date()
    date_filter = request.GET.get("date")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    page_number = request.GET.get("page", "1")

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

    # Get payments based on date range or single date
    if start_date and end_date:
        payments_qs = daily_collections(start_date=start_date, end_date=end_date)
        display_date = f"{start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}"
    else:
        payments_qs = daily_collections(filter_date)
        display_date = filter_date.strftime("%b %d, %Y")

    total = payments_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    avg_transaction = (total / payments_qs.count()) if payments_qs.count() > 0 else Decimal("0")

    paginator = Paginator(payments_qs, 50)
    page_obj = paginator.get_page(page_number)

    results = []
    for p in page_obj.object_list:
        results.append({
            "id": p.id,
            "receipt_number": p.receipt_number,
            "student": {
                "id": p.student.id,
                "student_number": p.student.student_number,
                "name": f"{p.student.first_name} {p.student.last_name}",
            },
            "semester": {
                "id": p.semester.id,
                "name": str(p.semester),
                "academic_year": p.semester.academic_year.name,
            },
            "method": p.method,
            "method_display": p.get_method_display(),
            "amount": float(p.amount),
            "reference": p.reference,
            "payment_date": p.payment_date.isoformat(),
        })

    return JsonResponse({
        "filter_date": filter_date.isoformat(),
        "date_from": date_from,
        "date_to": date_to,
        "display_date": display_date,
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "totals": {
            "total": float(total),
            "avg_transaction": float(avg_transaction),
            "transaction_count": payments_qs.count(),
        },
    })


@login_required
@permission_required("school.view_studentstatuslog", raise_exception=True)
def api_status_history_report(request):
    """Student status change history."""
    today = get_current_date()
    student_filter = request.GET.get("student")
    start_date_filter = request.GET.get("start_date")
    end_date_filter = request.GET.get("end_date")
    page_number = request.GET.get("page", "1")

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

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(page_number)

    results = []
    for log in page_obj.object_list:
        results.append({
            "id": log.id,
            "date_changed": log.date_changed.isoformat(),
            "student": {
                "id": log.student.id,
                "student_number": log.student.student_number,
                "name": f"{log.student.first_name} {log.student.last_name}",
                "program": log.student.program.name,
            },
            "status": log.status,
            "status_display": log.get_status_display(),
            "note": log.note,
        })

    all_students = Student.objects.select_related("program").order_by("last_name", "first_name")

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "filters": {
            "student": student.id if student else None,
            "start_date": start_date_filter,
            "end_date": end_date_filter,
        },
        "all_students": [
            {"id": s.id, "student_number": s.student_number, "name": f"{s.first_name} {s.last_name}", "program": s.program.name} for s in all_students
        ],
    })


# ============================================================
# REMINDERS API
# ============================================================

@login_required
@permission_required("school.view_student", raise_exception=True)
def api_reminders(request):
    """Display reminders about students with missing details."""
    page_number = request.GET.get("page", "1")

    students = students_with_missing_details()
    total_reminders = students.count()

    paginator = Paginator(students, 10)
    page_obj = paginator.get_page(page_number)

    results = []
    for student in page_obj.object_list:
        missing = []
        if not student.guardian_name:
            missing.append("Missing Guardian Name")
        if not student.student_phone:
            missing.append("Missing Student Phone")
        if not student.address:
            missing.append("Missing Address")
        if not student.guardian_phone:
            missing.append("Missing Guardian Phone")

        results.append({
            "id": student.id,
            "student_number": student.student_number,
            "name": f"{student.first_name} {student.last_name}",
            "program": {
                "id": student.program.id,
                "name": student.program.name,
                "code": student.program.code,
            },
            "missing_details": missing,
        })

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "total_reminders": total_reminders,
    })


# ============================================================
# ADMINISTRATION API
# ============================================================

@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_user_list(request):
    """List all users with their groups and permissions."""
    from django.contrib.auth.models import User, Group

    users = User.objects.all().prefetch_related('groups').order_by('-is_superuser', 'username')
    paginator = Paginator(users, 25)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    results = []
    for user in page_obj.object_list:
        groups = list(user.groups.all())
        results.append({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "is_active": user.is_active,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "groups": [
                {"id": g.id, "name": g.name} for g in groups
            ],
        })

    all_groups = Group.objects.all().order_by("name")

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "all_groups": [
            {"id": g.id, "name": g.name} for g in all_groups
        ],
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_user_create(request):
    """Create a new user and assign to a group."""
    from django.contrib.auth.models import User, Group

    if request.method != "POST":
        return JsonResponse({"errors": {"detail": ["Only POST method is allowed."]}}, status=405)

    payload = _parse_json_body(request)

    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    group_id = payload.get("group")
    is_staff = payload.get("is_staff", False)

    errors = {}
    if not username:
        errors["username"] = ["Username is required."]
    if not password:
        errors["password"] = ["Password is required."]
    else:
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            validate_password(password)
        except ValidationError as exc:
            errors["password"] = list(exc.messages)

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({"errors": {"username": ["A user with that username already exists."]}}, status=400)

    try:
        user = User.objects.create_user(
            username=username,
            password=password,
            is_staff=is_staff,
        )
        if group_id:
            try:
                group = Group.objects.get(pk=group_id)
                user.groups.add(group)
            except Group.DoesNotExist:
                pass
    except Exception as e:
        return JsonResponse({"errors": {"detail": [str(e)]}}, status=400)

    # Return user data without password
    groups = list(user.groups.all())
    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "groups": [
            {"id": g.id, "name": g.name} for g in groups
        ],
    }, status=201)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_user_update(request, pk):
    """Update user groups and staff status."""
    from django.contrib.auth.models import User, Group

    user = get_object_or_404(User, pk=pk)

    if request.method not in ["PATCH", "PUT"]:
        return JsonResponse({"errors": {"detail": ["Only PATCH or PUT method is allowed."]}}, status=405)

    payload = _parse_json_body(request)

    # Prevent superuser from removing their own superuser status
    if user == request.user and payload.get("is_superuser") is False:
        return JsonResponse({"errors": {"is_superuser": ["Cannot remove your own superuser status."]}}, status=400)

    # Prevent superuser from removing their own active status
    if user == request.user and payload.get("is_active") is False:
        return JsonResponse({"errors": {"is_active": ["Cannot deactivate your own account."]}}, status=400)

    if "is_staff" in payload:
        user.is_staff = payload["is_staff"]
    if "is_active" in payload:
        user.is_active = payload["is_active"]

    if "group" in payload:
        group_id = payload["group"]
        user.groups.clear()
        if group_id:
            try:
                group = Group.objects.get(pk=group_id)
                user.groups.add(group)
            except Group.DoesNotExist:
                pass

    user.save()

    groups = list(user.groups.all())
    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "groups": [
            {"id": g.id, "name": g.name} for g in groups
        ],
    })


@login_required
@permission_required("school.view_auditlog", raise_exception=True)
def api_audit_log_list(request):
    """Audit trail list with pagination and filters."""
    logs = AuditLog.objects.select_related("user", "student").all()

    # Filters
    action_filter = request.GET.get("action")
    user_filter = request.GET.get("user")
    student_filter = request.GET.get("student")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    page_number = request.GET.get("page", "1")

    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    if student_filter:
        logs = logs.filter(student_id=student_filter)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    logs = logs.order_by("-timestamp")
    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(page_number)

    results = []
    for log in page_obj.object_list:
        results.append({
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "user": {
                "id": log.user.id if log.user else None,
                "username": log.user.username if log.user else None,
            },
            "action": log.action,
            "action_display": log.get_action_display(),
            "category": log.category,
            "student": {
                "id": log.student.id if log.student else None,
                "student_number": log.student.student_number if log.student else None,
                "name": f"{log.student.first_name} {log.student.last_name}" if log.student else None,
            } if log.student else None,
            "summary": log.summary,
            "details": log.details,
        })

    # Get filter options
    all_actions = AuditLog.ACTION_CHOICES
    all_users = User.objects.filter(auditlog__isnull=False).distinct().order_by("username")

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "results": results,
        "filters": {
            "action": action_filter,
            "user": user_filter,
            "student": student_filter,
            "date_from": date_from,
            "date_to": date_to,
        },
        "all_actions": [
            {"value": v, "label": l} for v, l in all_actions
        ],
        "all_users": [
            {"id": u.id, "username": u.username} for u in all_users
        ],
    })


# ============================================================
# BACKUP MANAGEMENT API
# ============================================================

@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_backup_list(request):
    """List all backups with size and date."""
    config = BackupConfig.get_config()
    backup_dir = config.get_backup_path()
    backups = []

    import os
    if os.path.exists(backup_dir):
        for filename in sorted(os.listdir(backup_dir), reverse=True):
            filepath = os.path.join(backup_dir, filename)
            if os.path.isfile(filepath) and filename.endswith('.sqlite3'):
                stat = os.stat(filepath)
                backups.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

    return JsonResponse({
        "backups": backups,
        "config": {
            "backup_path": config.backup_path,
            "auto_backup_enabled": config.auto_backup_enabled,
            "retention_days": config.retention_days,
            "strict_mode": config.strict_mode,
        },
        "backup_available": config.is_backup_available(),
        "backup_path": backup_dir,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def api_backup_create(request):
    """Create a new, integrity-checked backup of the current database."""
    import os
    from datetime import datetime
    from django.conf import settings

    config = BackupConfig.get_config()
    db_path = settings.DATABASES['default']['NAME']
    backup_dir = config.get_backup_path()

    backup_name = timestamped_name("backup")
    backup_path = os.path.join(backup_dir, backup_name)

    try:
        create_backup(db_path, backup_path)
    except BackupError as exc:
        return JsonResponse({"errors": {"detail": [f"Backup failed: {exc}"]}}, status=500)

    stat = os.stat(backup_path)
    return JsonResponse({
        "success": True,
        "message": f"Backup created and verified: {backup_name}",
        "backup": {
            "name": backup_name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    }, status=201)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_backup_download(request, filename):
    """Download a backup file."""
    import os
    config = BackupConfig.get_config()
    backup_dir = config.get_backup_path()

    # Sanitize filename to prevent directory traversal
    filename = os.path.basename(filename)
    filepath = os.path.join(backup_dir, filename)

    if not os.path.exists(filepath):
        return JsonResponse({"errors": {"detail": ["Backup file not found."]}}, status=404)

    response = FileResponse(open(filepath, 'rb'), as_attachment=True, filename=filename)
    return response


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def api_backup_restore(request, filename):
    """Restore a verified backup, creating a safety backup first."""
    import os
    from django.conf import settings

    config = BackupConfig.get_config()
    db_path = settings.DATABASES['default']['NAME']
    backup_dir = config.get_backup_path()

    # Sanitize filename
    filename = os.path.basename(filename)
    backup_path = os.path.join(backup_dir, filename)

    if not os.path.exists(backup_path):
        return JsonResponse({"errors": {"detail": ["Backup file not found."]}}, status=404)

    try:
        safety_path = restore_backup(backup_path, db_path)
    except BackupError as exc:
        return JsonResponse({"errors": {"detail": [f"Restore failed: {exc}"]}}, status=500)

    return JsonResponse({
        "success": True,
        "message": f"Database restored from {filename} and verified.",
        "safety_backup": os.path.basename(safety_path) if safety_path else None,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def api_backup_upload(request):
    """Upload a backup file from local machine."""
    import os
    from datetime import datetime

    config = BackupConfig.get_config()
    backup_dir = config.get_backup_path()

    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir, exist_ok=True)
        except Exception as e:
            return JsonResponse({"errors": {"detail": [f"Cannot create backup directory: {e}"]}}, status=400)

    uploaded_file = request.FILES.get('backup_file')
    if not uploaded_file:
        return JsonResponse({"errors": {"backup_file": ["No file selected."]}}, status=400)

    # Validate file extension
    allowed_extensions = ('.sqlite3', '.db')
    if not uploaded_file.name.endswith(allowed_extensions):
        return JsonResponse({"errors": {"backup_file": ["Invalid file type. Only .sqlite3 or .db files are allowed."]}}, status=400)

    # Sanitize filename
    original_name = os.path.basename(uploaded_file.name)
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
            return JsonResponse(
                {"errors": {"backup_file": [f"Uploaded file rejected: {message}"]}},
                status=400,
            )

        stat = os.stat(backup_path)
        return JsonResponse({
            "success": True,
            "message": f"Backup uploaded and verified: {safe_name}",
            "backup": {
                "name": safe_name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        }, status=201)
    except Exception as e:
        return JsonResponse({"errors": {"detail": [f"Upload failed: {e}"]}}, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_backup_settings(request):
    """Get or update backup configuration."""
    config = BackupConfig.get_config()

    if request.method in ["PATCH", "PUT"]:
        payload = _parse_json_body(request)

        if "backup_path" in payload:
            config.backup_path = payload["backup_path"]
        if "auto_backup_enabled" in payload:
            config.auto_backup_enabled = payload["auto_backup_enabled"]
        if "retention_days" in payload:
            try:
                config.retention_days = int(payload["retention_days"])
            except (ValueError, TypeError):
                return JsonResponse({"errors": {"retention_days": ["Invalid value."]}}, status=400)
        if "strict_mode" in payload:
            config.strict_mode = payload["strict_mode"]

        config.save()

    return JsonResponse({
        "backup_path": config.backup_path,
        "auto_backup_enabled": config.auto_backup_enabled,
        "retention_days": config.retention_days,
        "strict_mode": config.strict_mode,
        "backup_available": config.is_backup_available(),
        "effective_backup_path": config.get_backup_path(),
    })


# ============================================================
# TIME OVERRIDE API
# ============================================================

@login_required
@user_passes_test(lambda u: u.is_superuser)
def api_time_override(request):
    """Get or set the time override."""
    from django.utils import timezone

    if request.method == "GET":
        frozen = TimeOverride.get_frozen_time()
        return JsonResponse({
            "frozen": frozen.isoformat() if frozen else None,
            "is_frozen": frozen is not None,
        })

    elif request.method in ["POST", "PATCH"]:
        payload = _parse_json_body(request)
        action = payload.get("action")

        if action == "set":
            frozen_datetime_str = payload.get("frozen_datetime")
            if not frozen_datetime_str:
                return JsonResponse({"errors": {"frozen_datetime": ["Datetime is required."]}}, status=400)
            try:
                if timezone.is_naive(frozen_datetime_str):
                    dt = timezone.make_aware(datetime.fromisoformat(frozen_datetime_str))
                else:
                    dt = datetime.fromisoformat(frozen_datetime_str)
                TimeOverride.set_frozen_time(dt)
                return JsonResponse({
                    "success": True,
                    "message": f"Time frozen to {dt}",
                    "frozen": dt.isoformat(),
                })
            except (ValueError, TypeError) as e:
                return JsonResponse({"errors": {"frozen_datetime": ["Invalid date/time format."]}}, status=400)

        elif action == "clear":
            TimeOverride.set_frozen_time(None)
            return JsonResponse({
                "success": True,
                "message": "Time override cleared. Using real time.",
                "frozen": None,
            })

        else:
            return JsonResponse({"errors": {"action": ["Invalid action. Use 'set' or 'clear'."]}}, status=400)

    return JsonResponse({"errors": {"detail": ["Method not allowed."]}}, status=405)


@login_required
def api_auth_check(request):
    """Check if user is authenticated and return user info."""
    return JsonResponse({
        "authenticated": True,
        "user": _auth_user_payload(request.user),
    })


@ensure_csrf_cookie
def api_auth_check_public(request):
    """Public auth check - returns auth status without requiring login."""
    if request.user.is_authenticated:
        return JsonResponse({
            "authenticated": True,
            "user": _auth_user_payload(request.user),
        })
    return JsonResponse({"authenticated": False, "user": None})


def api_auth_login(request):
    """Login via API - returns session cookie."""
    from django.contrib.auth import authenticate, login

    if request.method != "POST":
        return JsonResponse({"errors": {"detail": ["Only POST method is allowed."]}}, status=405)

    payload = _parse_json_body(request)
    username = payload.get("username", "").strip()
    password = payload.get("password", "")

    if not username or not password:
        return JsonResponse({"errors": {"detail": ["Username and password are required."]}}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return JsonResponse({
            "success": True,
            "user": _auth_user_payload(user),
        })
    return JsonResponse({"errors": {"detail": ["Invalid credentials."]}}, status=401)


@login_required
def api_auth_logout(request):
    """Logout via API."""
    from django.contrib.auth import logout
    logout(request)
    return JsonResponse({"success": True})
