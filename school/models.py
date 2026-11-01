from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q, Sum
from django.utils import timezone


def current_enrollment(enrollments, today=None):
    """Pick the enrollment that represents a student right now.

    Priority: a semester running today, then the next semester starting, then
    the most recent one that has ended. Pass an iterable of *active*
    enrollments with their semesters loaded to avoid extra queries.
    """
    from school.utils.time_utils import get_current_date

    today = today or get_current_date()
    enrollments = list(enrollments)

    for enrollment in enrollments:
        if enrollment.semester.start_date <= today <= enrollment.semester.end_date:
            return enrollment

    future = sorted(
        (e for e in enrollments if e.semester.start_date > today),
        key=lambda e: e.semester.start_date,
    )
    if future:
        return future[0]

    past = sorted(
        (e for e in enrollments if e.semester.end_date < today),
        key=lambda e: e.semester.end_date,
        reverse=True,
    )
    return past[0] if past else None


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
        default="NC",
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

        if self.year_level is not None and self.year_level < 1:
            raise ValidationError(
                "Year level must be at least 1."
            )

        if self.program_id and self.year_level is not None:
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
        blank=True,
        default="",
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
        choices=[
            ('MALE', 'Male'),
            ('FEMALE', 'Female'),
        ],
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
        permissions = [
            ("can_view_financial_reports", "Can view financial reports"),
            ("can_view_outstanding_reports", "Can view outstanding balances"),
            ("can_record_payments", "Can record payments"),
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
        enrollments = self.enrollments.filter(
            status=Enrollment.ACTIVE
        ).select_related('semester')

        return current_enrollment(enrollments, today)


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
        blank=True,
        help_text="Leave blank to allocate the next receipt number for the payment date.",
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

    def save(self, *args, **kwargs):
        """Allocate a receipt number when one was not supplied.

        Every payment needs a unique number, but operators should not have to
        invent one. Numbers are allocated per payment date (see
        ``school.utils.receipts``) and retried a few times so two tills saving
        at the same moment cannot silently reuse a number.
        """
        if self.receipt_number:
            return super().save(*args, **kwargs)

        from school.utils.receipts import next_receipt_number
        from school.utils.time_utils import get_current_date

        payment_date = self.payment_date or get_current_date()

        for _ in range(5):
            self.receipt_number = next_receipt_number(payment_date)
            try:
                # A savepoint keeps the outer transaction usable when the
                # unique constraint rejects a number that was just taken.
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.receipt_number = ""

        raise ValidationError(
            "A unique receipt number could not be allocated. Please try again."
        )


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
    """Return (program, year_level) pairs without a set-up fee structure.

    A structure only counts as set up once it has at least one fee item;
    an empty structure is treated the same as a missing one everywhere.
    """
    configured_pairs = set(
        FeeStructure.objects.filter(
            semester=semester,
            items__isnull=False,
        ).values_list(
            "program_id", "year_level"
        ).distinct()
    )
    missing = []
    for program in Program.objects.filter(active=True):
        for year_level in range(1, program.duration_years + 1):
            if (program.id, year_level) not in configured_pairs:
                missing.append({"program": program, "year_level": year_level})
    return missing


def outstanding_students(semester, limit=None):
    """Return queryset of students with outstanding balances for a semester."""
    from django.db.models import Q, Subquery, OuterRef, Sum, F, Value
    from django.db.models.functions import Coalesce
    
    # Subquery for charges
    charges_subquery = StudentCharge.objects.filter(
        student=OuterRef('pk'),
        enrollment__semester=semester,
    ).values('student_id').annotate(
        total=Coalesce(Sum('amount'), Value(Decimal('0')))
    ).values('total')
    
    # Subquery for payments
    payments_subquery = Payment.objects.filter(
        student=OuterRef('pk'),
        semester=semester,
    ).values('student_id').annotate(
        total=Coalesce(Sum('amount'), Value(Decimal('0')))
    ).values('total')
    
    students = Student.objects.filter(
        enrollments__semester=semester,
    ).annotate(
        charged=Coalesce(Subquery(charges_subquery), Value(Decimal('0'))),
        paid=Coalesce(Subquery(payments_subquery), Value(Decimal('0'))),
    ).annotate(
        balance=F('charged') - F('paid')
    ).filter(
        balance__gt=Decimal('0')
    ).order_by('-balance')
    
    if limit:
        students = students[:limit]
    
    return students

def payment_methods_breakdown(semester):
    """Return payment totals and actual transaction counts by method."""
    from django.db.models import Count

    return Payment.objects.filter(semester=semester).values("method").annotate(
        total=Sum("amount"),
        count=Count("pk"),
    ).order_by("-total")


def program_revenue(semester):
    """Return charges by fee-structure trade and payments by student trade.

    The two grouped queries preserve the historic attribution rule while
    keeping query count independent of the number of trades.
    """
    charged_by_program = {
        row["fee_item__fee_structure__program_id"]: row
        for row in StudentCharge.objects.filter(
            fee_item__fee_structure__semester=semester,
        ).values(
            "fee_item__fee_structure__program_id",
            "fee_item__fee_structure__program__name",
            "fee_item__fee_structure__program__code",
        ).annotate(total=Sum("amount"))
    }
    paid_by_program = {
        row["student__program_id"]: row["total"]
        for row in Payment.objects.filter(semester=semester).values(
            "student__program_id",
        ).annotate(total=Sum("amount"))
    }

    result = []
    for program_id, row in charged_by_program.items():
        result.append({
            "fee_item__fee_structure__program__id": program_id,
            "fee_item__fee_structure__program__name": row["fee_item__fee_structure__program__name"],
            "fee_item__fee_structure__program__code": row["fee_item__fee_structure__program__code"],
            "charged": row["total"] or Decimal("0"),
            "paid": paid_by_program.pop(program_id, Decimal("0")),
        })
    # Keep payments without charges visible in the aggregate, so collected
    # totals still reconcile even when a trade has no billed fee structure.
    if paid_by_program:
        payment_trades = Program.objects.in_bulk(paid_by_program)
        for program_id, amount in paid_by_program.items():
            trade = payment_trades.get(program_id)
            if trade:
                result.append({
                    "fee_item__fee_structure__program__id": program_id,
                    "fee_item__fee_structure__program__name": trade.name,
                    "fee_item__fee_structure__program__code": trade.code,
                    "charged": Decimal("0"),
                    "paid": amount or Decimal("0"),
                })
    result.sort(key=lambda item: item["charged"], reverse=True)
    return result
def students_with_missing_details():
    """
    Returns active students with incomplete contact or address information.
    Missing details include: no guardian name, no student phone, no address, or no guardian phone.
    """
    from django.db.models import Q
    
    return Student.objects.filter(
        status=Student.ACTIVE
    ).filter(
        Q(guardian_name='') | 
        Q(student_phone='') | 
        Q(address='') | 
        Q(guardian_phone='')
    ).select_related('program').order_by('-created_at')


def daily_collections(date=None, start_date=None, end_date=None):
    """
    Return payments for a specific date or date range.
    If start_date and end_date are provided, they take precedence.
    Otherwise, return payments for a specific date (default today).
    """
    from school.utils.time_utils import get_current_date
    
    if start_date and end_date:
        # Date range filter
        return Payment.objects.filter(
            payment_date__gte=start_date,
            payment_date__lte=end_date
        ).select_related("student", "semester", "semester__academic_year")
    else:
        # Single date filter
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


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('REGISTER', 'Student Registration'),
        ('STATUS_CHANGE', 'Status Change'),
        ('PAYMENT', 'Payment Recorded'),
        ('WITHDRAWAL', 'Withdrawal Adjustment'),
        ('FEE_STRUCTURE', 'Fee Structure Change'),
        ('ENROLLMENT', 'Enrollment Change'),
        ('OTHER', 'Other'),
    ]

    CATEGORY_CHOICES = [
        ('STUDENT', 'Student'),
        ('FINANCIAL', 'Financial'),
        ('SYSTEM', 'System'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    student = models.ForeignKey(
        'Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='STUDENT')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_action_display()} by {self.user} at {self.timestamp}"


class BackupConfig(models.Model):
    """
    Singleton configuration for backup settings.
    """
    backup_path = models.CharField(
        max_length=500,
        default='',
        help_text="Absolute path to backup directory (e.g., /media/usb/backups or D:\\backups)"
    )
    auto_backup_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic daily backups"
    )
    retention_days = models.PositiveIntegerField(
        default=7,
        help_text="Number of days to keep backup files"
    )
    strict_mode = models.BooleanField(
        default=True,
        help_text="When ON, dashboard will alert if backup media is not available"
    )

    class Meta:
        verbose_name = "Backup Configuration"
        verbose_name_plural = "Backup Configuration"

    def __str__(self):
        return "Backup Configuration"

    @classmethod
    def get_config(cls):
        """Get or create the singleton config."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def get_backup_path(self):
        """Return the configured backup path, falling back to settings.BACKUP_DIR."""
        if self.backup_path:
            return self.backup_path
        from django.conf import settings
        return settings.BACKUP_DIR

    def is_backup_available(self):
        """Check if the backup path exists and is writable."""
        import os
        path = self.get_backup_path()
        if not path:
            return False
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            # Test writability by creating a temporary file
            test_file = os.path.join(path, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except Exception:
            return False