from decimal import Decimal
from django.forms import inlineformset_factory
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

class AcademicYear(models.Model):

    name = models.CharField(
        max_length=20,
        unique=True,
    )

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
            )
        ]

    def __str__(self):
        return self.name

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Semester(models.Model):

    SEMESTER_CHOICES = [
        (1, "Semester 1"),
        (2, "Semester 2"),
        (3, "Semester 3"),
        (4, "Semester 4"),
    ]

    MONTH_CHOICES = [
        (1, "January"), (2, "February"), (3, "March"),
        (4, "April"), (5, "May"), (6, "June"),
        (7, "July"), (8, "August"), (9, "September"),
        (10, "October"), (11, "November"), (12, "December"),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="semesters",
    )

    number = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES,
    )

    start_month = models.PositiveSmallIntegerField(choices=MONTH_CHOICES)
    end_month = models.PositiveSmallIntegerField(choices=MONTH_CHOICES)

    class Meta:
        ordering = ["-academic_year__name", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "number"],
                name="unique_semester_number_per_year",
            ),
        ]

    def _month_sequence(self):
        """
        Returns the ordered list of months this semester spans,
        handling wrap-around (e.g. Nov -> Feb crosses year-end).
        """
        if self.start_month <= self.end_month:
            return list(range(self.start_month, self.end_month + 1))
        # wraps past December into the new year
        return list(range(self.start_month, 13)) + list(range(1, self.end_month + 1))

    def clean(self):
        super().clean()

        if self.start_month and self.end_month and self.start_month == self.end_month:
            raise ValidationError("Start month and end month cannot be the same.")

        if self.academic_year_id and self.start_month and self.end_month:
            my_months = set(self._month_sequence())

            siblings = Semester.objects.filter(
                academic_year=self.academic_year
            ).exclude(pk=self.pk)

            for other in siblings:
                if my_months & set(other._month_sequence()):
                    raise ValidationError(
                        f"These months overlap with {other} "
                        f"({other.get_start_month_display()} – {other.get_end_month_display()})."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def status(self):
        today = timezone.localdate()
        current_month = today.month
        return "ACTIVE" if current_month in self._month_sequence() else (
            "UPCOMING" if self._is_upcoming(current_month) else "COMPLETED"
        )

    def _is_upcoming(self, current_month):
        # Rough heuristic: if we haven't reached start_month yet this cycle
        seq = self._month_sequence()
        return current_month not in seq and seq and current_month < seq[0]

    @property
    def status_label(self):
        return {
            "UPCOMING": "Upcoming",
            "ACTIVE": "Active",
            "COMPLETED": "Completed",
        }[self.status]

    def __str__(self):
        return (
            f"{self.academic_year.name} - "
            f"Semester {self.number} "
            f"({self.get_start_month_display()}–{self.get_end_month_display()})"
        )
    
class Course(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True,
    )

    code = models.CharField(
        max_length=30,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class FeeItem(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    # Default/reference amount.
    # The actual semester amount lives on SemesterFee.
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class SemesterFee(models.Model):
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="fees",
    )
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["semester", "name"],
                name="unique_fee_name_per_semester",
            )
        ]

    def __str__(self):
        return f"{self.semester} - {self.name}"

class Student(models.Model):

    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    NOT_SPECIFIED = "NOT_SPECIFIED"

    GENDER_CHOICES = [
        (MALE, "Male"),
        (FEMALE, "Female"),
        (OTHER, "Other"),
        (NOT_SPECIFIED, "Prefer not to say"),
    ]

    student_number = models.CharField(
        max_length=30,
        unique=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    middle_name = models.CharField(
        max_length=100,
        blank=True,
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
        choices=GENDER_CHOICES,
        default=NOT_SPECIFIED,
    )

    guardian_name = models.CharField(
        max_length=150,
        blank=True,
    )

    guardian_phone = models.CharField(
        max_length=30,
        blank=True,
    )

    address = models.TextField(
        blank=True,
    )

    active = models.BooleanField(
        default=True,
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
    
    @property
    def current_course(self):
            """Return the course for the student's current active enrollment."""
            today = timezone.localdate()
            enrollment = self.enrollments.filter(
                status=Enrollment.ACTIVE,
                semester__start_date__lte=today,
                semester__end_date__gte=today,
            ).select_related('course').first()
            return enrollment.course if enrollment else None
    
    @property
    def current_course_name(self):
            course = self.current_course
            return course.name if course else "—"


class Enrollment(models.Model):

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"

    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (COMPLETED, "Completed"),
        (WITHDRAWN, "Withdrawn"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ACTIVE,
    )

    enrolled_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-enrolled_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "semester",
                ],
                name="student_can_only_enroll_once_per_semester",
            )
        ]

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.course} - "
            f"{self.semester}"
        )


class StudentCharge(models.Model):

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="charges",
    )

    semester_fee = models.ForeignKey(
        SemesterFee,
        on_delete=models.PROTECT,
        related_name="charges",
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
                fields=[
                    "student",
                    "semester_fee",
                ],
                name="unique_student_semester_fee",
            )
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
        .filter(
            semester_fee__semester=semester
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    paid = (
        student.payments
        .filter(
            semester=semester
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    return charged - paid