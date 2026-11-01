from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

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


@override_settings(ENABLE_TIME_OVERRIDE=True)
class FeeTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        TimeOverride.objects.update_or_create(
            pk=1,
            defaults={
                "frozen_datetime": timezone.make_aware(
                    datetime(2026, 10, 27, 12, 0)
                )
            },
        )
        cls.year_2026 = AcademicYear.objects.create(
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        cls.year_2027 = AcademicYear.objects.create(
            name="2027",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
        )
        cls.source = Semester.objects.create(
            academic_year=cls.year_2026,
            number=1,
            start_date=date(2026, 1, 12),
            end_date=date(2026, 6, 30),
        )
        cls.completed = Semester.objects.create(
            academic_year=cls.year_2026,
            number=2,
            start_date=date(2026, 7, 15),
            end_date=date(2026, 9, 30),
        )
        cls.target = Semester.objects.create(
            academic_year=cls.year_2027,
            number=1,
            start_date=date(2027, 1, 12),
            end_date=date(2027, 4, 2),
        )
        cls.program = Program.objects.create(
            code="DPF",
            name="Digital Photography",
            duration_years=2,
            category="NC",
        )
        cls.short_program = Program.objects.create(
            code="SHORT",
            name="Short Trade",
            duration_years=1,
            category="NC",
        )
        cls.admin = get_user_model().objects.create_superuser(
            username="fee-admin",
            email="fee-admin@example.com",
            password="test-pass-123",
        )

    @classmethod
    def tearDownClass(cls):
        TimeOverride.objects.all().delete()
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(self.admin)

    def make_structure(self, semester, program, year_level, items):
        structure = FeeStructure.objects.create(
            semester=semester,
            program=program,
            year_level=year_level,
        )
        for name, amount in items:
            FeeStructureItem.objects.create(
                fee_structure=structure,
                name=name,
                amount=amount,
            )
        return structure

    def make_enrolled_student(
        self, number, program=None, year_level=1, semester=None
    ):
        program = program or self.program
        semester = semester or self.target
        student = Student.objects.create(
            student_number=number,
            first_name="Test",
            last_name=number,
            program=program,
            intake_year=self.year_2026,
        )
        enrollment = Enrollment.objects.create(
            student=student,
            program=program,
            semester=semester,
            year_level=year_level,
        )
        return student, enrollment


class FeeSetUpDefinitionTests(FeeTestBase):
    def test_empty_structure_does_not_count_as_set_up(self):
        self.make_structure(self.target, self.program, 1, [])
        progress = fee_progress(self.target)
        cell = next(
            cell for cell in progress["cells"]
            if cell["program"].pk == self.program.pk
            and cell["year_level"] == 1
        )
        self.assertFalse(cell["set_up"])
        unconfigured = {
            (row["program"].pk, row["year_level"])
            for row in unconfigured_fee_structures(self.target)
        }
        self.assertIn((self.program.pk, 1), unconfigured)

    def test_structure_with_one_item_counts_as_set_up(self):
        self.make_structure(
            self.target, self.program, 1, [("Tuition", 100)]
        )
        progress = fee_progress(self.target)
        cell = next(
            cell for cell in progress["cells"]
            if cell["program"].pk == self.program.pk
            and cell["year_level"] == 1
        )
        self.assertTrue(cell["set_up"])
        unconfigured = {
            (row["program"].pk, row["year_level"])
            for row in unconfigured_fee_structures(self.target)
        }
        self.assertNotIn((self.program.pk, 1), unconfigured)


class CopyFeeStructureTests(FeeTestBase):
    def test_copy_fills_only_empty_cells_and_charges_students(self):
        self.make_structure(self.source, self.program, 1, [("Tuition", 100)])
        self.make_structure(self.source, self.program, 2, [("Tuition", 120)])
        self.make_structure(
            self.source, self.short_program, 1, [("Tuition", 80)]
        )
        # Invalid for a one-year trade but still present in the source.
        self.make_structure(
            self.source, self.short_program, 2, [("Tuition", 80)]
        )
        inactive = Program.objects.create(
            code="OLD",
            name="Inactive Trade",
            duration_years=2,
            category="NC",
            active=False,
        )
        self.make_structure(self.source, inactive, 1, [("Tuition", 50)])

        existing = self.make_structure(
            self.target, self.program, 1, [("Levy", 50)]
        )
        student, enrollment = self.make_enrolled_student(
            "ST-COPY", year_level=2
        )

        result = copy_fee_structures(self.source, self.target)

        self.assertEqual(result["copied"], 2)
        self.assertEqual(result["charges"], 1)
        self.assertEqual(result["skipped"], 3)
        self.assertEqual(
            list(existing.items.values_list("name", flat=True)),
            ["Levy"],
        )
        copied = FeeStructure.objects.get(
            semester=self.target, program=self.program, year_level=2
        )
        self.assertEqual(
            list(copied.items.values_list("name", "amount")),
            [("Tuition", 120)],
        )
        charge = StudentCharge.objects.get(
            student=student, enrollment=enrollment
        )
        self.assertEqual(charge.amount, 120)

    def test_copy_is_idempotent(self):
        self.make_structure(self.source, self.program, 1, [("Tuition", 100)])
        self.make_enrolled_student("ST-IDEMPOTENT", year_level=1)

        first = copy_fee_structures(self.source, self.target)
        second = copy_fee_structures(self.source, self.target)

        self.assertEqual(first["copied"], 1)
        self.assertEqual(first["charges"], 1)
        self.assertEqual(second["copied"], 0)
        self.assertEqual(second["charges"], 0)
        self.assertEqual(
            FeeStructureItem.objects.filter(
                fee_structure__semester=self.target
            ).count(),
            1,
        )


class BulkFeeTests(FeeTestBase):
    def bulk_data(self, programs, years):
        return {
            "programs": [str(program.pk) for program in programs],
            "year_levels": [str(year) for year in years],
            "fee_name": "Levy",
            "amount": "300.00",
            "description": "",
        }

    def test_bulk_skips_years_beyond_trade_duration(self):
        response = self.client.post(
            f"/semesters/{self.target.pk}/fee-structures/bulk/",
            self.bulk_data([self.program, self.short_program], [1, 2]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FeeStructure.objects.filter(
                semester=self.target,
                program=self.program,
                year_level=1,
            ).exists()
        )
        self.assertTrue(
            FeeStructure.objects.filter(
                semester=self.target,
                program=self.program,
                year_level=2,
            ).exists()
        )
        self.assertTrue(
            FeeStructure.objects.filter(
                semester=self.target,
                program=self.short_program,
                year_level=1,
            ).exists()
        )
        self.assertFalse(
            FeeStructure.objects.filter(
                semester=self.target,
                program=self.short_program,
                year_level=2,
            ).exists()
        )

    def test_bulk_does_not_duplicate_lines(self):
        url = f"/semesters/{self.target.pk}/fee-structures/bulk/"
        data = self.bulk_data([self.program], [1])

        self.client.post(url, data)
        self.client.post(url, data)

        self.assertEqual(
            FeeStructureItem.objects.filter(
                fee_structure__semester=self.target,
                fee_structure__program=self.program,
            ).count(),
            1,
        )


class EditFeeChargesTests(FeeTestBase):
    def test_edit_creates_missing_student_charges(self):
        structure = self.make_structure(
            self.target, self.program, 1, [("Tuition", 100)]
        )
        item = structure.items.get()
        student, enrollment = self.make_enrolled_student(
            "ST-EDIT", year_level=1
        )
        self.assertFalse(StudentCharge.objects.exists())

        response = self.client.post(
            f"/fee-structures/{structure.pk}/edit/",
            {
                "program": str(self.program.pk),
                "year_level": "1",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "1",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-id": str(item.pk),
                "items-0-name": "Tuition",
                "items-0-description": "",
                "items-0-amount": "100.00",
            },
        )

        self.assertEqual(response.status_code, 302)
        charge = StudentCharge.objects.get(
            student=student, enrollment=enrollment, fee_item=item
        )
        self.assertEqual(charge.amount, 100)


class CompletedSemesterLockTests(FeeTestBase):
    def setUp(self):
        super().setUp()
        self.structure = self.make_structure(
            self.completed, self.program, 1, [("Tuition", 100)]
        )
        self.item = self.structure.items.get()

    def test_completed_grid_is_read_only(self):
        response = self.client.get(
            f"/semesters/{self.completed.pk}/fee-structures/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_locked"])
        self.assertContains(
            response, "This semester is completed. Fees are locked."
        )

    def test_completed_edit_get_is_read_only(self):
        response = self.client.get(
            f"/fee-structures/{self.structure.pk}/edit/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_locked"])
        self.assertIsNone(response.context["form"])

    def test_completed_rejects_writes_everywhere(self):
        edit_payload = {
            "program": str(self.program.pk),
            "year_level": "1",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": str(self.item.pk),
            "items-0-name": "Tuition",
            "items-0-description": "",
            "items-0-amount": "999.00",
        }
        paths = [
            (
                f"/semesters/{self.completed.pk}/fee-structures/new/",
                {"program": str(self.program.pk), "year_level": "2"},
            ),
            (
                f"/semesters/{self.completed.pk}/fee-structures/bulk/",
                {
                    "programs": [str(self.program.pk)],
                    "year_levels": ["2"],
                    "fee_name": "Levy",
                    "amount": "10.00",
                    "description": "",
                },
            ),
            (
                f"/semesters/{self.completed.pk}/fee-structures/copy/",
                {"source": str(self.source.pk)},
            ),
            (f"/fee-structures/{self.structure.pk}/edit/", edit_payload),
        ]

        for path, payload in paths:
            response = self.client.post(path, payload)
            self.assertEqual(response.status_code, 302, path)

        self.item.refresh_from_db()
        self.assertEqual(self.item.amount, 100)
        self.assertEqual(
            FeeStructureItem.objects.filter(
                fee_structure__semester=self.completed
            ).count(),
            1,
        )


class FeePermissionTests(FeeTestBase):
    def test_view_only_user_cannot_change_fees(self):
        user = get_user_model().objects.create_user(
            username="fee-viewer",
            password="test-pass-123",
        )
        user.user_permissions.add(
            Permission.objects.get(codename="view_feestructure")
        )
        self.client.force_login(user)

        list_response = self.client.get(
            f"/semesters/{self.target.pk}/fee-structures/"
        )
        create_response = self.client.get(
            f"/semesters/{self.target.pk}/fee-structures/new/"
        )
        post_response = self.client.post(
            f"/semesters/{self.target.pk}/fee-structures/new/",
            {"program": str(self.program.pk), "year_level": "1"},
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)

    def test_grid_requires_login(self):
        self.client.logout()
        response = self.client.get(
            f"/semesters/{self.target.pk}/fee-structures/"
        )
        self.assertEqual(response.status_code, 302)


class FeeGridQueryTests(FeeTestBase):
    def test_query_count_does_not_grow_with_more_trades(self):
        url = f"/semesters/{self.target.pk}/fee-structures/"

        with CaptureQueriesContext(connection) as small:
            self.client.get(url)

        for index in range(8):
            Program.objects.create(
                code=f"T{index}",
                name=f"Trade {index}",
                duration_years=2,
                category="NC",
            )

        with CaptureQueriesContext(connection) as large:
            self.client.get(url)

        self.assertLessEqual(len(large), len(small) + 2)


class FeeFormPreservationTests(FeeTestBase):
    def test_legacy_form_keeps_selected_trade_on_invalid_post(self):
        response = self.client.post(
            f"/semesters/{self.target.pk}/fee-structures/new/",
            {
                "program": str(self.program.pk),
                "year_level": "1",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-name": "Tuition",
                "items-0-description": "",
                "items-0-amount": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["program"].value(),
            str(self.program.pk),
        )
        self.assertContains(response, 'value="Tuition"')
        self.assertContains(response, "This field is required")
        self.assertFalse(
            FeeStructure.objects.filter(semester=self.target).exists()
        )

    def test_locked_context_uses_hidden_trade_not_a_wiped_select(self):
        response = self.client.get(
            f"/semesters/{self.target.pk}/fee-structures/new/"
            f"?program={self.program.pk}&year_level=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<input type="hidden" name="program" value="{self.program.pk}">',
            html=False,
        )
        self.assertNotContains(response, "firstOption.disabled = true")

    def test_duplicate_structure_redirects_to_edit(self):
        existing = self.make_structure(
            self.target, self.program, 1, [("Tuition", 100)]
        )

        response = self.client.get(
            f"/semesters/{self.target.pk}/fee-structures/new/"
            f"?program={self.program.pk}&year_level=1"
        )

        self.assertRedirects(
            response,
            f"/fee-structures/{existing.pk}/edit/",
        )

    def test_year_level_none_does_not_crash_model_clean(self):
        structure = FeeStructure(
            program=self.program,
            year_level=None,
            semester=self.target,
        )
        structure.clean()


class FeeCopyViewTests(FeeTestBase):
    def test_copy_preview_and_post(self):
        self.make_structure(self.source, self.program, 1, [("Tuition", 100)])
        self.make_enrolled_student("ST-COPYVIEW", year_level=1)

        preview = self.client.get(
            f"/semesters/{self.target.pk}/fee-structures/copy/"
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.context["will_copy"], 1)

        response = self.client.post(
            f"/semesters/{self.target.pk}/fee-structures/copy/",
            {"source": str(self.source.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FeeStructure.objects.filter(
                semester=self.target, program=self.program, year_level=1
            ).exists()
        )
