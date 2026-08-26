# Fix: Include COMPLETED Enrollments in Academic Year Balance

## Problem
The academic year balance card (top of student_detail) only includes `Enrollment.ACTIVE` enrollments. When a semester is marked COMPLETED during progression, its charges/payments disappear from the year total.

## Current Behavior
- **Full balances table** (lines 666-693): Works correctly - iterates ALL semesters, shows charges/payments regardless of enrollment status
- **Academic year balance card** (lines 698-705): Only filters `status=Enrollment.ACTIVE` → COMPLETED semesters excluded
- **payment_create**: Only allows payments for ACTIVE enrollments (probably correct for operations)

## Fix Needed
Update the academic year balance query to include both ACTIVE and COMPLETED enrollments for the current academic year:

```python
enrollments = student.enrollments.filter(
    semester__academic_year=current_year, 
    status__in=[Enrollment.ACTIVE, Enrollment.COMPLETED]  # Include completed
).select_related("semester", "program").order_by("semester__number")
```

## Files to Modify
- `school/views.py` - `student_detail` view (line ~703)

## Validation
1. Progress student from Sem 1 → Sem 2 (Sem 1 becomes COMPLETED)
2. Check student_detail: Academic year balance card shows both semesters
3. Verify total_year_balance includes Sem 1 charges/payments
4. Full balances table still works (unchanged)