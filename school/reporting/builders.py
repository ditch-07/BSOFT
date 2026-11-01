from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, OuterRef, Subquery, Sum
from django.utils import timezone

from school.models import (
    AcademicYear, Enrollment, Payment, Program, Semester, Student, StudentCharge,
    daily_collections, enrollment_summary, outstanding_students,
    payment_methods_breakdown, program_revenue, student_status_history,
    unconfigured_fee_structures,
)
from school.reporting.definitions import DEFINITIONS, ZERO, positive_balance_totals
from school.reporting.registry import REPORT_BY_VIEW
from school.reporting.renderers import ReportColumn, ReportResult
from school.utils.time_utils import get_current_date, get_working_semester


def _selected_semester(request):
    semester_id = request.GET.get("semester")
    if semester_id:
        try:
            return Semester.objects.select_related("academic_year").get(pk=semester_id)
        except (Semester.DoesNotExist, ValueError):
            pass
    return get_working_semester()


def _fmt(value):
    return f"{(value or ZERO):.2f}"


def _common(request, view, filters, columns, rows, *, kpis=None, totals=None,
            empty_text="No records match these filters.", notes=None):
    spec = REPORT_BY_VIEW[view]
    return ReportResult(
        title=spec.title, subtitle=spec.description, generated_at=timezone.localtime(),
        generated_by=request.user.get_username(), applied_filters=filters, kpis=kpis or [],
        columns=columns, rows=rows, totals=totals or {}, empty_text=empty_text,
        notes=notes or [], orientation=spec.orientation, filename_stem=spec.filename_stem,
        row_count=len(rows),
    )


def _csv(result, headers, rows):
    result.csv_columns = [ReportColumn(label, key, numeric) for label, key, numeric in headers]
    result.csv_rows = rows
    return result


def build_outstanding(request):
    semester = _selected_semester(request)
    program_id = request.GET.get("program", "")
    course_year = request.GET.get("course_year", "")
    students = outstanding_students(semester) if semester else Student.objects.none()
    if program_id:
        students = students.filter(program_id=program_id)
    if course_year:
        students = students.filter(enrollments__semester=semester, enrollments__year_level=course_year)
    year_level = Enrollment.objects.filter(student_id=OuterRef("pk"), semester=semester).order_by("pk").values("year_level")[:1]
    students = students.select_related("program").annotate(course_year_value=Subquery(year_level)).order_by("-balance", "last_name", "first_name")
    rows, charged_total, paid_total, owed_total = [], ZERO, ZERO, ZERO
    show_contact = request.user.has_perm("school.view_student") and request.GET.get("show_contact") == "1"
    for student in students:
        charged, paid = student.charged or ZERO, student.paid or ZERO
        owed = max(charged - paid, ZERO)
        percent = paid / charged * 100 if charged else ZERO
        rows.append({
            "student_number": student.student_number, "name": f"{student.first_name} {student.last_name}",
            "trade": student.program.name, "course_year": student.course_year_value or "",
            "charged": _fmt(charged), "paid": _fmt(paid), "owed": _fmt(owed),
            "collected_percent": f"{percent:.1f}%", "guardian_name": student.guardian_name if show_contact else "",
            "guardian_phone": student.guardian_phone if show_contact else "", "student_id": student.pk,
            "status": student.status, "percent_width": min(100, max(0, float(percent))),
        })
        charged_total += charged
        paid_total += paid
        owed_total += owed
    trade_name = "All trades"
    if program_id:
        trade_name = Program.objects.filter(pk=program_id).values_list("name", flat=True).first() or "Selected trade"
    filters = [("Semester", f"{semester.academic_year.name} · Semester {semester.number}" if semester else "None"),
               ("Trade", trade_name), ("Course year", course_year or "All course years")]
    columns = [ReportColumn("Student", "name"), ReportColumn("Student number", "student_number"),
        ReportColumn("Trade", "trade"), ReportColumn("Course year", "course_year"),
        ReportColumn("Charged", "charged", True), ReportColumn("Paid", "paid", True),
        ReportColumn("Owed", "owed", True), ReportColumn("Collected %", "collected_percent", True)]
    if show_contact:
        columns.extend([ReportColumn("Guardian name", "guardian_name"), ReportColumn("Guardian phone", "guardian_phone")])
    result = _common(request, "outstanding_report", filters, columns, rows,
        kpis=[("Students owing", str(len(rows))), ("Total owed", f"${owed_total:.2f}"),
              ("Average owed", f"${owed_total / len(rows) if rows else ZERO:.2f}")],
        totals={"charged": _fmt(charged_total), "paid": _fmt(paid_total), "owed": _fmt(owed_total)},
        empty_text="No students owe fees for this semester. Review charges or try another semester.",
        notes=[DEFINITIONS["owed"] + " Students owing only; credits excluded."])
    if semester:
        legacy_headers = [("Student Number", "student_number", False), ("Name", "name", False),
            ("Program", "trade", False), ("Semester", "semester", False), ("Charged", "charged", True),
            ("Paid", "paid", True), ("Outstanding", "owed", True), ("Collection %", "collection_percent", True)]
        appended_headers = [("Course year", "course_year", False)]
        if show_contact:
            appended_headers.extend([("Guardian name", "guardian_name", False), ("Guardian phone", "guardian_phone", False)])
        export_rows = [{**row, "semester": str(semester), "collection_percent": row["collected_percent"].rstrip("%")}
                       for row in rows]
        if show_contact:
            for index, row in enumerate(export_rows):
                row["guardian_name"] = rows[index]["guardian_name"]
                row["guardian_phone"] = rows[index]["guardian_phone"]
        _csv(result, legacy_headers + appended_headers, export_rows)
    return result


def build_daily_collections(request):
    today = get_current_date()
    start, end, selected = request.GET.get("date_from", ""), request.GET.get("date_to", ""), request.GET.get("date", "")
    if start and end:
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            start_date = end_date = today
        payments = daily_collections(start_date=start_date, end_date=end_date)
        period_label = f"{start_date:%d %b %Y} – {end_date:%d %b %Y}"
    else:
        try:
            chosen = datetime.strptime(selected, "%Y-%m-%d").date() if selected else today
        except ValueError:
            chosen = today
        start_date = end_date = chosen
        payments = daily_collections(chosen)
        period_label = f"{chosen:%d %b %Y}"
    payments = payments.order_by("created_at", "pk")
    aggregate = payments.aggregate(total=Sum("amount"), count=Count("pk"))
    total, count = aggregate["total"] or ZERO, aggregate["count"] or 0
    method_totals = {method: {"count": 0, "amount": ZERO} for method, _ in Payment.PAYMENT_METHODS}
    rows, csv_rows = [], []
    for payment in payments:
        method_totals[payment.method]["count"] += 1
        method_totals[payment.method]["amount"] += payment.amount
        row = {"receipt": payment.receipt_number, "student": f"{payment.student.first_name} {payment.student.last_name}",
               "student_number": payment.student.student_number, "semester": str(payment.semester),
               "method": payment.get_method_display(), "amount": _fmt(payment.amount),
               "reference": payment.reference, "date": payment.payment_date.strftime("%d %b %Y"),
               "time": timezone.localtime(payment.created_at).strftime("%H:%M")}
        rows.append(row)
        csv_rows.append({**row, "date": payment.payment_date.isoformat()})
    method_notes = [f"{dict(Payment.PAYMENT_METHODS)[method]}: {data['count']} · ${data['amount']:.2f}"
                    for method, data in method_totals.items()]
    result = _common(request, "daily_collections_report", [("Date", period_label)], [
        ReportColumn("Receipt", "receipt"), ReportColumn("Student", "student"),
        ReportColumn("Student number", "student_number"), ReportColumn("Semester", "semester"),
        ReportColumn("Method", "method"), ReportColumn("Amount", "amount", True),
        ReportColumn("Reference", "reference"), ReportColumn("Date", "date"), ReportColumn("Time", "time")],
        rows, kpis=[("Transactions", str(count)), ("Collected", f"${total:.2f}"),
                    ("Average transaction", f"${total / count if count else ZERO:.2f}")],
        totals={"method": "TOTAL", "amount": _fmt(total)},
        empty_text=f"No payments in {period_label}. Try This week.", notes=method_notes)
    result.csv_columns = [ReportColumn(label, key, numeric) for label, key, numeric in [
        ("Receipt", "receipt", False), ("Student", "student", False), ("Student Number", "student_number", False),
        ("Semester", "semester", False), ("Method", "method", False), ("Amount", "amount", True),
        ("Reference", "reference", False), ("Date", "date", False), ("Time", "time", False)]]
    result.csv_rows = csv_rows + [{"method": "TOTAL", "amount": _fmt(total)}]
    return result


def build_payment_methods(request):
    semester = _selected_semester(request)
    breakdown = list(payment_methods_breakdown(semester)) if semester else []
    total = sum((item["total"] or ZERO for item in breakdown), ZERO)
    count = sum((item["count"] or 0 for item in breakdown), 0)
    labels = dict(Payment.PAYMENT_METHODS)
    rows = [{"method": labels.get(item["method"], item["method"]), "count": item["count"] or 0,
             "amount": _fmt(item["total"]), "share": f"{(item['total'] / total * 100) if total else ZERO:.1f}%"}
            for item in breakdown]
    result = _common(request, "payment_methods_report", [("Semester", str(semester) if semester else "None")], [
        ReportColumn("Method", "method"), ReportColumn("Transaction Count", "count", True),
        ReportColumn("Total Amount", "amount", True), ReportColumn("Share", "share", True)],
        rows, kpis=[("Transactions", str(count)), ("Collected", f"${total:.2f}")],
        totals={"method": "TOTAL", "count": count, "amount": _fmt(total), "share": "100.0%"},
        notes=[DEFINITIONS["collected"]])
    return _csv(result, [("Method", "method", False), ("Transaction Count", "count", True),
                         ("Total Amount", "amount", True)], rows)


def build_program_revenue(request):
    semester = _selected_semester(request)
    revenue = program_revenue(semester) if semester else []
    # Keep the legacy billed/collected attribution from program_revenue, but
    # derive Owed and Credit from each student's balance, grouped by current trade.
    balances_by_student = {}
    if semester:
        charge_rows = StudentCharge.objects.filter(enrollment__semester=semester).values(
            "student_id", "student__program_id", "student__program__name", "student__program__code"
        ).annotate(total=Sum("amount"))
        payment_rows = Payment.objects.filter(semester=semester).values(
            "student_id", "student__program_id", "student__program__name", "student__program__code"
        ).annotate(total=Sum("amount"))
        for item in charge_rows:
            balances_by_student[item["student_id"]] = {
                "trade_id": item["student__program_id"], "trade": item["student__program__name"],
                "code": item["student__program__code"], "charged": item["total"] or ZERO, "paid": ZERO,
            }
        for item in payment_rows:
            balance = balances_by_student.setdefault(item["student_id"], {
                "trade_id": item["student__program_id"], "trade": item["student__program__name"],
                "code": item["student__program__code"], "charged": ZERO, "paid": ZERO,
            })
            balance["paid"] = item["total"] or ZERO
    balance_by_trade = {}
    for balance in balances_by_student.values():
        trade_balance = balance_by_trade.setdefault(balance["trade_id"], {
            "trade": balance["trade"], "code": balance["code"], "owed": ZERO, "credit": ZERO,
        })
        student_balance = balance["charged"] - balance["paid"]
        if student_balance > ZERO:
            trade_balance["owed"] += student_balance
        elif student_balance < ZERO:
            trade_balance["credit"] -= student_balance

    rows, charged_total, paid_total, owed_total, credit_total = [], ZERO, ZERO, ZERO, ZERO
    row_by_trade = {}
    for item in revenue:
        trade_id = item["fee_item__fee_structure__program__id"]
        charged, paid = item["charged"] or ZERO, item["paid"] or ZERO
        legacy_net = charged - paid
        trade_balance = balance_by_trade.get(trade_id, {"owed": ZERO, "credit": ZERO})
        owed, credit = trade_balance["owed"], trade_balance["credit"]
        charged_total += charged; paid_total += paid; owed_total += owed; credit_total += credit
        percent = paid / charged * 100 if charged else ZERO
        row = {"trade": item["fee_item__fee_structure__program__name"], "code": item["fee_item__fee_structure__program__code"],
            "charged": _fmt(charged), "paid": _fmt(paid), "owed": _fmt(owed), "credit": _fmt(credit),
            "legacy_net": _fmt(legacy_net), "net": _fmt(legacy_net), "percent": f"{percent:.1f}%", "csv_percent": f"{percent:.1f}", "trade_id": trade_id}
        rows.append(row)
        row_by_trade[trade_id] = row
    for trade_id, trade_balance in balance_by_trade.items():
        if trade_id not in row_by_trade:
            row = {"trade": trade_balance["trade"], "code": trade_balance["code"], "charged": _fmt(ZERO),
                "paid": _fmt(ZERO), "owed": _fmt(trade_balance["owed"]), "credit": _fmt(trade_balance["credit"]),
                "legacy_net": _fmt(ZERO), "net": _fmt(ZERO), "percent": "0.0%", "csv_percent": "0.0", "trade_id": trade_id}
            rows.append(row)
            owed_total += trade_balance["owed"]
            credit_total += trade_balance["credit"]
    result = _common(request, "program_revenue_report", [("Semester", str(semester) if semester else "None")], [
        ReportColumn("Trade", "trade"), ReportColumn("Code", "code"), ReportColumn("Billed", "charged", True),
        ReportColumn("Collected", "paid", True), ReportColumn("Owed", "owed", True), ReportColumn("Credit", "credit", True),
        ReportColumn("Net outstanding", "net", True), ReportColumn("Collection %", "percent", True)], rows,
        kpis=[("Billed", f"${charged_total:.2f}"), ("Collected", f"${paid_total:.2f}"),
              ("Owed", f"${owed_total:.2f}"), ("Credit", f"${credit_total:.2f}")],
        totals={"trade": "TOTAL", "charged": _fmt(charged_total), "paid": _fmt(paid_total),
                "owed": _fmt(owed_total), "credit": _fmt(credit_total), "net": _fmt(charged_total - paid_total)}, notes=[DEFINITIONS["net"]])
    return _csv(result, [("Program", "trade", False), ("Program Code", "code", False),
        ("Charged", "charged", True), ("Paid", "paid", True), ("Outstanding", "legacy_net", True),
        ("Collection %", "csv_percent", True), ("Owed", "owed", True), ("Credit", "credit", True),
        ("Net", "net", True)], rows)


def build_enrollment(request):
    program_id, intake_year, status = request.GET.get("program", ""), request.GET.get("intake_year", ""), request.GET.get("status", "")
    program = Program.objects.filter(pk=program_id).first() if program_id else None
    data = list(enrollment_summary(program=program, intake_year=intake_year or None, status=status or None))
    rows = [{"trade": item["program__name"], "code": item["program__code"], "intake_year": item["intake_year__name"],
             "status": dict(Student.STATUS_CHOICES).get(item["status"], item["status"]), "count": item["count"]} for item in data]
    result = _common(request, "enrollment_report", [("Trade", program.name if program else "All trades"),
        ("Intake year", intake_year or "All years"), ("Status", status or "All statuses")], [
        ReportColumn("Trade", "trade"), ReportColumn("Trade code", "code"), ReportColumn("Intake year", "intake_year"),
        ReportColumn("Status", "status"), ReportColumn("Student count", "count", True)], rows,
        kpis=[("Enrolled students", str(sum(row["count"] for row in rows)))], totals={"count": sum(row["count"] for row in rows)},
        notes=["CSV remains in the existing long-form format."])
    return _csv(result, [("Program", "trade", False), ("Program Code", "code", False),
        ("Intake Year", "intake_year", False), ("Status", "status", False), ("Student Count", "count", True)], rows)


def build_fee_audit(request):
    semester = _selected_semester(request)
    missing = unconfigured_fee_structures(semester) if semester else []
    rows = [{"trade": item["program"].name, "code": item["program"].code, "course_year": item["year_level"],
             "semester": str(semester) if semester else "", "academic_year": semester.academic_year.name if semester else "",
             "students_waiting": Enrollment.objects.filter(semester=semester, program=item["program"],
                 year_level=item["year_level"], student__status=Student.ACTIVE).values("student_id").distinct().count() if semester else 0,
             "fees_url": f"/semesters/{semester.pk}/fee-structures/?program={item['program'].pk}&year={item['year_level']}#fee-cell-{item['program'].pk}-{item['year_level']}" if semester else ""}
            for item in missing]
    total_pairs = sum(Program.objects.filter(active=True).values_list("duration_years", flat=True))
    result = _common(request, "fee_audit_report", [("Semester", str(semester) if semester else "None")], [
        ReportColumn("Trade", "trade"), ReportColumn("Trade code", "code"),
        ReportColumn("Course year", "course_year", True), ReportColumn("Students waiting", "students_waiting", True),
        ReportColumn("Set up fees", "fees_url")], rows,
        kpis=[("Fees still missing", str(len(rows))), ("Configured", f"{total_pairs-len(rows)} of {total_pairs}")],
        empty_text="All active trades have fee items for this semester. Continue to the Fees grid to review.")
    return _csv(result, [("Program", "trade", False), ("Program Code", "code", False),
        ("Year Level", "course_year", True), ("Semester", "semester", False), ("Academic Year", "academic_year", False)], rows)


def build_status_history(request):
    today = get_current_date()
    start, end = request.GET.get("start_date") or (today-timedelta(days=30)).isoformat(), request.GET.get("end_date") or today.isoformat()
    student_id, status = request.GET.get("student", ""), request.GET.get("status", "")
    student = Student.objects.filter(pk=student_id).first() if student_id else None
    logs = student_status_history(student=student, start_date=start, end_date=end)
    if status:
        logs = logs.filter(status=status)
    rows, csv_rows = [], []
    for log in logs:
        row = {"date": timezone.localtime(log.date_changed).strftime("%d %b %Y %H:%M"),
            "student": f"{log.student.first_name} {log.student.last_name}", "student_number": log.student.student_number,
            "trade": log.student.program.name, "status": log.get_status_display(), "note": log.note}
        rows.append(row)
        csv_rows.append({**row, "date": log.date_changed.strftime("%Y-%m-%d %H:%M")})
    result = _common(request, "status_history_report", [("From", start), ("To", end),
        ("Student", student.student_number if student else "All students"), ("Status", status or "All statuses")], [
        ReportColumn("Date changed", "date"), ReportColumn("Student", "student"), ReportColumn("Student number", "student_number"),
        ReportColumn("Trade", "trade"), ReportColumn("Status", "status"), ReportColumn("Note", "note")], rows,
        empty_text="No status changes in this period. Try This month.")
    result = _csv(result, [("Date Changed", "date", False), ("Student", "student", False),
        ("Student Number", "student_number", False), ("Program", "trade", False), ("Status", "status", False), ("Note", "note", False)], csv_rows)
    return result


def build_financial_records(request):
    today, year_id = get_current_date(), request.GET.get("academic_year", "")
    if year_id:
        years = AcademicYear.objects.filter(pk=year_id)
    else:
        current = AcademicYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        years = AcademicYear.objects.filter(pk=current.pk) if current else AcademicYear.objects.none()
    semesters = list(Semester.objects.filter(academic_year__in=years).select_related("academic_year").order_by("academic_year__name", "number"))
    ids = [semester.pk for semester in semesters]
    charged = {row["fee_item__fee_structure__semester_id"]: row for row in StudentCharge.objects.filter(
        fee_item__fee_structure__semester_id__in=ids).values("fee_item__fee_structure__semester_id").annotate(total=Sum("amount"), students=Count("student", distinct=True))}
    paid = {row["semester_id"]: row["total"] or ZERO for row in Payment.objects.filter(semester_id__in=ids).values("semester_id").annotate(total=Sum("amount"))}
    charged_students = {(row["fee_item__fee_structure__semester_id"], row["student_id"]): row["total"] for row in StudentCharge.objects.filter(
        fee_item__fee_structure__semester_id__in=ids).values("fee_item__fee_structure__semester_id", "student_id").annotate(total=Sum("amount"))}
    paid_students = {(row["semester_id"], row["student_id"]): row["total"] for row in Payment.objects.filter(semester_id__in=ids).values("semester_id", "student_id").annotate(total=Sum("amount"))}
    balances = {semester_id: [] for semester_id in ids}
    for key, amount in charged_students.items():
        balances[key[0]].append((amount, paid_students.get(key, ZERO)))
    for key, amount in paid_students.items():
        if key not in charged_students:
            balances[key[0]].append((ZERO, amount))
    rows, totals = [], {key: ZERO for key in ("charged", "paid", "owed", "credit", "net", "students")}
    for semester in semesters:
        bill, collected = charged.get(semester.pk, {}).get("total") or ZERO, paid.get(semester.pk, ZERO)
        balance = positive_balance_totals(balances[semester.pk])
        students = charged.get(semester.pk, {}).get("students", 0)
        row = {"semester": str(semester), "students": students, "charged": _fmt(bill), "paid": _fmt(collected),
            "owed": _fmt(balance["owed"]), "credit": _fmt(balance["credit"]), "net": _fmt(bill-collected),
            "percent": f"{(collected/bill*100) if bill else ZERO:.1f}%"}
        rows.append(row)
        for key, value in (("charged", bill), ("paid", collected), ("owed", balance["owed"]),
                           ("credit", balance["credit"]), ("net", bill-collected), ("students", students)):
            totals[key] += value
    year = years.first()
    result = _common(request, "financial_records", [("Academic year", str(year or "Current year"))], [
        ReportColumn("Semester", "semester"), ReportColumn("Students charged", "students", True),
        ReportColumn("Billed", "charged", True), ReportColumn("Collected", "paid", True), ReportColumn("Owed", "owed", True),
        ReportColumn("Credit", "credit", True), ReportColumn("Net outstanding", "net", True), ReportColumn("Collected %", "percent", True)], rows,
        kpis=[("Billed", f"${totals['charged']:.2f}"), ("Collected", f"${totals['paid']:.2f}"),
              ("Owed", f"${totals['owed']:.2f}"), ("Credit", f"${totals['credit']:.2f}")],
        totals={key: _fmt(value) if key != "students" else value for key, value in totals.items()}, notes=[DEFINITIONS["net"]])
    result.csv_columns = result.columns
    result.csv_rows = rows
    return result


BUILDERS = {
    "outstanding_report": build_outstanding, "daily_collections_report": build_daily_collections,
    "financial_records": build_financial_records, "program_revenue_report": build_program_revenue,
    "payment_methods_report": build_payment_methods, "enrollment_report": build_enrollment,
    "fee_audit_report": build_fee_audit, "status_history_report": build_status_history,
}
