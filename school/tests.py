from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .forms import ProgramForm
from .models import (
    AcademicYear,
    Enrollment,
    FeeStructure,
    FeeStructureItem,
    Program,
    Semester,
    Student,
    StudentCharge,
    TimeOverride,
    unconfigured_fee_structures,
)
from .views import copy_fee_structures, fee_progress


class ProgramFormTests(TestCase):
    def test_program_form_defaults_to_national_certificate(self):
        form = ProgramForm()

        self.assertEqual(form.fields["category"].initial, "NC")


class ReminderListTests(TestCase):
    def test_reminders_are_paginated(self):
        intake_year = AcademicYear.objects.create(
            name="2025",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        program = Program.objects.create(
            code="NC-TEST",
            name="NC Test Program",
            description="",
            duration_years=2,
            category="NC",
        )

        for index in range(1, 22):
            Student.objects.create(
                student_number=f"ST{index:03d}",
                first_name=f"Student{index}",
                last_name="Test",
                guardian_name="",
                guardian_phone="",
                student_phone="",
                address="",
                program=program,
                intake_year=intake_year,
                status=Student.ACTIVE,
            )

        user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.client.force_login(user)

        response = self.client.get("/reminders/?page=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(len(response.context["page_obj"].object_list), 10)
        self.assertGreater(response.context["page_obj"].paginator.num_pages, 1)
