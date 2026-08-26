# Student Detail - Academic Year Balance Fix

## Problem
Current "Owed This Academic Year" only sums balances for semesters where charges exist. It doesn't account for semesters without configured fee structures, and the display is not prominent enough.

## Requirements
1. **Base on current academic year** (where `is_current=True`)
2. **Project from FeeStructure** for unconfigured semesters - calculate what student *should* owe based on their enrollment program/year_level
3. **Show summary card at top** with:
   - Per-semester balance (charged - paid)
   - Total academic year balance (sum of both semesters)
   - Visual indicators for configured vs projected amounts

## Implementation Plan

### 1. Update `student_detail` view (`school/views.py:661-715`)

**New logic for `total_owed_this_year`:**
```python
current_year = AcademicYear.objects.filter(is_current=True).first()
if current_year:
    # Get student's active enrollments in current year
    enrollments = student.enrollments.filter(
        semester__academic_year=current_year, 
        status=Enrollment.ACTIVE
    ).select_related('semester', 'program')
    
    semester_balances = []
    total_year_balance = Decimal("0")
    
    for enrollment in enrollments:
        semester = enrollment.semester
        
        # Actual charges (from StudentCharge)
        charged = student.charges.filter(
            enrollment__semester=semester
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        
        paid = student.payments.filter(semester=semester).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")
        
        actual_balance = charged - paid
        
        # Projected charges (from FeeStructure) if no charges exist
        projected_charged = Decimal("0")
        if charged == 0:
            fee_structure = FeeStructure.objects.filter(
                program=enrollment.program,
                year_level=enrollment.year_level,
                semester=semester
            ).prefetch_related("items").first()
            if fee_structure:
                projected_charged = sum(item.amount for item in fee_structure.items.all(), Decimal("0"))
        
        # Use projected if no actual charges
        effective_charged = charged if charged > 0 else projected_charged
        effective_balance = effective_charged - paid
        
        semester_balances.append({
            "semester": semester,
            "charged": charged,
            "projected_charged": projected_charged,
            "paid": paid,
            "balance": effective_balance,
            "is_projected": charged == 0 and projected_charged > 0,
        })
        total_year_balance += effective_balance
    
    context["semester_balances"] = semester_balances
    context["total_year_balance"] = total_year_balance
```

### 2. Update `student_detail.html` template

**Replace current "Owed This Academic Year" card with new summary card:**
- Show each semester in current academic year with balance
- Show total year balance
- Visual distinction for projected vs actual charges
- Keep existing detailed tables below for full history

### 3. Key calculations
- **Semester balance** = effective_charged - paid
- **Academic year total** = sum of semester balances
- **Projected** flag: true when no StudentCharges exist but FeeStructure exists

### 4. Edge cases
- No current academic year → show N/A
- No active enrollments in current year → show $0
- Student has multiple enrollments in same semester (shouldn't happen due to unique constraint)
- FeeStructure exists but no items → $0 projected

## Files to Modify
1. `school/views.py` - `student_detail` view
2. `templates/school/student_detail.html` - new summary card