import random
from decimal import Decimal
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from school.models import (
    AcademicYear,
    Semester,
    Program,
    Student,
    StudentStatusLog,
    Enrollment,
    FeeStructure,
    FeeStructureItem,
    StudentCharge,
    Payment,
)
from school.views import create_academic_year_enrollments

try:
    from faker import Faker
    fake = Faker()
    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False


class Command(BaseCommand):
    help = "Seed 60 students enrolled in 2027 Semester 1 Year 1 with realistic fee payments."

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=60,
            help='Number of students to create (default: 60)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing students before seeding'
        )

    def handle(self, *args, **options):
        count = options['count']
        clear = options['clear']

        # Get 2027 Semester 1
        try:
            semester = Semester.objects.get(number=1, academic_year__name='2027')
        except Semester.DoesNotExist:
            self.stderr.write(self.style.ERROR("2027 Semester 1 not found. Please create it first."))
            return

        self.stdout.write(f"Using semester: {semester}")

        # Get all active programs
        programs = list(Program.objects.filter(active=True))
        if not programs:
            self.stderr.write(self.style.ERROR("No active programs found."))
            return

        self.stdout.write(f"Available programs: {[p.name for p in programs]}")

        # Verify fee structures exist for Year 1 for all programs
        for program in programs:
            fs = FeeStructure.objects.filter(program=program, year_level=1, semester=semester).first()
            if not fs:
                self.stdout.write(self.style.WARNING(f"WARNING: No fee structure for {program} Year 1 in {semester}"))
            else:
                items = list(fs.items.all().values_list('name', 'amount'))
                self.stdout.write(f"  {program} Year 1 fees: {items}")

        if clear:
            self.stdout.write("Clearing existing students and related records...")
            # Delete in order to respect protected foreign keys
            Payment.objects.all().delete()
            StudentCharge.objects.all().delete()
            StudentStatusLog.objects.all().delete()
            Enrollment.objects.all().delete()
            Student.objects.all().delete()

        # Helper functions
        def random_name():
            if HAS_FAKER:
                return fake.first_name(), fake.last_name()
            first_names = ['John', 'Jane', 'Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Henry', 
                          'Olivia', 'Noah', 'Liam', 'Emma', 'Oliver', 'Sophia', 'Elijah', 'Isabella', 'James', 'Mia',
                          'William', 'Charlotte', 'Benjamin', 'Amelia', 'Lucas', 'Harper', 'Mason', 'Evelyn', 'Alexander', 'Abigail',
                          'Michael', 'Emily', 'Daniel', 'Elizabeth', 'Matthew', 'Sofia', 'David', 'Avery', 'Joseph', 'Ella',
                          'Samuel', 'Scarlett', 'Andrew', 'Victoria', 'Joshua', 'Madison', 'Christopher', 'Luna', 'Anthony', 'Grace']
            last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Martinez', 'Hernandez',
                         'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee',
                         'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker',
                         'Young', 'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores', 'Green']
            return random.choice(first_names), random.choice(last_names)

        def random_student_number():
            year = 2027
            seq = random.randint(1000, 9999)
            return f"BSOFT{year}-{seq:04d}"

        def random_date_of_birth():
            start = datetime(2000, 1, 1).date()
            end = datetime(2010, 12, 31).date()
            return start + timedelta(days=random.randint(0, (end - start).days))

        def random_phone():
            return f"0{random.randint(70, 78)}{random.randint(1000000, 9999999)}"

        def random_address():
            if HAS_FAKER:
                return fake.address()
            streets = ['Main St', 'Oak Ave', 'Pine Rd', 'Maple Ln', 'Cedar Blvd', 'Elm St', 'Park Ave', 'Lake Dr', 'Hill Rd', 'Valley View']
            cities = ['Harare', 'Bulawayo', 'Mutare', 'Gweru', 'Kwekwe', 'Masvingo', 'Chinhoyi', 'Marondera', 'Bindura', 'Rusape']
            suburbs = ['Avondale', 'Mount Pleasant', 'Highlands', 'Borrowdale', 'Mabelreign', 'Southerton', 'Mbare', 'Warren Park', 'Budiriro', 'Glen View']
            return f"{random.randint(1, 999)} {random.choice(streets)}, {random.choice(suburbs)}, {random.choice(cities)}"

        def random_national_id():
            if random.random() > 0.3:
                prefix = random.choice(['', 'M.', 'A.', 'K.', 'N.', 'P.'])
                return f"{prefix}{random.randint(100000, 999999)}{random.choice(['A', 'B', 'C', 'D', 'E'])}"
            return ''

        # Payment distribution: 20% full, 30% partial (50-90%), 30% minimal (10-49%), 20% none
        def get_payment_percent():
            r = random.random()
            if r < 0.20:
                return 1.0  # Full payment
            elif r < 0.50:
                return round(random.uniform(0.50, 0.90), 2)  # Partial - majority paid
            elif r < 0.80:
                return round(random.uniform(0.10, 0.49), 2)  # Minimal payment
            else:
                return 0.0  # No payment

        created = 0
        for i in range(count):
            first, last = random_name()
            student_number = random_student_number()
            
            # Ensure unique student number
            while Student.objects.filter(student_number=student_number).exists():
                student_number = random_student_number()

            # Random program assignment (weighted slightly towards Fabrication)
            program_weights = [0.30, 0.40, 0.30]  # Electrical Power, Fabrication, Milwight
            program = random.choices(programs, weights=program_weights, k=1)[0]

            with transaction.atomic():
                # Create student
                student = Student.objects.create(
                    student_number=student_number,
                    first_name=first,
                    last_name=last,
                    national_id=random_national_id(),
                    date_of_birth=random_date_of_birth(),
                    gender=random.choice(['MALE', 'FEMALE', 'OTHER', 'NOT_SPECIFIED']),
                    guardian_name=f"{random.choice(['Mr.', 'Mrs.', 'Ms.'])} {random_name()[0]} {random_name()[1]}" if random.random() > 0.3 else '',
                    guardian_phone=random_phone() if random.random() > 0.4 else '',
                    student_phone=random_phone() if random.random() > 0.5 else '',
                    address=random_address() if random.random() > 0.3 else '',
                    program=program,
                    intake_year=semester.academic_year,
                    status=Student.ACTIVE,
                )

                # Create enrollments and charges for all semesters in the academic year
                create_academic_year_enrollments(
                    student=student,
                    start_semester=semester,
                    start_year_level=1,
                    program=student.program
                )
                self.stdout.write(f"  {student_number}: Created academic year enrollments")

                # Create payment based on distribution (using Semester 1 charges)
                # Get total charged for Semester 1
                sem1_enrollment = student.enrollments.filter(semester=semester).first()
                total_charged = Decimal('0')
                if sem1_enrollment:
                    total_charged = student.charges.filter(enrollment=sem1_enrollment).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                payment_percent = get_payment_percent()
                if payment_percent > 0 and total_charged > 0:
                    amount = (total_charged * Decimal(str(payment_percent))).quantize(Decimal('0.01'))
                    if amount < Decimal('1.00'):
                        amount = Decimal('1.00')
                    
                    receipt = f"RCP-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
                    while Payment.objects.filter(receipt_number=receipt).exists():
                        receipt = f"RCP-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

                    # Payment date within the semester
                    days_into_semester = random.randint(0, (semester.end_date - semester.start_date).days)
                    payment_date = semester.start_date + timedelta(days=days_into_semester)
                    
                    method = random.choice([Payment.CASH, Payment.BANK, Payment.ECOCASH, Payment.OTHER])
                    
                    Payment.objects.create(
                        receipt_number=receipt,
                        student=student,
                        semester=semester,
                        amount=amount,
                        payment_date=payment_date,
                        method=method,
                        reference=f"REF{random.randint(100000, 999999)}" if random.random() > 0.5 else '',
                        notes=f"Payment for {semester} - {program.name} Year 1" if random.random() > 0.7 else '',
                    )
                    self.stdout.write(f"  {student_number}: Payment ${amount} ({payment_percent*100:.0f}%) via {method}")

                created += 1
                
                if created % 10 == 0:
                    self.stdout.write(f"Created {created}/{count} students...")

        # Summary
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully created {created} students."))
        
        # Print payment summary
        total_students = Student.objects.count()
        students_with_payments = Student.objects.filter(payments__isnull=False).distinct().count()
        total_payments = Payment.objects.filter(semester=semester).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_charged_all = StudentCharge.objects.filter(enrollment__semester=semester).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        self.stdout.write(f"\n--- Summary for {semester} ---")
        self.stdout.write(f"Total students: {total_students}")
        self.stdout.write(f"Students with payments: {students_with_payments}")
        self.stdout.write(f"Total charged: ${total_charged_all}")
        self.stdout.write(f"Total paid: ${total_payments}")
        if total_charged_all > 0:
            self.stdout.write(f"Collection rate: {(total_payments/total_charged_all)*100:.1f}%")