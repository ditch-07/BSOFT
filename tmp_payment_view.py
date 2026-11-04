@transaction.atomic
@permission_required("school.can_record_payments", raise_exception=True)
def payment_create(request):
    """Take one payment against one semester of one student.

    The page answers three questions in order: who is paying, which semester the
    money belongs to, and how much was handed over. Every figure comes from the
    same charge and payment aggregates the student statement uses, so the
    balance shown here matches the account it is paid into.
    """
    student_id = request.GET.get("student") or request.POST.get("student_id")
    selected_semester_id = (
        request.GET.get("semester")
        or request.POST.get("semester")
    )
    recorded_id = request.GET.get("recorded")
    today = get_current_date()

    student = None
    term_rows = []
    skipped_terms = 0
    selected_term = None

    if student_id:
        student = get_object_or_404(
            Student.objects.select_related("program", "intake_year"),
            pk=student_id,
            status=Student.ACTIVE,
        )

        all_terms = _payment_terms(student, today)
        term_rows = [row for row in all_terms if row["billable"]]
        skipped_terms = len(all_terms) - len(term_rows)

        if selected_semester_id:
            selected_term = next(
                (
                    row for row in term_rows
                    if str(row["semester"].pk) == str(selected_semester_id)
                ),
                None,
            )

        # A rejected POST keeps the operator's own choice; a fresh page opens
        # on the semester the student is actually in.
        if selected_term is None and request.method != "POST":
            selected_term = next(
                (row for row in term_rows if row["is_current"]), None
            ) or (term_rows[0] if term_rows else None)

    semester_queryset = (
        Semester.objects.filter(pk__in=[row["semester"].pk for row in term_rows])
        if term_rows
        else Semester.objects.none()
    )

    form = PaymentForm(request.POST or None, semester_queryset=semester_queryset)

    if request.method == "POST":
        if not student:
            messages.error(request, "Choose a student before recording a payment.")
        elif not form.is_valid():
            messages.error(
                request,
                "This payment was not recorded. Check the highlighted fields.",
            )
        else:
            payment = form.save(commit=False)
            payment.student = student
            payment.save()

            from school.utils.audit import log_action

            log_action(
                user=request.user,
                action="PAYMENT",
                student=student,
                summary=(
                    f"Payment of {payment.amount} recorded for "
                    f"{payment.semester} (receipt {payment.receipt_number})"
                ),
                details={
                    "receipt": payment.receipt_number,
                    "amount": str(payment.amount),
                    "semester": str(payment.semester),
                    "method": payment.get_method_display(),
                    "reference": payment.reference,
                },
                category="FINANCIAL",
            )

            messages.success(
                request,
                f"Receipt {payment.receipt_number} recorded for "
                f"{student.first_name} {student.last_name}.",
            )

            # Redirect after POST so a refresh cannot record the same money twice.
            query = urlencode({
                "student": student.pk,
                "semester": payment.semester_id,
                "recorded": payment.pk,
            })
            return redirect(f"{reverse('payment_create')}?{query}")

    # ---------------------------------------------------------
    # CONFIRMATION
    # ---------------------------------------------------------

    recorded_payment = None
    if recorded_id and student:
        recorded_payment = (
            Payment.objects
            .filter(pk=recorded_id, student=student)
            .select_related("semester", "semester__academic_year")
            .first()
        )

    if recorded_payment and selected_term is None:
        selected_term = next(
            (
                row for row in term_rows
                if row["semester"].pk == recorded_payment.semester_id
            ),
            None,
        )

    for row in term_rows:
        row["is_selected"] = bool(
            selected_term and row["semester"].pk == selected_term["semester"].pk
        )

    # ---------------------------------------------------------
    # ACCOUNT FIGURES
    # ---------------------------------------------------------

    account_charged = Decimal("0")
    account_paid = Decimal("0")

    if student:
        account_charged = (
            student.charges.aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        account_paid = (
            student.payments.aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

    return render(
        request,
        "school/payment_create.html",
        {
            "form": form,
            "student": student,
            "term_rows": term_rows,
            "selected_term": selected_term,
            "skipped_terms": skipped_terms,
            "recorded_payment": recorded_payment,
            "account_charged": account_charged,
            "account_paid": account_paid,
            "account_balance": account_charged - account_paid,
            "today": today,
            "next_receipt": next_receipt_number(today),
        },
    )
