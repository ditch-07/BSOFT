import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.db import connection

from .models import (
    AcademicYear,
    Enrollment,
    FeeStructure,
    FeeStructureItem,
    Payment,
    Program,
    Semester,
    Student,
    StudentCharge,
    StudentStatusLog,
    TimeOverride,
)


@override_settings(ENABLE_TIME_OVERRIDE=True)
class LegacyReportCharacterizationTests(TestCase):
    """Pin existing report CSV schemas and representative values before migration."""

    def setUp(self):
        self.today = date(2027, 3, 1)
        TimeOverride.set_frozen_time(
            timezone.make_aware(datetime(2027, 3, 1, 12, 0))
        )
        self.year = AcademicYear.objects.create(
            name="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)
        )
        self.semester = Semester.objects.create(
            academic_year=self.year, number=1,
            start_date=date(2027, 1, 1), end_date=date(2027, 6, 30),
        )
        self.program = Program.objects.create(
            code="QA-1", name="QA Trade", duration_years=2
        )
        self.student = Student.objects.create(
            student_number="QA-001", first_name="Ada", last_name="Lovelace",
            guardian_name="Grace Lovelace", guardian_phone="+263 77 123 4567",
            student_phone="+263 71 000 0000", program=self.program,
            intake_year=self.year, status=Student.ACTIVE,
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student, program=self.program, semester=self.semester,
            year_level=1, status=Enrollment.ACTIVE,
        )
        structure = FeeStructure.objects.create(
            semester=self.semester, program=self.program, year_level=1
        )
        item = FeeStructureItem.objects.create(
            fee_structure=structure, name="Tuition", amount=Decimal("100.00")
        )
        StudentCharge.objects.create(
            student=self.student, enrollment=self.enrollment,
            fee_item=item, amount=Decimal("100.00"),
        )
        self.payment = Payment.objects.create(
            receipt_number="QA-R-001", student=self.student, semester=self.semester,
            amount=Decimal("75.00"), payment_date=self.today, method=Payment.CASH,
            reference="QA reference",
        )
        self.log = StudentStatusLog.objects.create(
            student=self.student, status=Student.ACTIVE, note="QA status"
        )
        StudentStatusLog.objects.filter(pk=self.log.pk).update(
            date_changed=timezone.make_aware(datetime(2027, 3, 1, 12, 30))
        )

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="reports-root", password="test-password", email="root@example.test"
        )
        self.bursar = User.objects.create_user(
            username="reports-bursar", password="test-password"
        )
        self.read_only = User.objects.create_user(
            username="reports-reader", password="test-password"
        )
        for codename in (
            "can_view_financial_reports", "can_view_outstanding_reports",
            "view_student", "view_feestructure", "view_studentstatuslog",
        ):
            permission = Permission.objects.get(
                content_type__app_label="school", codename=codename
            )
            self.bursar.user_permissions.add(permission)
        self.read_only.user_permissions.add(Permission.objects.get(
            content_type__app_label="school", codename="view_student"
        ))

    def csv_rows(self, user, route):
        self.client.force_login(user)
        response = self.client.get(reverse(route), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        return list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))

    def test_existing_csv_headers_and_rows_are_characterized(self):
        cases = {
            "outstanding_report": (
                ["Student Number", "Name", "Program", "Semester", "Charged", "Paid", "Outstanding", "Collection %"],
                [["QA-001", "Ada Lovelace", "QA Trade", "2027 - Semester 1", "100.00", "75.00", "25.00", "75.0"]],
            ),
            "daily_collections_report": (
                ["Receipt", "Student", "Student Number", "Semester", "Method", "Amount", "Reference", "Date"],
                [["QA-R-001", "Ada Lovelace", "QA-001", "2027 - Semester 1", "Cash", "75.00", "QA reference", "2027-03-01"]],
            ),
            "enrollment_report": (
                ["Program", "Program Code", "Intake Year", "Status", "Student Count"],
                [["QA Trade", "QA-1", "2027", "Active", "1"]],
            ),
            "fee_audit_report": (
                ["Program", "Program Code", "Year Level", "Semester", "Academic Year"],
                [["QA Trade", "QA-1", "2", "2027 - Semester 1", "2027"]],
            ),
            "payment_methods_report": (
                ["Method", "Transaction Count", "Total Amount"],
                [["Cash", "1", "75.00"]],
            ),
            "program_revenue_report": (
                ["Program", "Program Code", "Charged", "Paid", "Outstanding", "Collection %"],
                [["QA Trade", "QA-1", "100.00", "75.00", "25.00", "75.0"]],
            ),
            "status_history_report": (
                ["Date Changed", "Student", "Student Number", "Program", "Status", "Note"],
                [["2027-03-01 10:30", "Ada Lovelace", "QA-001", "QA Trade", "Active", "QA status"]],
            ),
        }
        for route, (legacy_header, legacy_rows) in cases.items():
            with self.subTest(route=route):
                actual = self.csv_rows(self.superuser, route)
                self.assertEqual(actual[0][:len(legacy_header)], legacy_header)
                self.assertEqual([row[:len(legacy_header)] for row in actual[1:1 + len(legacy_rows)]], legacy_rows)
                if route == "outstanding_report":
                    self.assertEqual(actual[0][len(legacy_header):], ["Course year"])
                    self.assertEqual(actual[1][len(legacy_header):], ["1"])
                elif route == "daily_collections_report":
                    self.assertEqual(actual[0][len(legacy_header):], ["Time"])
                    self.assertRegex(actual[1][-1], r"^\d{2}:\d{2}$")
                elif route == "program_revenue_report":
                    self.assertEqual(actual[0][len(legacy_header):], ["Owed", "Credit", "Net"])
                    self.assertEqual(actual[1][len(legacy_header):], ["25.00", "0.00", "25.00"])

    def test_read_only_user_is_denied_money_and_restricted_csv_exports(self):
        for route in (
            "financial_records", "daily_collections_report", "payment_methods_report",
            "program_revenue_report", "outstanding_report", "fee_audit_report",
            "status_history_report",
        ):
            with self.subTest(route=route):
                self.client.force_login(self.read_only)
                self.assertEqual(
                    self.client.get(reverse(route), {"format": "csv"}).status_code, 403
                )
        self.client.force_login(self.read_only)
        self.assertEqual(
            self.client.get(reverse("enrollment_report"), {"format": "csv"}).status_code,
            200,
        )

    def test_financial_records_has_shared_csv_export(self):
        rows = self.csv_rows(self.superuser, "financial_records")
        self.assertEqual(rows[0][0], "Semester")
        self.assertEqual(rows[1][2:5], ["100.00", "75.00", "25.00"])

    def test_exports_have_bom_and_payment_count_is_a_count(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("payment_methods_report"), {"format": "csv"})
        self.assertTrue(response.content.startswith(bytes((0xEF, 0xBB, 0xBF))))
        self.assertEqual(self.payment.amount, Decimal("75.00"))
        rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[1][1], "1")

    def test_all_report_pages_and_pdf_exports_render(self):
        routes = (
            "financial_records", "enrollment_report", "outstanding_report", "fee_audit_report",
            "payment_methods_report", "program_revenue_report", "daily_collections_report",
            "status_history_report",
        )
        self.client.force_login(self.superuser)
        for route in routes:
            with self.subTest(route=route):
                html = self.client.get(reverse(route))
                self.assertEqual(html.status_code, 200)
                self.assertContains(html, "reports.css")
                pdf = self.client.get(reverse(route), {"format": "pdf"})
                self.assertEqual(pdf.status_code, 200)
                self.assertEqual(pdf["Content-Type"], "application/pdf")
                self.assertTrue(pdf.content.startswith(b"%PDF-"))

    def test_daily_defaults_to_today_and_exports_are_audited(self):
        self.client.force_login(self.superuser)
        html = self.client.get(reverse("daily_collections_report"))
        self.assertContains(html, 'value="2027-03-01"')
        pdf = self.client.get(reverse("daily_collections_report"), {"format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        self.assertTrue(self.superuser.auditlog_set.filter(
            action="OTHER", summary="Exported Daily collections (PDF)", category="FINANCIAL"
        ).exists())

    def test_report_hub_and_contact_columns_follow_permissions(self):
        self.client.force_login(self.read_only)
        response = self.client.get(reverse("reports_index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enrollment summary")
        self.assertNotContains(response, "Financial records")
        self.assertNotContains(response, "Outstanding balances")
        self.client.force_login(self.bursar)
        self.assertContains(self.client.get(reverse("reports_index")), "Outstanding balances")
        outstanding = self.client.get(reverse("outstanding_report"))
        self.assertNotContains(outstanding, "Guardian phone")
        with_contacts = self.client.get(reverse("outstanding_report"), {"show_contact": "1"})
        self.assertContains(with_contacts, "Guardian phone")
        self.assertContains(with_contacts, "+263 77 123 4567")

    def test_credit_reconciliation_matches_financial_records_and_outstanding(self):
        credit_student = Student.objects.create(
            student_number="QA-002", first_name="Grace", last_name="Hopper",
            guardian_name="", guardian_phone="", student_phone="", address="",
            program=self.program, intake_year=self.year, status=Student.ACTIVE,
        )
        enrollment = Enrollment.objects.create(
            student=credit_student, program=self.program, semester=self.semester,
            year_level=1, status=Enrollment.ACTIVE,
        )
        structure = FeeStructure.objects.get(semester=self.semester, program=self.program, year_level=1)
        item = FeeStructureItem.objects.create(fee_structure=structure, name="Lab", amount=Decimal("20.00"))
        StudentCharge.objects.create(student=credit_student, enrollment=enrollment, fee_item=item, amount=Decimal("20.00"))
        Payment.objects.create(receipt_number="QA-R-002", student=credit_student, semester=self.semester,
            amount=Decimal("30.00"), payment_date=self.today, method=Payment.CASH)
        self.client.force_login(self.superuser)
        fin = self.client.get(reverse("financial_records"), {"format": "csv", "academic_year": self.year.pk})
        fin_rows = list(csv.DictReader(StringIO(fin.content.decode("utf-8-sig"))))
        self.assertEqual(fin_rows[0]["Owed"], "25.00")
        self.assertEqual(fin_rows[0]["Credit"], "10.00")
        self.assertEqual(fin_rows[0]["Net outstanding"], "15.00")
        self.assertEqual(Decimal(fin_rows[0]["Owed"]) - Decimal(fin_rows[0]["Credit"]), Decimal(fin_rows[0]["Net outstanding"]))
        outstanding = self.client.get(reverse("outstanding_report"), {"format": "csv"})
        out_rows = list(csv.DictReader(StringIO(outstanding.content.decode("utf-8-sig"))))
        self.assertEqual(len(out_rows), 1)
        self.assertEqual(out_rows[0]["Outstanding"], "25.00")
        revenue = self.client.get(reverse("program_revenue_report"), {"format": "csv"})
        revenue_rows = list(csv.DictReader(StringIO(revenue.content.decode("utf-8-sig"))))
        self.assertEqual(revenue_rows[0]["Outstanding"], "15.00")
        self.assertEqual(revenue_rows[0]["Owed"], "25.00")
        self.assertEqual(revenue_rows[0]["Credit"], "10.00")
        self.assertEqual(revenue_rows[0]["Net"], "15.00")

    def test_csv_formula_injection_is_neutralized(self):
        self.payment.reference = "=HYPERLINK(\"bad\")"
        self.payment.save(update_fields=["reference"])
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("daily_collections_report"), {"format": "csv"})
        self.assertIn(b"'=HYPERLINK", response.content)
