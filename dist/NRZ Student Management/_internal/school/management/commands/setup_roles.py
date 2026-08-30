from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):
    help = "Create default groups and assign permissions"

    def handle(self, *args, **options):
        # Registrar group - can register students
        registrar, created = Group.objects.get_or_create(name="Registrar")
        if created:
            self.stdout.write(self.style.SUCCESS("Created 'Registrar' group"))
        else:
            self.stdout.write("'Registrar' group already exists")

        registrar_perms = Permission.objects.filter(
            codename__in=[
                "add_student",
                "view_student",
            ]
        )
        registrar.permissions.set(registrar_perms)
        self.stdout.write(f"Assigned {registrar_perms.count()} permissions to 'Registrar' group")

        # Finance group - can view financial reports and record payments
        finance, created = Group.objects.get_or_create(name="Finance")
        if created:
            self.stdout.write(self.style.SUCCESS("Created 'Finance' group"))
        else:
            self.stdout.write("'Finance' group already exists")

        finance_perms = Permission.objects.filter(
            codename__in=[
                "can_view_financial_reports",
                "can_view_outstanding_reports",
                "can_record_payments",
                "view_student",
                "view_auditlog",
            ]
        )
        finance.permissions.set(finance_perms)
        self.stdout.write(f"Assigned {finance_perms.count()} permissions to 'Finance' group")

        # Academic group - can manage programs, semesters, fee structures
        academic, created = Group.objects.get_or_create(name="Academic")
        if created:
            self.stdout.write(self.style.SUCCESS("Created 'Academic' group"))
        else:
            self.stdout.write("'Academic' group already exists")

        academic_perms = Permission.objects.filter(
            codename__in=[
                "view_program",
                "add_program",
                "view_academicyear",
                "view_semester",
                "add_semester",
                "change_semester",
                "view_feestructure",
                "add_feestructure",
                "change_feestructure",
            ]
        )
        academic.permissions.set(academic_perms)
        self.stdout.write(f"Assigned {academic_perms.count()} permissions to 'Academic' group")

        self.stdout.write(self.style.SUCCESS("All groups configured successfully"))