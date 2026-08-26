from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

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
)


# ============================================================
# DASHBOARD
# ============================================================

def dashboard(request):
    today = timezone.localdate()

    # --- Current academic period ---
    current_year = AcademicYear.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
    ).select_related("academic_year").first()

    # --- Student count ---
    total_students = Student.objects.filter(status=Student.ACTIVE).count()

    # --- Financials for current semester ---
    if current_semester:
        total_charged = StudentCharge.objects.filter(
            fee_item__fee_structure__semester=current_semester
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        total_paid = Payment.objects.filter(
            semester=current_semester
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        outstanding = total_charged - total_paid
        collection_rate = (
            (total_paid / total_charged * 100) if total_charged > 0 else 0
        )

        active_this_semester = Student.objects.filter(
            enrollments__semester=current_semester,
            enrollments__status=Enrollment.ACTIVE,
        ).annotate(
            charged=Sum(
                "charges__amount",
                filter=Q(charges__fee_item__fee_structure__semester=current_semester),
            ),
            paid=Sum(
                "payments__amount",
                filter=Q(payments__semester=current_semester),
            ),
        )

        students_with_balance = active_this_semester.filter(
            charged__gt=F("paid")
        ).count()

        top_outstanding = (
            active_this_semester
            .annotate(balance=F("charged") - F("paid"))
            .filter(balance__gt=0)
            .order_by("-balance")[:5]
        )
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
        configured_pairs = set(
            FeeStructure.objects.filter(semester=fee_setup_semester).values_list(
                "program_id", "year_level"
            )
        )
        for program in Program.objects.filter(active=True):
            for year_level in range(1, program.duration_years + 1):
                if (program.id, year_level) not in configured_pairs:
                    unconfigured_fee_count += 1

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
    }
    return render(request, "school/dashboard.html", context)


# ============================================================
# FINANCIAL RECORDS
# ============================================================

def financial_records(request):
    """
    Institution-wide financial records showing aggregate charged/paid/outstanding
    per semester, grouped by academic year.
    """
    from itertools import groupby

    year_filter = request.GET.get("academic_year", "")
    current_year = AcademicYear.objects.filter(is_current=True).first()
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

    year_groups = {}
    for item in semester_data:
        year = item["academic_year"]
        if year not in year_groups:
            year_groups[year] = []
        year_groups[year].append(item)

    year_totals = {}
    for year, semesters in year_groups.items():
        charged = sum(s["total_charged"] for s in semesters)
        paid = sum(s["total_paid"] for s in semesters)
        year_totals[year] = {
            "charged": charged,
            "paid": paid,
            "outstanding": sum(s["outstanding"] for s in semesters),
            "collection_rate": (paid / charged * 100) if charged > 0 else 0,
        }

    all_years = AcademicYear.objects.all().order_by("-name")

    selected_year = None
    if selected_year_id:
        selected_year = all_years.filter(pk=selected_year_id).first()

    grand_total_charged = sum(t["charged"] for t in year_totals.values())
    grand_total_paid = sum(t["paid"] for t in year_totals.values())
    grand_total_outstanding = sum(t["outstanding"] for t in year_totals.values())
    grand_collection_rate = (
        (grand_total_paid / grand_total_charged * 100) if grand_total_charged > 0 else 0
    )

    context = {
        "year_groups": year_groups,
        "year_totals": year_totals,
        "all_years": all_years,
        "selected_year_id": selected_year_id,
        "selected_year": selected_year,
        "current_year": current_year,
        "grand_total_charged": grand_total_charged,
        "grand_total_paid": grand_total_paid,
        "grand_total_outstanding": grand_total_outstanding,
        "grand_collection_rate": grand_collection_rate,
        "today": timezone.localdate(),
    }
    return render(request, "school/financial_records.html", context)


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
    today = timezone.localdate()

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

def academic_year_list(request):
    years = AcademicYear.objects.all().order_by("-name")
    paginator = Paginator(years, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "school/academic_year_list.html", {"page_obj": page_obj})


def academic_year_create(request):
    form = AcademicYearForm(request.POST or None)

    if form.is_valid():
        year = form.save()

        if year.is_current:
            AcademicYear.objects.exclude(pk=year.pk).update(is_current=False)

        messages.success(request, "Academic year created successfully.")
        return redirect("academic_year_list")

    return render(
        request,
        "school/form.html",
        {
            "form": form,
            "title": "Create Academic Year",
            "back_url": "academic_year_list",
        },
    )


# ============================================================
# SEMESTERS
# (Fee structures are configured separately — see below — since a
# semester now covers several Program/Year-Level fee structures.)
# ============================================================

def semester_list(request):
    semesters = Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number")
    paginator = Paginator(semesters, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "school/semester_list.html", {"page_obj": page_obj})


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

def program_list(request):
    programs = Program.objects.all().order_by("name")
    paginator = Paginator(programs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "school/program_list.html", {"page_obj": page_obj})


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
# STUDENTS
# ============================================================

def student_list(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    program_filter = request.GET.get("program", "")
    intake_year_filter = request.GET.get("intake_year", "")
    current_semester_only = request.GET.get("current_semester", "")

    students = Student.objects.all()

    if query:
        students = students.filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    if program_filter:
        students = students.filter(program_id=program_filter)

    if status_filter:
        students = students.filter(status=status_filter.upper())

    if intake_year_filter:
        students = students.filter(intake_year_id=intake_year_filter)

    if current_semester_only:
        today = timezone.localdate()
        current_sem = Semester.objects.filter(
            start_date__lte=today, end_date__gte=today
        ).first()
        if current_sem:
            students = students.filter(enrollments__semester=current_sem)

    # Get programs with student counts for filter dropdown
    program_counts = Student.objects.values("program__id", "program__name").annotate(
        count=Count("id")
    ).order_by("program__name")

    # Get intake years with student counts
    intake_year_counts = Student.objects.values("intake_year__id", "intake_year__name").annotate(
        count=Count("id")
    ).order_by("-intake_year__name")

    # Get status counts
    status_counts = Student.objects.values("status").annotate(
        count=Count("id")
    ).order_by("status")

    students = students.select_related("program", "intake_year").prefetch_related(
        "enrollments__semester"
    )

    paginator = Paginator(students, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "school/student_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status_filter": status_filter,
            "program_filter": program_filter,
            "intake_year_filter": intake_year_filter,
            "current_semester_only": current_semester_only,
            "status_choices": Student.STATUS_CHOICES,
            "program_counts": program_counts,
            "intake_year_counts": intake_year_counts,
            "status_counts": {s["status"]: s["count"] for s in status_counts},
        },
    )


@transaction.atomic
def student_create(request):
    student_form = StudentForm(request.POST or None)

    today = timezone.localdate()
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

                fee_structure = FeeStructure.objects.filter(
                    program=student.program,
                    year_level=year_level,
                    semester=semester,
                ).prefetch_related("items").first()

                if fee_structure:
                    for item in fee_structure.items.all():
                        StudentCharge.objects.create(
                            student=student,
                            enrollment=enrollment,
                            fee_item=item,
                            amount=item.amount,
                        )
                else:
                    messages.warning(
                        request,
                        "Student registered, but no fee structure is set up yet for "
                        f"{student.program} Year {year_level} in {semester}. "
                        "The student currently shows a $0 balance until fees are configured.",
                    )

                StudentStatusLog.objects.create(
                    student=student,
                    status=Student.ACTIVE,
                    note="Initial registration.",
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


def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)

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
    current_year = AcademicYear.objects.filter(is_current=True).first()
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
        },
    )


def student_status_change(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = StudentStatusChangeForm(request.POST or None, initial={"status": student.status})

    if form.is_valid():
        student.status = form.cleaned_data["status"]
        student.save(update_fields=["status"])

        StudentStatusLog.objects.create(
            student=student,
            status=student.status,
            note=form.cleaned_data["note"],
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
# PAYMENTS
# ============================================================

@transaction.atomic
def payment_create(request):
    student_id = request.GET.get("student") or request.POST.get("student_id")
    selected_semester_id = request.GET.get("semester") or request.POST.get("semester")

    student = None
    enrollments = []
    selected_enrollment = None
    today = timezone.localdate()

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

        # Determine default semester (current active enrollment)
        default_enrollment = None
        for e in enrollments:
            if e.status == Enrollment.ACTIVE and e.semester.end_date >= today:
                default_enrollment = e
                break
        
        # Fallback: first active enrollment, then first enrollment
        if not default_enrollment:
            for e in enrollments:
                if e.status == Enrollment.ACTIVE:
                    default_enrollment = e
                    break
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

            # Auto-assign charges from FeeStructure
            fee_structure = FeeStructure.objects.filter(
                program=program,
                year_level=next_year_level,
                semester=target_semester,
            ).prefetch_related("items").first()

            if fee_structure:
                for item in fee_structure.items.all():
                    StudentCharge.objects.get_or_create(
                        student=student,
                        enrollment=enrollment,
                        fee_item=item,
                        defaults={"amount": item.amount},
                    )

    messages.success(
        request,
        f"Progressed {enrolled_count} students to {target_semester}. "
        f"{completed_count} students marked as completed/graduated."
    )
    return redirect("semester_list")