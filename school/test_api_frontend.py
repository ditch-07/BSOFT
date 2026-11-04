import json
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import resolve

from config.views import nuxt_app
from school.models import AcademicYear, Enrollment, Program, Semester, Student, StudentStatusLog


class FrontendApiIntegrationTests(TestCase):
    def test_vue_routes_use_the_spa_and_api_routes_remain_available(self):
        if settings.FRONTEND_MODE == "vue":
            self.assertIs(resolve("/").func, nuxt_app)
            self.assertIs(resolve("/students/").func, nuxt_app)
            self.assertIs(resolve("/students/archive/").func, nuxt_app)
            self.assertIs(resolve("/students/import/").func, nuxt_app)
            self.assertIs(resolve("/students/1/edit/").func, nuxt_app)
        else:
            self.assertEqual(resolve("/").url_name, "dashboard")
            self.assertEqual(resolve("/students/").url_name, "student_list")
            self.assertEqual(resolve("/students/archive/").url_name, "archive_list")
            self.assertEqual(resolve("/students/import/").url_name, "student_import")
            self.assertEqual(resolve("/students/1/edit/").url_name, "student_edit")
        self.assertEqual(resolve("/api/dashboard/").url_name, "api_dashboard")

    def test_unauthenticated_api_requests_return_json_401(self):
        response = self.client.get("/api/dashboard/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Authentication credentials were not provided.")

    def test_dashboard_hides_financial_data_without_financial_permissions(self):
        user = get_user_model().objects.create_user(
            username="student-reader",
            password="test-password",
        )
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_student",
                content_type__app_label="school",
            )
        )
        self.client.force_login(user)

        response = self.client.get("/api/dashboard/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["can_view_financials"])
        self.assertFalse(payload["can_view_outstanding"])
        self.assertIsNone(payload["financials"])
        self.assertIsNone(payload["outstanding"])
        self.assertEqual(payload["recent_payments"], [])
        self.assertEqual(payload["today_total"], 0)

    def test_auth_check_sets_csrf_cookie_and_student_search_is_available(self):
        response = self.client.get("/api/auth/check/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

        user = get_user_model().objects.create_superuser(
            username="api-reader",
            email="api-reader@example.com",
            password="test-password",
        )
        self.client.force_login(user)
        auth_response = self.client.get("/api/auth/check/")
        self.assertTrue(auth_response.json()["user"]["permissions"]["view_student"])
        self.assertTrue(auth_response.json()["user"]["permissions"]["add_student"])
        self.assertTrue(auth_response.json()["user"]["permissions"]["change_student"])
        self.assertTrue(
            auth_response.json()["user"]["permissions"]["can_view_financial_reports"]
        )

        response = self.client.get("/api/students/search/?q=ad")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"students": []})

    def test_archive_api_filters_students_and_returns_filter_metadata(self):
        user = get_user_model().objects.create_superuser(
            username="archive-reader",
            email="archive-reader@example.com",
            password="test-password",
        )
        self.client.force_login(user)
        intake_year = AcademicYear.objects.create(
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        program = Program.objects.create(
            code="ARC",
            name="Archive test",
            duration_years=2,
        )
        student = Student.objects.create(
            student_number="ARC-001",
            first_name="Archive",
            last_name="Student",
            program=program,
            intake_year=intake_year,
        )

        response = self.client.get("/api/archive/students/?status=WITHDRAWN&page=1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["status_counts"]["WITHDRAWN"], 0)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["programs"], [{"id": program.id, "name": program.name, "count": 1}])
        self.assertEqual(payload["intake_years"], [intake_year.name])

        response = self.client.get(
            f"/api/archive/students/?status=ACTIVE&program={program.id}"
            f"&intake={intake_year.name}&q={student.student_number}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], student.id)
        self.assertEqual(payload["results"][0]["intake_year"], intake_year.name)

    def test_student_edit_and_status_change_apis(self):
        user = get_user_model().objects.create_superuser(
            username="student-editor",
            email="student-editor@example.com",
            password="test-password",
        )
        self.client.force_login(user)
        intake_year = AcademicYear.objects.create(
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        program = Program.objects.create(
            code="EDIT",
            name="Edit test",
            duration_years=2,
        )
        student = Student.objects.create(
            student_number="EDIT-001",
            first_name="Before",
            last_name="Student",
            program=program,
            intake_year=intake_year,
        )

        updated = self.client.patch(
            f"/api/students/{student.id}/patch/",
            data=json.dumps({"first_name": "After"}),
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["first_name"], "After")
        self.assertEqual(updated.json()["intake_year_id"], intake_year.id)

        status_response = self.client.post(
            f"/api/students/{student.id}/status/",
            data=json.dumps({"status": "DEFERRED", "note": "Awaiting return"}),
            content_type="application/json",
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "DEFERRED")
        self.assertEqual(status_response.json()["note"], "Awaiting return")

    def test_student_import_requires_preview_and_confirms_valid_rows(self):
        user = get_user_model().objects.create_superuser(
            username="student-importer",
            email="student-importer@example.com",
            password="test-password",
        )
        self.client.force_login(user)
        intake_year = AcademicYear.objects.create(
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        semester = Semester.objects.create(
            academic_year=intake_year,
            number=1,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 6, 30),
        )
        program = Program.objects.create(
            code="IMP",
            name="Import test",
            duration_years=2,
        )
        spreadsheet = SimpleUploadedFile(
            "students.csv",
            b"STUDENT NO,SURNAME,NAME,TRADE\nIMP-001,Student,Import,IMP\n"
            b"IMP-002,Invalid,Student,UNKNOWN\n",
            content_type="text/csv",
        )

        preview_response = self.client.post(
            "/api/students/import/preview/",
            {
                "file": spreadsheet,
                "intake_year": intake_year.id,
                "semester": semester.id,
                "year_level": 1,
                "default_status": "ACTIVE",
            },
        )
        self.assertEqual(preview_response.status_code, 200)
        preview = preview_response.json()
        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(preview["invalid_count"], 1)
        self.assertEqual(Student.objects.count(), 0)

        confirm_response = self.client.post(
            "/api/students/import/confirm/",
            data=json.dumps({"preview_id": preview["preview_id"]}),
            content_type="application/json",
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.json()["created_count"], 1)
        self.assertEqual(confirm_response.json()["skipped_count"], 0)
        self.assertTrue(Student.objects.filter(student_number="IMP-001").exists())
        self.assertEqual(Enrollment.objects.filter(student__student_number="IMP-001").count(), 1)
        self.assertTrue(StudentStatusLog.objects.filter(student__student_number="IMP-001").exists())

        repeated_confirmation = self.client.post(
            "/api/students/import/confirm/",
            data=json.dumps({"preview_id": preview["preview_id"]}),
            content_type="application/json",
        )
        self.assertEqual(repeated_confirmation.status_code, 200)
        self.assertEqual(repeated_confirmation.json()["created_count"], 0)
        self.assertEqual(repeated_confirmation.json()["skipped"], ["IMP-001"])

    def test_api_logout_requires_csrf_token(self):
        user = get_user_model().objects.create_user(
            username="api-user",
            password="test-password",
        )
        client = Client(enforce_csrf_checks=True)
        client.get("/api/auth/check/")
        csrf_token = client.cookies["csrftoken"].value
        login_response = client.post(
            "/api/auth/login/",
            data=json.dumps({"username": user.username, "password": "test-password"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)

        rejected = client.post(
            "/api/auth/logout/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 403)

        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            "/api/auth/logout/",
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
