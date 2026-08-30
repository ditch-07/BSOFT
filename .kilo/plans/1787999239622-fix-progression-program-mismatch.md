# Fix: Automatic Progression Program Mismatch

## Problem
When a student's program is changed via the edit form, automatic progression fails with:
```
"Enrollment program must match the student's program."
```

## Root Cause
In `create_academic_year_enrollments()` (views.py:61), new enrollments are created using `student.program` (the student's **current** program). However, the progression logic in both `bulk_progress_students` view and `progress_students_by_date` management command correctly uses the program from the **source enrollment** (`current.program`) for the immediate next enrollment.

This creates a mismatch:
1. Student was in Program A, completed Semester 1
2. Student's program changed to Program B via edit
3. Progression to Semester 2:
   - Immediate enrollment created with Program A (from source enrollment) ✓
   - `create_academic_year_enrollments` creates future enrollments with Program B (student's current program) ✗
4. Validation fails because enrollment.program (A) != student.program (B)

## Files to Fix
1. `school/views.py` - `create_academic_year_enrollments()` function (line 61)
2. `school/views.py` - `bulk_progress_students()` view (line 2104) - pass program
3. `school/management/commands/progress_students_by_date.py` (line 157) - pass program

## Solution
Modify `create_academic_year_enrollments()` to accept an optional `program` parameter. If provided, use it instead of `student.program`. This maintains program continuity within the same academic year.

## Changes

### 1. Update `create_academic_year_enrollments` function
```python
def create_academic_year_enrollments(student, start_semester, start_year_level, program=None):
    """
    Create enrollments and charges for all semesters in the academic year
    of `start_semester` from that semester onward.
    """
    if program is None:
        program = student.program
    # ... rest of function uses `program` instead of `student.program`
```

### 2. Update call sites to pass the program
- `bulk_progress_students` (line 2104): pass `program` (from `current.program`)
- `progress_students_by_date` (line 157): pass `program` (from `current.program`)
- `student_create` (line 1490): pass `student_form.instance.program`
- `seed_students` command: pass `student.program`

## Validation
The Enrollment model's `clean()` method validates `enrollment.program == student.program`. This is the intended behavior - a student's enrollments should match their current program. The fix ensures that when progressing within an academic year, the program stays consistent with the source enrollment.

## Risk
Low - this only affects the progression logic. Existing enrollments are not modified.