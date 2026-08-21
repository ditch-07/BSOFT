from decimal import Decimal
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from django.contrib import messages
from django.db.models import F
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.db import transaction
from django.utils import timezone

from .forms import (
    AcademicYearForm,
    SemesterForm,
    CourseForm,
    StudentForm,
    EnrollmentForm,
    PaymentForm,
)

from .models import (
    AcademicYear,
    Semester,
    Course,
    SemesterFee,
    Student,
    Enrollment,
    StudentCharge,
    Payment,
)

# ============================================================
# DASHBOARD
# ============================================================


from django.db.models import Sum, Q
from decimal import Decimal

def dashboard(request):
    today = timezone.localdate()

    # --- Current academic period ---
    current_year = AcademicYear.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).first()

    # --- Student count ---
    total_students = Student.objects.filter(active=True).count()

    # --- Financials for current semester ---
    if current_semester:
        # All charges for all students in this semester
        total_charged = StudentCharge.objects.filter(
            semester_fee__semester=current_semester
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        total_paid = Payment.objects.filter(
            semester=current_semester
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        outstanding = total_charged - total_paid
        collection_rate = (total_paid / total_charged * 100) if total_charged > 0 else 0

        # Students with outstanding balance in current semester
        students_with_balance = Student.objects.filter(
            enrollments__semester=current_semester,
            enrollments__status=Enrollment.ACTIVE
        ).annotate(
            charged=Sum('charges__amount', filter=Q(charges__semester_fee__semester=current_semester)),
            paid=Sum('payments__amount', filter=Q(payments__semester=current_semester))
        ).filter(charged__gt=F('paid')).count()

        # Top 5 students with highest outstanding
        top_outstanding = Student.objects.filter(
            enrollments__semester=current_semester,
            enrollments__status=Enrollment.ACTIVE
        ).annotate(
            charged=Sum('charges__amount', filter=Q(charges__semester_fee__semester=current_semester)),
            paid=Sum('payments__amount', filter=Q(payments__semester=current_semester))
        ).annotate(
            balance=F('charged') - F('paid')
        ).filter(balance__gt=0).order_by('-balance')[:5]

    else:
        total_charged = total_paid = outstanding = collection_rate = students_with_balance = 0
        top_outstanding = []

    # --- Today's payments ---
    today_payments = Payment.objects.filter(payment_date=today).select_related('student', 'semester')
    today_total = today_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # --- Recent payments (last 10) ---
    recent_payments = Payment.objects.select_related('student', 'semester').order_by('-payment_date', '-id')[:10]

    # --- Upcoming semester (if any) ---
    upcoming_semester = Semester.objects.filter(start_date__gt=today).order_by('start_date').first()

    context = {
        'total_students': total_students,
        'current_year': current_year,
        'current_semester': current_semester,
        'total_charged': total_charged,
        'total_paid': total_paid,
        'outstanding': outstanding,
        'collection_rate': collection_rate,
        'students_with_balance': students_with_balance,
        'top_outstanding': top_outstanding,
        'today_payments': today_payments,
        'today_total': today_total,
        'recent_payments': recent_payments,
        'upcoming_semester': upcoming_semester,
        'today': today,
    }
    return render(request, 'school/dashboard.html', context)

def student_search(request):

    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({
            "students": []
        })

    students = (
        Student.objects
        .filter(active=True)
        .filter(
            Q(student_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(middle_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .order_by(
            "last_name",
            "first_name",
        )[:10]
    )

    data = []

    for student in students:

        enrollment = (
            student.enrollments
        .filter(
        status=Enrollment.ACTIVE,
        semester__start_date__lte=timezone.localdate(),
        semester__end_date__gte=timezone.localdate(),
        )
        .select_related("course", "semester", "semester__academic_year")
        .first()
        )
        data.append({
            "id": student.id,
            "student_number": student.student_number,
            "name": (
                f"{student.first_name} "
                f"{student.last_name}"
            ),
            "course": (
                enrollment.course.name
                if enrollment
                else "Not enrolled"
            ),
            "semester": (
                str(enrollment.semester)
                if enrollment
                else "No active semester"
            ),
        })

    return JsonResponse({
        "students": data
    })
# ============================================================
# ACADEMIC YEARS
# ============================================================

def academic_year_list(request):

    years = AcademicYear.objects.all()

    return render(
        request,
        "school/academic_year_list.html",
        {
            "years": years,
        },
    )


def academic_year_create(request):

    form = AcademicYearForm(
        request.POST or None
    )

    if form.is_valid():

        year = form.save()

        if year.is_current:
            AcademicYear.objects.exclude(
                pk=year.pk
            ).update(
                is_current=False
            )

        messages.success(
            request,
            "Academic year created successfully.",
        )

        return redirect(
            "academic_year_list"
        )

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
# ============================================================

def semester_list(request):

    semesters = Semester.objects.select_related(
        "academic_year"
    )

    return render(
        request,
        "school/semester_list.html",
        {
            "semesters": semesters,
        },
    )


from django.forms import ValidationError, inlineformset_factory
from .forms import SemesterForm, SemesterFeeFormSet
@transaction.atomic
def semester_create(request):
    if request.method == "POST":
        form = SemesterForm(request.POST)
        formset = SemesterFeeFormSet(request.POST, instance=None)

        if form.is_valid() and formset.is_valid():
            try:
                semester = form.save()
            except ValidationError as e:
                # Safety net: catches overlap errors raised inside
                # Semester.save() -> full_clean() if they slip past
                # form.is_valid() (e.g. race condition on concurrent submits)
                form.add_error(None, e)
            else:
                formset.instance = semester
                formset.save()
                messages.success(request, "Semester and fees created successfully.")
                return redirect("semester_list")
    else:
        form = SemesterForm()
        formset = SemesterFeeFormSet(instance=None)

    return render(
        request,
        "school/semester_create_with_fees.html",
        {
            "form": form,
            "formset": formset,
            "title": "Create Semester",
            "back_url": "semester_list",
        },
    )
#  ============================================================
# FEE SETUP
# ============================================================

# def fee_setup(request):

#     fee_items = FeeItem.objects.all()

#     semester_fees = SemesterFee.objects.select_related(
#         "semester",
#         "semester__academic_year",
#         "fee_item",
#     )

#     return render(
#         request,
#         "school/fee_setup.html",
#         {
#             "fee_items": fee_items,
#             "semester_fees": semester_fees,
#         },
#     )


# def fee_item_create(request):

#     form = FeeItemForm(
#         request.POST or None
#     )

#     if form.is_valid():

#         form.save()

#         messages.success(
#             request,
#             "Fee item created.",
#         )

#         return redirect(
#             "fee_setup"
#         )

#     return render(
#         request,
#         "school/form.html",
#         {
#             "form": form,
#             "title": "Create Fee Item",
#             "back_url": "fee_setup",
#         },
#     )


# def semester_fee_create(request):

#     form = SemesterFeeForm(
#         request.POST or None
#     )

#     if form.is_valid():

#         form.save()

#         messages.success(
#             request,
#             "Fee assigned to semester.",
#         )

#         return redirect(
#             "fee_setup"
#         )

#     return render(
#         request,
#         "school/form.html",
#         {
#             "form": form,
#             "title": "Assign Fee To Semester",
#             "back_url": "fee_setup",
#         },
#     )


# ============================================================
# STUDENTS
# ============================================================

from django.core.paginator import Paginator

def student_list(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')  # 'active' or 'inactive'
    students = Student.objects.all()

    if query:
        students = students.filter(
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(middle_name__icontains=query) |
            Q(last_name__icontains=query)
        )
    if status_filter == 'active':
        students = students.filter(active=True)
    elif status_filter == 'inactive':
        students = students.filter(active=False)

    # Prefetch to avoid N+1 queries
    students = students.prefetch_related('enrollments__course', 'enrollments__semester')

    paginator = Paginator(students, 20)  # 20 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'school/student_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
    })

@transaction.atomic
def student_create(request):
    student_form = StudentForm(request.POST or None)
    course_id = request.POST.get("course")
    semester_id = request.POST.get("semester")

    courses = Course.objects.filter(active=True)

    # Only show currently active semesters (by date)
    today = timezone.localdate()
    semesters = Semester.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).select_related("academic_year")

    if request.method == "POST":
        if student_form.is_valid():
            if not course_id:
                messages.error(request, "Please select a course.")
            elif not semester_id:
                messages.error(request, "Please select a semester.")
            else:
                try:
                    course = Course.objects.get(pk=course_id, active=True)
                    semester = Semester.objects.get(pk=semester_id)
                except (Course.DoesNotExist, Semester.DoesNotExist):
                    messages.error(request, "Selected course or semester no longer exists.")
                    return render(request, "school/student_register.html", {
                        "form": student_form,
                        "courses": courses,
                        "semesters": semesters,
                    })

                # Create student
                student = student_form.save()

                # Enroll
                Enrollment.objects.create(
                    student=student,
                    course=course,
                    semester=semester,
                    status=Enrollment.ACTIVE,
                )

                # Create charges for this semester
                semester_fees = SemesterFee.objects.filter(semester=semester)
                for sf in semester_fees:
                    StudentCharge.objects.create(
                        student=student,
                        semester_fee=sf,
                        amount=sf.amount,
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
            "courses": courses,
            "semesters": semesters,
        },
    )

def student_detail(request, pk):

    student = get_object_or_404(
        Student,
        pk=pk,
    )

    semesters = Semester.objects.select_related(
        "academic_year"
    )

    balances = []

    for semester in semesters:

        charged = (
            StudentCharge.objects.filter(
                student=student,
                semester_fee__semester=semester,
            ).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0")
        )

        paid = (
            Payment.objects.filter(
                student=student,
                semester=semester,
            ).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0")
        )

        balances.append(
            {
                "semester": semester,
                "charged": charged,
                "paid": paid,
                "balance": charged - paid,
            }
        )

    payments = student.payments.select_related(
        "semester"
    )

    return render(
        request,
        "school/student_detail.html",
        {
            "student": student,
            "balances": balances,
            "payments": payments,
        },
    )


# ============================================================
# ENROLL STUDENT IN SEMESTER
# ============================================================


# ============================================================
# PAYMENTS
# ============================================================

def course_list(request):

    courses = Course.objects.all()

    return render(
        request,
        "school/course_list.html",
        {
            "courses": courses,
        },
    )


def course_create(request):

    form = CourseForm(
        request.POST or None
    )

    if form.is_valid():

        form.save()

        messages.success(
            request,
            "Course created successfully.",
        )

        return redirect(
            "course_list"
        )

    return render(
        request,
        "school/form.html",
        {
            "form": form,
            "title": "Create Course",
            "back_url": "course_list",
        },
    )

@transaction.atomic
def payment_create(request):

    student_id = request.GET.get(
        "student"
    ) or request.POST.get(
        "student_id"
    )

    student = None
    enrollment = None

    if student_id:

        student = get_object_or_404(
            Student,
            pk=student_id,
            active=True,
        )

        enrollment = (
    student.enrollments
    .filter(
        status=Enrollment.ACTIVE,
        semester__start_date__lte=timezone.localdate(),
        semester__end_date__gte=timezone.localdate(),
    )
    .select_related("course", "semester", "semester__academic_year")
    .first()
)
    form = PaymentForm(
        request.POST or None
    )

    if request.method == "POST":

        if not student:

            messages.error(
                request,
                "Please select a student first.",
            )

        elif not enrollment:

            messages.error(
                request,
                "This student has no active enrollment.",
            )

        elif form.is_valid():

            payment = form.save(
                commit=False
            )

            payment.student = student
            payment.semester = enrollment.semester

            payment.save()

            messages.success(
                request,
                "Payment recorded successfully.",
            )

            return redirect(
                "payment_create"
            )

    balance = None
    charged = 0
    paid = 0

    if student and enrollment:

        charged = (
            student.charges
            .filter(
                semester_fee__semester=(
                    enrollment.semester
                )
            )
            .aggregate(
                total=Sum("amount")
            )["total"] or 0
        )

        paid = (
            student.payments
            .filter(
                semester=enrollment.semester
            )
            .aggregate(
                total=Sum("amount")
            )["total"] or 0
        )

        balance = charged - paid

    return render(
        request,
        "school/payment_create.html",
        {
            "form": form,
            "student": student,
            "enrollment": enrollment,
            "charged": charged,
            "paid": paid,
            "balance": balance,
        },
    )

@transaction.atomic
def semester_edit(request, pk):
    semester = get_object_or_404(Semester, pk=pk)

    if request.method == "POST":
        form = SemesterForm(request.POST, instance=semester)
        formset = SemesterFeeFormSet(request.POST, instance=semester)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Semester updated successfully.")
            return redirect("semester_list")
    else:
        form = SemesterForm(instance=semester)
        formset = SemesterFeeFormSet(instance=semester)

    return render(
        request,
        "school/semester_create_with_fees.html",
        {
            "form": form,
            "formset": formset,
            "title": f"Edit {semester}",
            "submit_label": "Update Semester",
            "back_url": "semester_list",
        },
    )