"""Tests for the Phase 0 safety fixes: access control and verified backups."""
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import AcademicYear, Enrollment, Program, Semester, Student
from .utils.backups import (
    BackupError,
    create_backup,
    restore_backup,
    verify_backup,
)


class ProgressionPermissionTests(TestCase):
    """Bulk progression must require the same permission as manual progression."""

    @classmethod
    def setUpTestData(cls):
        cls.year = AcademicYear.objects.create(
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        cls.program = Program.objects.create(
            code="TST",
            name="Test Trade",
            duration_years=2,
            category="NC",
        )
        cls.source = Semester.objects.create(
            academic_year=cls.year,
            number=1,
            start_date=date(2026, 1, 12),
            end_date=date(2026, 6, 30),
        )
        cls.target = Semester.objects.create(
            academic_year=cls.year,
            number=2,
            start_date=date(2026, 7, 15),
            end_date=date(2026, 11, 30),
        )
        cls.student = Student.objects.create(
            student_number="TST-001",
            first_name="Test",
            last_name="Student",
            program=cls.program,
            intake_year=cls.year,
        )
        cls.enrollment = Enrollment.objects.create(
            student=cls.student,
            program=cls.program,
            semester=cls.source,
            year_level=1,
        )
        cls.clerk = get_user_model().objects.create_user(
            username="progression-clerk",
            password="test-pass-123",
        )

    def setUp(self):
        self.client.force_login(self.clerk)
        self.url = reverse(
            "bulk_progress_students", args=[self.source.pk]
        )

    def test_user_without_change_student_permission_is_refused(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.student, semester=self.target
            ).exists()
        )

    def test_user_with_change_student_permission_can_progress(self):
        self.clerk.user_permissions.add(
            Permission.objects.get(codename="change_student")
        )

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("semester_list"),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student,
                semester=self.target,
                year_level=1,
            ).exists()
        )


class UserPasswordValidationTests(TestCase):
    """Account creation must enforce the configured password validators."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="user-admin",
            email="user-admin@example.com",
            password="test-pass-123",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("user_create"),
            {
                "username": "weak-user",
                "password": "password123",
                "group": "",
                "is_staff": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too common")
        self.assertFalse(
            get_user_model().objects.filter(username="weak-user").exists()
        )


class BackupHelpersTests(SimpleTestCase):
    """Backups are consistent copies, checked by SQLite before and after restore."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_database(self, name, marker):
        path = self.root / name
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE django_migrations "
                "(id INTEGER PRIMARY KEY, app TEXT)"
            )
            connection.execute("CREATE TABLE marker (value TEXT)")
            connection.execute(
                "INSERT INTO marker (value) VALUES (?)", (marker,)
            )
            connection.commit()
        finally:
            connection.close()
        return path

    def read_marker(self, path):
        connection = sqlite3.connect(path)
        try:
            return connection.execute(
                "SELECT value FROM marker"
            ).fetchone()[0]
        finally:
            connection.close()

    def test_created_backup_is_verified_and_source_is_untouched(self):
        source = self.make_database("source.sqlite3", "original")
        destination = self.root / "backups" / "backup.sqlite3"

        create_backup(source, destination)

        ok, message = verify_backup(destination)
        self.assertTrue(ok, message)
        self.assertEqual(self.read_marker(destination), "original")
        self.assertEqual(self.read_marker(source), "original")
        self.assertFalse(
            destination.with_name(destination.name + ".partial").exists()
        )

    def test_verify_rejects_a_file_that_is_not_sqlite(self):
        bogus = self.root / "not-a-backup.sqlite3"
        bogus.write_text("this is not a database", encoding="utf-8")

        ok, message = verify_backup(bogus)

        self.assertFalse(ok)
        self.assertIn("not a readable SQLite database", message)

    def test_verify_rejects_a_database_without_migrations(self):
        path = self.root / "unrelated.sqlite3"
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE something (id INTEGER)")
            connection.commit()
        finally:
            connection.close()

        ok, message = verify_backup(path)

        self.assertFalse(ok)
        self.assertIn("django_migrations", message)

    def test_restore_refuses_an_invalid_backup(self):
        live = self.make_database("live.sqlite3", "live")
        bogus = self.root / "bogus.sqlite3"
        bogus.write_text("not a backup", encoding="utf-8")

        with self.assertRaises(BackupError):
            restore_backup(bogus, live)

        self.assertEqual(self.read_marker(live), "live")

    def test_restore_replaces_database_and_keeps_a_verified_safety_copy(self):
        live = self.make_database("live.sqlite3", "live")
        backup = self.make_database("chosen.sqlite3", "restored")

        with patch(
            "school.utils.backups._close_database_connections"
        ) as close_connections:
            safety_path = restore_backup(backup, live)

        close_connections.assert_called_once()
        self.assertEqual(self.read_marker(live), "restored")
        self.assertIsNotNone(safety_path)
        self.assertTrue(safety_path.exists())
        self.assertEqual(self.read_marker(safety_path), "live")
        ok, message = verify_backup(safety_path)
        self.assertTrue(ok, message)

        ok, message = verify_backup(live)
        self.assertTrue(ok, message)
        self.assertFalse(
            live.with_name(live.name + ".restore-partial").exists()
        )
