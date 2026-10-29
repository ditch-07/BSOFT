from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .context_processors import navigation_summary
from .models import (
    AcademicYear,
    FeeStructure,
    FeeStructureItem,
    Program,
    Semester,
    Student,
    TimeOverride,
    students_with_missing_details,
    unconfigured_fee_structures,
)


class NavbarTestCase(TestCase):
    def setUp(self):
        cache.clear()
        TimeOverride.set_frozen_time(None)
        self.year = AcademicYear.objects.create(
            name="2027",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
        )
        self.program = Program.objects.create(
            code="NAV",
            name="Navigation Trade",
            duration_years=2,
            category="NC",
        )
        self.semester = Semester.objects.create(
            academic_year=self.year,
            number=1,
            start_date=date(2027, 1, 12),
            end_date=date(2027, 6, 30),
        )

    def make_user(self, username, *codenames, superuser=False):
        user = get_user_model().objects.create_user(
            username=username,
            password="testpass123",
            is_staff=superuser,
            is_superuser=superuser,
        )
        for codename in codenames:
            user.user_permissions.add(Permission.objects.get(codename=codename))
        return user

    def make_student(self, number, first_name="Ada", status=Student.ACTIVE, **fields):
        return Student.objects.create(
            student_number=number,
            first_name=first_name,
            last_name="Moyo",
            program=self.program,
            intake_year=self.year,
            status=status,
            **fields,
        )


class NavbarRenderingTests(NavbarTestCase):
    def test_superuser_gets_global_workflows_and_sidebar_academic_years(self):
        self.client.force_login(self.make_user("root", superuser=True))

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Bsoft")
        self.assertContains(response, 'aria-label="Quick actions"')
        self.assertContains(response, 'role="combobox"')
        self.assertContains(response, "Record payment")
        self.assertContains(response, "Register student")
        self.assertContains(response, "Academic years")
        self.assertContains(response, "Logout")
        self.assertContains(response, reverse("fee_structure_list", args=[self.semester.pk]))
        self.assertNotContains(response, ">Academics</a>")

    def test_payment_only_user_sees_payment_but_not_student_or_fee_actions(self):
        self.client.force_login(self.make_user("payments", "can_record_payments"))

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Record payment")
        self.assertNotContains(response, "Register student")
        self.assertNotContains(response, 'role="combobox"')
        self.assertNotContains(response, "Fees not set up")

    def test_read_only_user_has_search_but_no_write_actions(self):
        self.client.force_login(
            self.make_user("reader", "view_student", "view_feestructure")
        )

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, 'role="combobox"')
        self.assertNotContains(response, "Record payment")
        self.assertNotContains(response, "Register student")
        self.assertNotContains(response, "Fees not set up")

    def test_student_detail_makes_global_payment_action_student_aware(self):
        student = self.make_student("002/ECS")
        self.client.force_login(self.make_user("detail-root", superuser=True))

        response = self.client.get(reverse("student_detail", args=[student.pk]))

        self.assertContains(
            response,
            f'href="{reverse("payment_create")}?student={student.pk}"',
        )

    def test_logout_remains_a_post_workflow(self):
        self.client.force_login(self.make_user("logout-user"))

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(ENABLE_TIME_OVERRIDE=True)
    def test_testing_clock_is_visible_with_simulated_date(self):
        TimeOverride.set_frozen_time(
            timezone.make_aware(timezone.datetime(2027, 1, 12, 8, 0))
        )
        self.client.force_login(self.make_user("clock-root", superuser=True))

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Testing clock: 12 Jan 2027")
        self.assertContains(response, reverse("time_override"))
        self.assertEqual(response.context["nav_semester"], self.semester)
        self.assertFalse(response.context["nav_semester_is_upcoming"])


class NavbarSummaryTests(NavbarTestCase):
    def test_counts_match_dashboard_fee_helper_and_reminder_queryset(self):
        structure = FeeStructure.objects.create(
            program=self.program,
            year_level=1,
            semester=self.semester,
        )
        FeeStructureItem.objects.create(
            fee_structure=structure,
            name="Tuition",
            amount="300.00",
        )
        self.make_student("MISSING", guardian_name="")
        self.client.force_login(self.make_user("counts-root", superuser=True))

        response = self.client.get(reverse("dashboard"))

        expected_fees = len(unconfigured_fee_structures(response.context["nav_semester"]))
        expected_reminders = students_with_missing_details().count()
        self.assertEqual(response.context["nav_fee_count"], expected_fees)
        self.assertEqual(response.context["reminders_count"], expected_reminders)
        self.assertEqual(
            response.context["nav_attention_count"],
            expected_fees + expected_reminders,
        )

    def test_warm_navigation_summary_adds_no_queries(self):
        user = self.make_user("cache-root", superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        navigation_summary(request)

        with CaptureQueriesContext(connection) as queries:
            summary = navigation_summary(request)

        self.assertEqual(len(queries), 0)
        self.assertEqual(summary["nav_semester"], self.semester)


class NavbarSearchTests(NavbarTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user("search-user", "view_student", "can_record_payments")
        self.client.force_login(self.user)

    def test_partial_name_and_number_include_deferred_for_global_search(self):
        active = self.make_student("002/ECS", first_name="Tadiwa")
        deferred = self.make_student(
            "002/ECS-D",
            first_name="Tariro",
            status=Student.DEFERRED,
        )

        number_response = self.client.get(
            reverse("student_search"),
            {"q": "002/ECS", "include_deferred": "1"},
        )
        name_response = self.client.get(
            reverse("student_search"),
            {"q": "Tadi", "include_deferred": "1"},
        )

        self.assertEqual(number_response.status_code, 200)
        rows = number_response.json()["students"]
        self.assertEqual({row["id"] for row in rows}, {active.pk, deferred.pk})
        active_row = next(row for row in rows if row["id"] == active.pk)
        deferred_row = next(row for row in rows if row["id"] == deferred.pk)
        self.assertIn("course_year", active_row)
        self.assertIsNotNone(active_row["payment_url"])
        self.assertIsNone(deferred_row["payment_url"])
        self.assertEqual(len(name_response.json()["students"]), 1)

    def test_existing_payment_search_stays_active_only(self):
        self.make_student("ACTIVE-01")
        self.make_student("DEFERRED-01", status=Student.DEFERRED)

        response = self.client.get(reverse("student_search"), {"q": "01"})

        rows = response.json()["students"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Active")

    def test_search_returns_at_most_eight_students(self):
        for index in range(10):
            self.make_student(f"GROUP-{index:02d}", first_name="Group")

        response = self.client.get(reverse("student_search"), {"q": "Group"})

        self.assertEqual(len(response.json()["students"]), 8)
