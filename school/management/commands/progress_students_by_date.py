# from datetime import datetime
# from django.core.management.base import BaseCommand
# from django.db import transaction
# from django.db.models import Sum
# from django.utils import timezone

# from school.models import (
#     Semester,
#     Enrollment,
#     Student,
#     StudentCharge,
#     Payment,
# )
# from school.views import create_academic_year_enrollments
# from school.utils.time_utils import get_current_date   # 👈 new import


# class Command(BaseCommand):
#     help = "Automatically progress students whose semester has ended to the next semester."

#     def add_arguments(self, parser):
#         parser.add_argument(
#             '--dry-run',
#             action='store_true',
#             help='Show what would be done without making changes.',
#         )
#         parser.add_argument(
#             '--date',
#             type=str,
#             help='Override "today" date (YYYY-MM-DD). If not provided, uses system date (or frozen time if enabled).',
#         )

#     def handle(self, *args, **options):
#         dry_run = options['dry_run']
#         date_str = options.get('date')

#         # Determine the "today" date
#         if date_str:
#             today = datetime.strptime(date_str, '%Y-%m-%d').date()
#             self.stdout.write(self.style.WARNING(f"Using explicit date: {today}"))
#         else:
#             today = get_current_date()   # uses frozen time if enabled, else real system date
#             if hasattr(today, 'tzinfo'):  # ensure it's a date, not datetime
#                 today = today.date()
#             self.stdout.write(f"Using date from system/frozen: {today}")

#         if dry_run:
#             self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

#         # Find all semesters that have ended (end_date < today)
#         ended_semesters = Semester.objects.filter(
#             end_date__lt=today
#         ).order_by('end_date')

#         if not ended_semesters.exists():
#             self.stdout.write(self.style.SUCCESS("No ended semesters found. Nothing to do."))
#             return

#         self.stdout.write(f"Found {ended_semesters.count()} ended semester(s):")
#         for sem in ended_semesters:
#             self.stdout.write(f"  - {sem} (ended {sem.end_date})")

#         total_progressed = 0
#         total_completed = 0
#         total_errors = 0
#         students_with_balance = []

#         for source_semester in ended_semesters:
#             # Find the next chronological semester
#             target_semester = Semester.objects.filter(
#                 start_date__gt=source_semester.start_date
#             ).order_by('start_date').first()

#             if not target_semester:
#                 self.stdout.write(
#                     self.style.ERROR(f"No next semester found after {source_semester}. Skipping.")
#                 )
#                 continue

#             # Get active enrollments from the source semester
#             active_enrollments = Enrollment.objects.filter(
#                 semester=source_semester,
#                 status=Enrollment.ACTIVE,
#                 student__status=Student.ACTIVE,
#             ).select_related('student', 'program')

#             if not active_enrollments.exists():
#                 self.stdout.write(f"  No active students in {source_semester}")
#                 continue

#             self.stdout.write(f"  Processing {active_enrollments.count()} students from {source_semester} -> {target_semester}")

#             for current in active_enrollments:
#                 student = current.student
#                 program = current.program

#                 # Calculate next year level
#                 if source_semester.number == 1:
#                     next_year_level = current.year_level
#                 else:
#                     next_year_level = current.year_level + 1

#                 # Check if student completed the program
#                 if next_year_level > program.duration_years:
#                     if not dry_run:
#                         with transaction.atomic():
#                             student.status = Student.COMPLETED
#                             student.save(update_fields=['status'])
#                             current.status = Enrollment.COMPLETED
#                             current.save(update_fields=['status'])

#                             from school.models import StudentStatusLog
#                             StudentStatusLog.objects.create(
#                                 student=student,
#                                 status=Student.COMPLETED,
#                                 note=f"Completed {program.name} after {source_semester} via auto-progression.",
#                             )
#                     total_completed += 1
#                     self.stdout.write(f"    {student.student_number}: COMPLETED program")
#                     continue

#                 # Check outstanding balance for warning
#                 charged = StudentCharge.objects.filter(
#                     enrollment=current
#                 ).aggregate(total=Sum('amount'))['total'] or 0
#                 paid = Payment.objects.filter(
#                     student=student, semester=source_semester
#                 ).aggregate(total=Sum('amount'))['total'] or 0
#                 balance = charged - paid

#                 if balance > 0:
#                     students_with_balance.append({
#                         'student': student,
#                         'semester': source_semester,
#                         'balance': balance,
#                     })

#                 # Create new enrollment (or get existing)
#                 if not dry_run:
#                     with transaction.atomic():
#                         enrollment, created = Enrollment.objects.get_or_create(
#                             student=student,
#                             semester=target_semester,
#                             defaults={
#                                 'program': program,
#                                 'year_level': next_year_level,
#                                 'status': Enrollment.ACTIVE,
#                             },
#                         )

#                         if created:
#                             # Mark old enrollment as completed
#                             current.status = Enrollment.COMPLETED
#                             current.save(update_fields=['status'])

#                             # Create enrollments and charges for all semesters in the target academic year
#                             create_academic_year_enrollments(
#                                 student=student,
#                                 start_semester=target_semester,
#                                 start_year_level=next_year_level,
#                                 program=program
#                             )

#                             total_progressed += 1
#                             self.stdout.write(f"    {student.student_number}: Progressed to {target_semester} (Year {next_year_level})")
#                         else:
#                             # Already enrolled in target – mark source as completed
#                             current.status = Enrollment.COMPLETED
#                             current.save(update_fields=['status'])
#                             self.stdout.write(f"    {student.student_number}: Already enrolled in {target_semester} (marked old as completed)")
#                 else:
#                     total_progressed += 1
#                     self.stdout.write(f"    {student.student_number}: Would progress to {target_semester} (Year {next_year_level})")

#         # Summary
#         self.stdout.write(self.style.SUCCESS("\n=== PROGRESSION SUMMARY ==="))
#         self.stdout.write(f"Students progressed: {total_progressed}")
#         self.stdout.write(f"Students completed program: {total_completed}")
#         self.stdout.write(f"Students with outstanding balance: {len(students_with_balance)}")
#         self.stdout.write(f"Errors: {total_errors}")

#         if students_with_balance:
#             self.stdout.write(self.style.WARNING("\nStudents with outstanding balances (need review):"))
#             for s in students_with_balance:
#                 self.stdout.write(f"  {s['student'].student_number} - {s['student'].first_name} {s['student'].last_name} "
#                                  f"({s['semester']}): ${s['balance']}")

#         self.stdout.write(self.style.SUCCESS(f"\nAuto-progression completed at {timezone.now()}"))