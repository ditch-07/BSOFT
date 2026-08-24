import random
from decimal import Decimal
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from school.models import (
    AcademicYear,
    Semester,
    Course,
    Student,
    Enrollment,
    SemesterFee,
    StudentCharge,
    Payment,
)

try:
    from faker import Faker
    fake = Faker()
    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False


class Command(BaseCommand):
    help = "Seed students using the exact registration flow (student + enrollment + charges)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=30,
            help='Number of students to create (default: 30)'
        )
        parser.add_argument(
            '--semester',
            type=int,
            help='ID of the semester to enroll students into (default: first active semester)'
        )
        parser.add_argument(
            '--course',
            type=int,
            help='ID of the course to enroll students into (default: random active course)'
        )
        parser.add_argument(
            '--with-payments',
            action='store_true',
            help='Also create random payments for some students'
        )

    def handle(self, *args, **options):
        count = options['count']
        semester_id = options.get('semester')
        course_id = options.get('course')
        with_payments = options['with_payments']

        # --- 1. Determine semester ---
        if semester_id:
            try:
                semester = Semester.objects.get(pk=semester_id)
            except Semester.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Semester with ID {semester_id} not found."))
                return
        else:
            semester = Semester.objects.filter(status=Semester.ACTIVE).first()
            if not semester:
                semester = Semester.objects.order_by('start_date').first()
            if not semester:
                self.stderr.write(self.style.ERROR("No semesters found. Please create at least one semester."))
                return
        self.stdout.write(f"Using semester: {semester}")

        # --- 2. Determine course ---
        if course_id:
            try:
                course = Course.objects.get(pk=course_id, active=True)
            except Course.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Active course with ID {course_id} not found."))
                return
        else:
            courses = list(Course.objects.filter(active=True))
            if not courses:
                self.stderr.write(self.style.ERROR("No active courses found. Please create at least one course."))
                return
            course = random.choice(courses)
        self.stdout.write(f"Using course: {course}")

        # --- 3. Ensure semester has fees (optional warning) ---
        fee_count = SemesterFee.objects.filter(semester=semester).count()
        if fee_count == 0:
            self.stdout.write(self.style.WARNING(f"WARNING: Semester {semester} has no fee items. Students will be enrolled but no charges created."))

        # --- 4. Helper functions for random data ---
        def random_name():
            if HAS_FAKER:
                return fake.first_name(), fake.last_name()
            first_names = ['John', 'Jane', 'Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Henry', 'Olivia', 'Noah']
            last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Martinez', 'Hernandez']
            return random.choice(first_names), random.choice(last_names)

        def random_student_number():
            year = random.randint(2020, 2026)
            seq = random.randint(1, 9999)
            return f"STU-{year}-{seq:04d}"

        def random_date_of_birth():
            start = datetime(2000, 1, 1).date()
            end = datetime(2010, 12, 31).date()
            return start + timedelta(days=random.randint(0, (end - start).days))

        def random_phone():
            return f"0{random.randint(70, 78)}{random.randint(1000000, 9999999)}"

        def random_address():
            if HAS_FAKER:
                return fake.address()
            streets = ['Main St', 'Oak Ave', 'Pine Rd', 'Maple Ln', 'Cedar Blvd', 'Elm St']
            cities = ['Harare', 'Bulawayo', 'Mutare', 'Gweru', 'Kwekwe', 'Masvingo']
            return f"{random.randint(1, 999)} {random.choice(streets)}, {random.choice(cities)}"

        # --- 5. Create students ---
        created = 0
        for i in range(count):
            first, last = random_name()
            student_number = random_student_number()
            # Ensure unique
            while Student.objects.filter(student_number=student_number).exists():
                student_number = random_student_number()

            with transaction.atomic():
                # 5a. Create student (same fields as StudentForm)
                student = Student.objects.create(
                    student_number=student_number,
                    first_name=first,
                    last_name=last,
                    national_id_=random.choice(['', 'M.', 'A.', 'K.', 'N.', 'P.']) if random.random() > 0.5 else '',
                    date_of_birth=random_date_of_birth(),
                    gender=random.choice(['MALE', 'FEMALE', 'OTHER', 'NOT_SPECIFIED']),
                    guardian_name=f"{random.choice(['Mr.', 'Mrs.', 'Ms.'])} {random_name()[0]} {random_name()[1]}" if random.random() > 0.3 else '',
                    guardian_phone=random_phone() if random.random() > 0.4 else '',
                    address=random_address() if random.random() > 0.3 else '',
                    active=True,
                )
                self.stdout.write(f"Created student: {student}")

                # 5b. Enroll (same as view: creates Enrollment with status=ACTIVE)
                enrollment = Enrollment.objects.create(
                    student=student,
                    course=course,
                    semester=semester,
                    status=Enrollment.ACTIVE,
                )
                self.stdout.write(f"  Enrolled in {semester} for {course}")

                # 5c. Create charges for all SemesterFee items of that semester
                semester_fees = SemesterFee.objects.filter(semester=semester)
                for sf in semester_fees:
                    # Check uniqueness (should not happen, but safe)
                    if StudentCharge.objects.filter(student=student, semester_fee=sf).exists():
                        continue
                    StudentCharge.objects.create(
                        student=student,
                        semester_fee=sf,
                        amount=sf.amount,
                    )
                    self.stdout.write(f"    Charged {sf.fee_item.name}: {sf.amount}")

                # 5d. Optionally create a random payment
                if with_payments and random.random() > 0.5:
                    total_charged = StudentCharge.objects.filter(
                        student=student,
                        semester_fee__semester=semester
                    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
                    if total_charged > 0:
                        percent = Decimal(random.uniform(0.1, 1.0))
                        amount = (total_charged * percent).quantize(Decimal('0.01'))
                        if amount < Decimal('1.00'):
                            amount = Decimal('1.00')
                        receipt = f"RCP-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
                        while Payment.objects.filter(receipt_number=receipt).exists():
                            receipt = f"RCP-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
                        Payment.objects.create(
                            receipt_number=receipt,
                            student=student,
                            semester=semester,
                            amount=amount,
                            payment_date=timezone.now().date() - timedelta(days=random.randint(0, 30)),
                            method=random.choice(['CASH', 'BANK', 'ECOCASH', 'OTHER']),
                            reference=f"REF{random.randint(100000, 999999)}" if random.random() > 0.5 else '',
                            notes=f"Payment for {semester}" if random.random() > 0.7 else '',
                        )
                        self.stdout.write(f"    Created payment: {receipt} for {amount}")

            created += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully created {created} students."))