# Payment Semester Selection Feature

## Goal
Allow admins to record payments for any semester (past, current, upcoming) instead of only the current semester. Default to current semester with clear selection UI.

## Current Behavior
- `payment_create` auto-selects first active enrollment where `semester__end_date__gte=today`
- No semester selection UI - payment always goes to that one semester
- PaymentForm deliberately excludes semester field (comment says "should never be a field the admin picks by hand")

## Requirements
1. **Semester selector** - Dropdown to choose which semester to pay for
2. **Default to current** - Pre-select the current semester (first active enrollment with end_date >= today)
3. **Clear selection** - User must explicitly see/choose the semester
4. **Show balance per semester** - Display charged/paid/balance for selected semester
5. **All enrollments** - Include past (COMPLETED) and upcoming enrollments

## Implementation Plan

### 1. Update `payment_create` view (`school/views.py:793-859`)
- Get all student enrollments (ACTIVE + COMPLETED) with charges/payments
- Accept `semester` query param to override default
- Default to current semester logic (first active enrollment with end_date >= today)
- Pass semester choices to template
- Validate selected semester has enrollment for this student

### 2. Update `PaymentForm` (`school/forms.py:165-185`)
- Add `semester` field (ModelChoiceField with student's enrollments)
- Keep it in form for validation but can be hidden if needed

### 3. Update `payment_create.html` template
- Add semester selector dropdown above payment form
- Show charged/paid/balance for selected semester (update via HTMX or JS)
- Clear visual indication that semester selection is required
- Disable payment form until semester selected (optional)

### 4. Data Flow
```
GET /payments/new/?student=123
  → payment_create()
    → Get student
    → Get all enrollments with charges/payments
    → Determine default semester (current)
    → Render template with semester choices

GET /payments/new/?student=123&semester=5
  → Same but pre-select semester 5
  → Show that semester's balance

POST /payments/new/ {student_id, semester, amount, ...}
  → Validate semester belongs to student
  → Create payment for that semester
```

## Key Decisions

### Q1: Should semester selector be a form field or URL param?
- **Form field** (Recommended): Part of POST, validates cleanly, shows in form
- URL param: Simpler GET, but need hidden field for POST

### Q2: Which enrollments to show in dropdown?
- All enrollments where student has charges OR payments (has financial activity)
- Or: All enrollments for student (ACTIVE + COMPLETED)
- **Recommendation**: All enrollments with financial activity (charges or payments exist)

### Q3: How to handle "no enrollment but want to pay"?
- Edge case: Student may want to pay for upcoming semester before enrollment
- Could allow selecting any semester where FeeStructure exists for their program/year
- **Recommendation**: Start with enrollments only; add "upcoming" later if needed

### Q4: Default semester logic?
- Current: First active enrollment with end_date >= today
- If none, first upcoming enrollment
- If none, most recent completed enrollment

## Files to Modify
1. `school/views.py` - `payment_create` view
2. `school/forms.py` - `PaymentForm` (add semester field)
3. `templates/school/payment_create.html` - Add semester selector UI

## Validation Steps
1. Select student → shows current semester by default
2. Change semester dropdown → updates balance display
3. Submit payment → creates payment for selected semester
4. Verify payment appears in student_detail for correct semester
5. Test with past (COMPLETED), current (ACTIVE), upcoming enrollments