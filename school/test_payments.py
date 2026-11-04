import json
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import (
    AcademicYear,
    AuditLog,
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
class PaymentTestBase(TestCase):
    """A student billed for one semester, with a second semester on the way."""

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
        cls.current = Semester.objects.create(
            academic_year=cls.year_2026,
            number=2,
            start_date=date(2026, 7, 15),
            end_date=date(2026, 12, 15),
        )
        cls.upcoming = Semester.objects.create(
            academic_year=cls.year_2027,
            number=1,
            start_date=date(2027, 1, 12),
            end_date=date(2027, 6, 30),
        )
        cls.program = Program.objects.create(
            code="DPF",
            name="Digital Photography",
            duration_years=2,
            category="NC",
        )
        cls.bursar = get_user_model().objects.create_user(
            username="bursar",
            password="test-pass-123",
        )
        cls.bursar.user_permissions.add(
            Permission.objects.get(codename="can_record_payments"),
            Permission.objects.get(codename="view_student"),
        )
        cls.viewer = get_user_model().objects.create_user(
            username="viewer",
            password="test-pass-123",
        )
        cls.viewer.user_permissions.add(
            Permission.objects.get(codename="view_student"),
        )
        cls.finance = get_user_model().objects.create_user(
            username="finance",
            password="test-pass-123",
        )
        cls.finance.user_permissions.add(
            Permission.objects.get(codename="view_student"),
            Permission.objects.get(codename="can_view_financial_reports"),
        )

    @classmethod
    def tearDownClass(cls):
        TimeOverride.objects.all().delete()
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(self.bursar)
        self.student = self.make_student("BSOFT-001")
        self.current_enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            semester=self.current,
            year_level=1,
        )
        self.upcoming_enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            semester=self.upcoming,
            year_level=1,
        )
        self.charge(self.current_enrollment, "Tuition", "1200.00")
        self.charge(self.upcoming_enrollment, "Tuition", "1200.00")

    # ---------------------------------------------------------
    # helpers
    # ---------------------------------------------------------

    def make_student(self, number, status=Student.ACTIVE, program=None):
        return Student.objects.create(
            student_number=number,
            first_name="Tendai",
            last_name="Moyo",
            program=program or self.program,
            intake_year=self.year_2026,
            status=status,
            student_phone="+263 77 123 4567",
        )

    def charge(self, enrollment, name, amount):
        structure, _ = FeeStructure.objects.get_or_create(
            program=enrollment.program,
            year_level=enrollment.year_level,
            semester=enrollment.semester,
        )
        item = FeeStructureItem.objects.create(
            fee_structure=structure,
            name=f"{name} {amount}",
            amount=Decimal(amount),
        )
        return StudentCharge.objects.create(
            student=enrollment.student,
            enrollment=enrollment,
            fee_item=item,
            amount=Decimal(amount),
        )

    def pay(self, student, amount, semester=None, method=Payment.CASH, receipt=""):
        return Payment.objects.create(
            student=student,
            semester=semester or self.current,
            amount=Decimal(amount),
            payment_date=date(2026, 10, 27),
            method=method,
            receipt_number=receipt,
        )

    def post_payment(self, **overrides):
        payload = {
            "student_id": self.student.pk,
            "semester": self.current.pk,
            "amount": "300.00",
            "payment_date": "2026-10-27",
            "method": Payment.BANK,
            "receipt_number": "",
            "reference": "BANK-SLIP-77",
            "notes": "Part payment",
        }
        payload.update(overrides)
        return self.client.post(reverse("payment_create"), payload)

    def page_url(self, **params):
        url = reverse("payment_create")
        query = {"student": self.student.pk}
        query.update(params)
        return f"{url}?" + "&".join(f"{key}={value}" for key, value in query.items())


class ReceiptAllocationTests(PaymentTestBase):
    def test_receipt_numbers_are_allocated_in_order_for_the_payment_date(self):
        first = self.pay(self.student, "10.00", receipt="")
        second = self.pay(self.student, "10.00", receipt="")

        self.assertEqual(first.receipt_number, "RCP-20261027-0001")
        self.assertEqual(second.receipt_number, "RCP-20261027-0002")

    def test_receipt_numbers_are_scoped_per_payment_date(self):
        self.pay(self.student, "10.00", receipt="")

        other_day = Payment.objects.create(
            student=self.student,
            semester=self.current,
            amount=Decimal("5.00"),
            payment_date=date(2026, 10, 28),
            receipt_number="",
        )

        self.assertEqual(other_day.receipt_number, "RCP-20261028-0001")

    def test_supplied_receipt_number_is_kept(self):
        payment = self.pay(self.student, "10.00", receipt="BOOK-0042")
        self.assertEqual(payment.receipt_number, "BOOK-0042")

    def test_api_payment_without_receipt_is_stored_with_one(self):
        response = self.client.post(
            reverse("api_payment_create"),
            data=json.dumps({
                "student": self.student.pk,
                "semester": self.current.pk,
                "amount": "150.00",
                "payment_date": "2026-10-27",
                "method": Payment.ECOCASH,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        payment = Payment.objects.get(pk=response.json()["id"])
        self.assertTrue(payment.receipt_number.startswith("RCP-20261027-"))
        self.assertEqual(payment.method, Payment.ECOCASH)

    def test_api_rejects_an_unparseable_payment_date(self):
        response = self.client.post(
            reverse("api_payment_create"),
            data=json.dumps({
                "student": self.student.pk,
                "semester": self.current.pk,
                "amount": "150.00",
                "payment_date": "not-a-date",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_date", response.json()["errors"])
        self.assertFalse(Payment.objects.exists())


class RecordPaymentPageTests(PaymentTestBase):
    def test_page_shows_each_billable_semester_with_its_balance(self):
        self.pay(self.student, "200.00")

        response = self.client.get(self.page_url())
        rows = {row["semester"].pk: row for row in response.context["term_rows"]}

        self.assertEqual(response.status_code, 200)
        self.assertEqual(rows[self.current.pk]["charged"], Decimal("1200.00"))
        self.assertEqual(rows[self.current.pk]["paid"], Decimal("200.00"))
        self.assertEqual(rows[self.current.pk]["balance"], Decimal("1000.00"))
        self.assertEqual(rows[self.upcoming.pk]["balance"], Decimal("1200.00"))
        self.assertTrue(rows[self.current.pk]["is_selected"])
        self.assertFalse(rows[self.upcoming.pk]["is_selected"])

    def test_semester_without_fees_is_hidden_and_counted(self):
        blank = Semester.objects.create(
            academic_year=self.year_2027,
            number=2,
            start_date=date(2027, 7, 15),
            end_date=date(2027, 12, 15),
        )
        Enrollment.objects.create(
            student=self.student,
            program=self.program,
            semester=blank,
            year_level=2,
        )

        response = self.client.get(self.page_url())

        shown = [row["semester"].pk for row in response.context["term_rows"]]
        self.assertNotIn(blank.pk, shown)
        self.assertEqual(response.context["skipped_terms"], 1)

    def test_payment_date_defaults_to_today(self):
        response = self.client.get(self.page_url())
        self.assertEqual(
            response.context["form"].fields["payment_date"].initial,
            date(2026, 10, 27),
        )

    def test_page_offers_every_payment_method(self):
        response = self.client.get(self.page_url())
        methods = response.context["form"].fields["method"].choices
        self.assertEqual(
            [value for value, _ in methods],
            [Payment.CASH, Payment.BANK, Payment.ECOCASH, Payment.OTHER],
        )

    def test_query_count_does_not_grow_with_semesters(self):
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.page_url())

        for number in (1, 2, 3, 4):
            extra = Semester.objects.create(
                academic_year=self.year_2027,
                number=number,
                start_date=date(2027, 1, 1),
                end_date=date(2027, 2, 1),
            )
            enrollment = Enrollment.objects.create(
                student=self.student,
                program=self.program,
                semester=extra,
                year_level=1,
            )
            self.charge(enrollment, "Tuition", "100.00")

        with CaptureQueriesContext(connection) as large:
            self.client.get(self.page_url())

        self.assertLessEqual(len(large), len(small))


class RecordPaymentSubmissionTests(PaymentTestBase):
    def test_recording_a_payment_redirects_to_the_receipt(self):
        response = self.post_payment()

        payment = Payment.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"recorded={payment.pk}", response["Location"])
        self.assertEqual(payment.amount, Decimal("300.00"))
        self.assertEqual(payment.method, Payment.BANK)
        self.assertEqual(payment.reference, "BANK-SLIP-77")
        self.assertTrue(payment.receipt_number.startswith("RCP-20261027-"))

    def test_confirmation_page_shows_the_receipt_and_new_balance(self):
        self.post_payment()
        payment = Payment.objects.get()

        response = self.client.get(
            self.page_url(semester=self.current.pk, recorded=payment.pk)
        )

        self.assertContains(response, payment.receipt_number)
        self.assertContains(response, "Payment recorded")
        self.assertEqual(response.context["recorded_payment"], payment)
        self.assertEqual(
            response.context["selected_term"]["balance"],
            Decimal("900.00"),
        )

    def test_reloading_the_confirmation_does_not_record_again(self):
        self.post_payment()
        payment = Payment.objects.get()
        url = self.page_url(semester=self.current.pk, recorded=payment.pk)

        self.client.get(url)
        self.client.get(url)

        self.assertEqual(Payment.objects.count(), 1)

    def test_supplied_receipt_number_is_used(self):
        self.post_payment(receipt_number="BOOK-0099")
        self.assertEqual(Payment.objects.get().receipt_number, "BOOK-0099")

    def test_used_receipt_number_is_rejected_without_saving(self):
        self.pay(self.student, "50.00", receipt="BOOK-0099")

        response = self.post_payment(receipt_number="BOOK-0099")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertIn("receipt_number", response.context["form"].errors)
        self.assertContains(response, "already been used")

    def test_overpayment_is_allowed_and_shown_as_credit(self):
        self.post_payment(amount="1500.00")
        payment = Payment.objects.get()

        response = self.client.get(
            self.page_url(semester=self.current.pk, recorded=payment.pk)
        )

        self.assertEqual(
            response.context["selected_term"]["balance"],
            Decimal("-300.00"),
        )
        self.assertContains(response, "in credit")

    def test_zero_amount_is_rejected(self):
        response = self.post_payment(amount="0.00")

        self.assertFalse(Payment.objects.exists())
        self.assertIn("amount", response.context["form"].errors)

    def test_semester_from_another_student_is_rejected(self):
        other = self.make_student("BSOFT-002")
        Enrollment.objects.create(
            student=other,
            program=self.program,
            semester=self.current,
            year_level=1,
        )
        foreign_semester = Semester.objects.create(
            academic_year=self.year_2027,
            number=2,
            start_date=date(2027, 7, 15),
            end_date=date(2027, 12, 15),
        )
        Enrollment.objects.create(
            student=other,
            program=self.program,
            semester=foreign_semester,
            year_level=2,
        )

        response = self.post_payment(semester=foreign_semester.pk)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.exists())

    def test_invalid_post_keeps_the_typed_values_visible(self):
        response = self.post_payment(receipt_number="BOOK-0099", amount="0.00")

        self.assertContains(response, "BOOK-0099")
        self.assertEqual(response.context["form"].data["reference"], "BANK-SLIP-77")

    def test_payment_is_written_to_the_audit_trail(self):
        self.post_payment()

        payment = Payment.objects.get()
        log = AuditLog.objects.get(student=self.student)
        self.assertEqual(log.action, "PAYMENT")
        self.assertEqual(log.details["receipt"], payment.receipt_number)
        self.assertEqual(log.details["method"], "Bank")

    def test_other_roles_cannot_open_the_page(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.page_url())
        self.assertEqual(response.status_code, 403)

    def test_anonymous_users_are_sent_to_the_login_page(self):
        self.client.logout()
        response = self.client.get(self.page_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_inactive_student_cannot_be_charged(self):
        deferred = self.make_student("BSOFT-003", status=Student.DEFERRED)
        response = self.client.get(
            f"{reverse('payment_create')}?student={deferred.pk}"
        )
        self.assertEqual(response.status_code, 404)


class ArchiveBase(PaymentTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.bursar)


class ArchiveListTests(ArchiveBase):
    def test_archive_lists_every_status_not_only_active(self):
        self.make_student("BSOFT-100", status=Student.COMPLETED)
        self.make_student("BSOFT-101", status=Student.WITHDRAWN)
        self.make_student("BSOFT-102", status=Student.DEFERRED)

        response = self.client.get(reverse("archive_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtered_count"], 4)
        self.assertContains(response, "BSOFT-100")
        self.assertContains(response, "BSOFT-101")

    def test_status_and_trade_filters_narrow_the_list(self):
        other_program = Program.objects.create(
            code="CARP",
            name="Carpentry",
            duration_years=1,
            category="NC",
        )
        self.make_student("BSOFT-200", status=Student.COMPLETED)
        self.make_student("BSOFT-201", status=Student.WITHDRAWN, program=other_program)

        completed = self.client.get(reverse("archive_list"), {"status": "COMPLETED"})
        carpentry = self.client.get(reverse("archive_list"), {"program": other_program.pk})

        self.assertEqual(completed.context["filtered_count"], 1)
        self.assertContains(completed, "BSOFT-200")
        self.assertNotContains(completed, "BSOFT-201")
        self.assertEqual(carpentry.context["filtered_count"], 1)
        self.assertContains(carpentry, "BSOFT-201")

    def test_search_matches_name_and_number(self):
        response = self.client.get(reverse("archive_list"), {"q": "BSOFT-001"})
        self.assertEqual(response.context["filtered_count"], 1)
        self.assertContains(response, "Tendai")

    def test_intake_year_filter(self):
        response = self.client.get(reverse("archive_list"), {"intake": "2026"})
        self.assertEqual(response.context["filtered_count"], 1)

    def test_rows_carry_the_current_course_year(self):
        response = self.client.get(reverse("archive_list"))
        listed = list(response.context["page_obj"])[0]
        self.assertEqual(listed.current_enrollment.year_level, 1)

    def test_query_count_does_not_grow_with_students(self):
        with CaptureQueriesContext(connection) as small:
            self.client.get(reverse("archive_list"))

        for index in range(10):
            self.make_student(f"BSOFT-3{index:02d}")

        with CaptureQueriesContext(connection) as large:
            self.client.get(reverse("archive_list"))

        self.assertLessEqual(len(large), len(small) + 1)

    def test_archive_requires_the_view_student_permission(self):
        self.client.force_login(self.finance)
        self.assertEqual(
            self.client.get(reverse("archive_list")).status_code, 200
        )

        outsider = get_user_model().objects.create_user(
            username="outsider", password="test-pass-123"
        )
        self.client.force_login(outsider)
        self.assertEqual(
            self.client.get(reverse("archive_list")).status_code, 403
        )


class ArchiveDetailTests(ArchiveBase):
    def setUp(self):
        super().setUp()
        self.pay(self.student, "250.00", method=Payment.ECOCASH, receipt="RCP-X-1")
        StudentStatusLog.objects.create(
            student=self.student,
            status=Student.DEFERRED,
            note="Family relocation",
        )
        self.url = reverse("archive_detail", args=[self.student.pk])

    def test_detail_shows_identity_ledger_payments_and_history(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tendai")
        self.assertContains(response, "RCP-X-1")
        self.assertContains(response, "EcoCash")
        self.assertContains(response, "Family relocation")
        self.assertContains(response, "Semester ledger")
        self.assertEqual(
            response.context["balance"], Decimal("2150.00")
        )

    def test_financials_are_hidden_without_a_financial_permission(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_financials"])
        self.assertNotContains(response, "RCP-X-1")
        self.assertContains(response, "hidden")
        self.assertContains(response, "Digital Photography")

    def test_financials_are_shown_to_financial_roles(self):
        self.client.force_login(self.finance)
        response = self.client.get(self.url)

        self.assertTrue(response.context["show_financials"])
        self.assertContains(response, "RCP-X-1")

    def test_record_payment_action_needs_payment_permission_and_active_student(self):
        self.assertContains(self.client.get(self.url), "Record payment")

        self.client.force_login(self.finance)
        self.assertNotContains(self.client.get(self.url), "Record payment")

        self.student.status = Student.COMPLETED
        self.student.save(update_fields=["status"])
        self.client.force_login(self.bursar)
        self.assertNotContains(self.client.get(self.url), "Record payment")

    def test_unknown_student_is_a_404(self):
        response = self.client.get(reverse("archive_detail", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_query_count_does_not_grow_with_semesters(self):
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.url)

        for number in (1, 2, 3):
            extra = Semester.objects.create(
                academic_year=self.year_2027,
                number=number,
                start_date=date(2027, 1, 1),
                end_date=date(2027, 2, 1),
            )
            Enrollment.objects.create(
                student=self.student,
                program=self.program,
                semester=extra,
                year_level=1,
            )

        with CaptureQueriesContext(connection) as large:
            self.client.get(self.url)

        self.assertLessEqual(len(large), len(small) + 1)
