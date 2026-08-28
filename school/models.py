from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class TimeOverride(models.Model):
    """
    Stores a fixed datetime to use instead of real time.
    There should be only one row (singleton).
    """
    frozen_datetime = models.DateTimeField(null=True, blank=True)

    @classmethod
    def get_frozen_time(cls):
        """Returns the frozen datetime, or None if not set."""
        obj = cls.objects.first()
        return obj.frozen_datetime if obj else None

    @classmethod
    def set_frozen_time(cls, dt):
        """Set the frozen datetime (or None to clear)."""
        obj, created = cls.objects.get_or_create(pk=1)
        obj.frozen_datetime = dt
        obj.save()

    class Meta:
        verbose_name = "Time Override"
        verbose_name_plural = "Time Overrides"


class AcademicYear(models.Model):
    name = models.CharField(
        max_length=20,
        unique=True,
    )

    start_date = models.DateField()
    end_date = models.DateField()

    is_current = models.BooleanField(
        default=False,
    )

    class Meta:
        ordering = ["-name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="only_one_current_academic_year",
            ),
        ]

    def clean(self):
        super().clean()

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError(
                    "Academic year end date must be after the start date."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Semester(models.Model):
    PERIOD_CHOICES = [
        (1, "Semester Period 1"),
        (2, "Semester Period 2"),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="semesters",
    )

    number = models.PositiveSmallIntegerField(
        choices=PERIOD_CHOICES,
    )

    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-academic_year__name", "number"]

        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "number"],
                name="unique_semester_period_per_year",
            ),
        ]

    def clean(self):
        super().clean()

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError(
                    "Semester end date must be after the start date."
                )

        if self.academic_year_id:
            if (
                self.start_date
                and self.academic_year.start_date
                and self.start_date < self.academic_year.start_date
            ):
                raise ValidationError(
                    "Semester cannot start before the academic year."
                )

            if (
                self.end_date
                and self.academic_year.end_date
                and self.end_date > self.academic_year.end_date
            ):
                raise ValidationError(
                    "Semester cannot end after the academic year."
                )

    @property
    def is_active(self):
        from school.utils.time_utils import get_current_date

        today = get_current_date()
        return self.start_date <= today <= self.end_date

    @property
    def is_upcoming(self):
        from school.utils.time_utils import get_current_date

        return self.start_date > get_current_date()

    @property
    def is_completed(self):
        from school.utils.time_utils import get_current_date

        return self.end_date < get_current_date()

    @property
    def status(self):
        if self.is_active:
            return "ACTIVE"

        if self.is_upcoming:
            return "UPCOMING"

        return "COMPLETED"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.academic_year.name} - Semester {self.number}"


class Program(models.Model):
    CATEGORY_CHOICES = [
        ("NC", "National Certificate"),
        ("NQ", "National Qualification"),
        ("OTHER", "Other"),
    ]

    code = models.CharField(
        max_length=30,
        unique=True,
    )

    name = models.CharField(
        max_length=150,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    duration_years = models.PositiveSmallIntegerField()

    category = models.CharField(
        max_length=10,
        choices=CATEGORY_CHOICES,
        default="OTHER",
    )

    active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()

        if self.duration_years < 1:
            raise ValidationError(
                "Program duration must be at least one year."
            )

    @property
    def total_semesters(self):
        return self.duration_years * 2

    def __str__(self):
        return f"{self.code} - {self.name}"


class FeeStructure(models.Model):
    """
    Defines what a particular program/year level owes
    during a specific academic semester period.
    """

    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name="fee_structures",
    )

    year_level = models.PositiveSmallIntegerField()

    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name="fee_structures",
    )

    class Meta:
        ordering = [
            "program",
            "year_level",
            "semester__academic_year__name",
            "semester__number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "program",
                    "year_level",
                    "semester",
                ],
                name="unique_program_year_level_semester_fee_structure",
            ),
        ]

    def clean(self):
        super().clean()

        if self.year_level < 1:
            raise ValidationError(
                "Year level must be at least 1."
            )

        if self.program_id:
            if self.year_level > self.program.duration_years:
                raise ValidationError(
                    "Year level cannot exceed the program duration."
                )

    @property
    def program_semester_number(self):
        return ((self.year_level - 1) * 2) + self.semester.number

    def __str__(self):
        return (
            f"{self.program} - "
            f"Year {self.year_level} - "
            f"Semester {self.program_semester_number} - "
            f"{self.semester.academic_year.name}"
        )


class FeeStructureItem(models.Model):
    fee_structure = models.ForeignKey(
        FeeStructure,
        on_delete=models.CASCADE,
        related_name="items",
    )

    name = models.CharField(
        max_length=100,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["fee_structure", "name"],
                name="unique_fee_item_per_structure",
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.amount}"


class Student(models.Model):
    ACTIVE = "ACTIVE"
    DEFERRED = "DEFERRED"
    WITHDRAWN = "WITHDRAWN"
    COMPLETED = "COMPLETED"

    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (DEFERRED, "Deferred"),
        (WITHDRAWN, "Withdrawn"),
        (COMPLETED, "Completed"),
    ]

    student_number = models.CharField(
        max_length=30,
        unique=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    national_id = models.CharField(
        max_length=100,
    )

    last_name = models.CharField(
        max_length=100,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    gender = models.CharField(
        max_length=20,
        blank=True,
    )

    guardian_name = models.CharField(
        max_length=150,
        blank=True,
    )

    guardian_phone = models.CharField(
        max_length=30,
        blank=True,
    )

    student_phone = models.CharField(
        max_length=30,
        blank=True ,
    )

    address = models.TextField(
        blank=True,
    )

    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name="students",
    )

    intake_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="students",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ACTIVE,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "last_name",
            "first_name",
        ]

    def __str__(self):
        return (
            f"{self.student_number} - "
            f"{self.first_name} "
            f"{self.last_name}"
        )

    def get_current_enrollment(self, today=None):
        """
        Determine the student's current enrollment based on priority:
        1. Currently active semester (today between start_date and end_date)
        2. Next upcoming semester (earliest start_date in the future)
        3. Most recent past semester (latest end_date)
        Returns None if no active enrollments exist.
        """
        from school.utils.time_utils import get_current_date
        
        today = today or get_current_date()
        
        # Get all active enrollments with semester data
        enrollments = self.enrollments.filter(
            status=Enrollment.ACTIVE
        ).select_related('semester')
        
        # 1. Currently active
        for e in enrollments:
            if e.semester.start_date <= today <= e.semester.end_date:
                return e
        
        # 2. Future (next upcoming) - earliest start_date first
        future = enrollments.filter(semester__start_date__gt=today).order_by('semester__start_date')
        if future.exists():
            return future.first()
        
        # 3. Past (most recent) - latest end_date first
        past = enrollments.order_by('-semester__end_date')
        return past.first() if past.exists() else None


class StudentStatusLog(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="status_logs",
    )

    status = models.CharField(
        max_length=20,
        choices=Student.STATUS_CHOICES,
    )

    date_changed = models.DateTimeField(
        auto_now_add=True,
    )

    note = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["-date_changed"]

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.get_status_display()} - "
            f"{self.date_changed}"
        )


class Enrollment(models.Model):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    DEFERRED = "DEFERRED"
    WITHDRAWN = "WITHDRAWN"

    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (COMPLETED, "Completed"),
        (DEFERRED, "Deferred"),
        (WITHDRAWN, "Withdrawn"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    year_level = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ACTIVE,
    )

    enrolled_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-semester__academic_year__name", "-semester__number"]

        constraints = [
            models.UniqueConstraint(
                fields=["student", "semester"],
                name="student_can_only_enroll_once_per_semester",
            ),
        ]

    @property
    def program_semester_number(self):
        return ((self.year_level - 1) * 2) + self.semester.number

    def clean(self):
        super().clean()

        if self.program_id and self.year_level > self.program.duration_years:
            raise ValidationError(
                "Year level cannot exceed the program duration."
            )

        if self.program_id and self.student_id:
            if self.student.program_id != self.program_id:
                raise ValidationError(
                    "Enrollment program must match the student's program."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.program} - "
            f"Semester {self.program_semester_number}"
        )


class StudentCharge(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="charges",
    )

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.PROTECT,
        related_name="charges",
    )

    fee_item = models.ForeignKey(
        FeeStructureItem,
        on_delete=models.PROTECT,
        related_name="student_charges",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "enrollment", "fee_item"],
                name="unique_student_enrollment_fee_item",
            ),
        ]


class Payment(models.Model):
    CASH = "CASH"
    BANK = "BANK"
    ECOCASH = "ECOCASH"
    OTHER = "OTHER"

    PAYMENT_METHODS = [
        (CASH, "Cash"),
        (BANK, "Bank"),
        (ECOCASH, "EcoCash"),
        (OTHER, "Other"),
    ]

    receipt_number = models.CharField(
        max_length=50,
        unique=True,
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    payment_date = models.DateField()

    method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default=CASH,
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-payment_date",
            "-id",
        ]

    def __str__(self):
        return self.receipt_number


def student_balance(student, semester):
    charged = (
        student.charges
        .filter(enrollment__semester=semester)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    paid = (
        student.payments
        .filter(semester=semester)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    return charged - paid


def semester_financials(semester):
    """Return charged/paid/outstanding/collection_rate for a semester."""
    charged = StudentCharge.objects.filter(
        fee_item__fee_structure__semester=semester
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    paid = Payment.objects.filter(semester=semester).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")

    return {
        "charged": charged,
        "paid": paid,
        "outstanding": charged - paid,
        "collection_rate": (paid / charged * 100) if charged > 0 else 0,
    }


def unconfigured_fee_structures(semester):
    """Return list of (program, year_level) pairs missing fee structure for semester."""
    configured_pairs = set(
        FeeStructure.objects.filter(semester=semester).values_list(
            "program_id", "year_level"
        )
    )
    missing = []
    for program in Program.objects.filter(active=True):
        for year_level in range(1, program.duration_years + 1):
            if (program.id, year_level) not in configured_pairs:
                missing.append({"program": program, "year_level": year_level})
    return missing


def outstanding_students(semester, limit=None):
    """Return queryset of students with outstanding balances for a semester."""
    from django.db.models import F, Q
    
    students = Student.objects.filter(
        enrollments__semester=semester,
        enrollments__status=Enrollment.ACTIVE,
    ).annotate(
        charged=Sum(
            "charges__amount",
            filter=Q(charges__fee_item__fee_structure__semester=semester),
        ),
        paid=Sum(
            "payments__amount",
            filter=Q(payments__semester=semester),
        ),
    ).filter(
        charged__gt=F("paid")
    ).order_by("-charged")
    
    if limit:
        students = students[:limit]
    return students


def payment_methods_breakdown(semester):
    """Return payment totals grouped by method for a semester."""
    return Payment.objects.filter(semester=semester).values("method").annotate(
        total=Sum("amount"),
        count=Sum("amount", default=0)
    ).order_by("-total")


def program_revenue(semester):
    """Return revenue grouped by program for a semester."""
    return StudentCharge.objects.filter(
        fee_item__fee_structure__semester=semester
    ).values(
        "fee_item__fee_structure__program__id",
        "fee_item__fee_structure__program__name",
        "fee_item__fee_structure__program__code"
    ).annotate(
        charged=Sum("amount"),
        paid=Sum(
            "student__payments__amount",
            filter=Q(student__payments__semester=semester)
        )
    ).order_by("-charged")


def daily_collections(date=None):
    """Return payments for a specific date (default today)."""
    from school.utils.time_utils import get_current_date
    if date is None:
        date = get_current_date()
    return Payment.objects.filter(payment_date=date).select_related(
        "student", "semester", "semester__academic_year"
    )


def enrollment_summary(program=None, intake_year=None, status=None):
    """Return enrollment counts grouped by program/intake_year/status."""
    from django.db.models import Count
    
    students = Student.objects.all()
    if program:
        students = students.filter(program=program)
    if intake_year:
        students = students.filter(intake_year=intake_year)
    if status:
        students = students.filter(status=status.upper())
    
    return students.values(
        "program__id", "program__name", "program__code",
        "intake_year__id", "intake_year__name",
        "status"
    ).annotate(count=Count("id")).order_by("program__name", "intake_year__name", "status")


def student_status_history(student=None, start_date=None, end_date=None):
    """Return StudentStatusLog entries with optional filters."""
    logs = StudentStatusLog.objects.select_related("student", "student__program")
    if student:
        logs = logs.filter(student=student)
    if start_date:
        logs = logs.filter(date_changed__date__gte=start_date)
    if end_date:
        logs = logs.filter(date_changed__date__lte=end_date)
    return logs.order_by("-date_changed")