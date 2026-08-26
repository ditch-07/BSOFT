# Fix: Mark Old Enrollment as Completed During Progression

## Problem
When `bulk_progress_students` progresses students to the next semester:
- Creates new `Enrollment` for target semester (ACTIVE)
- **Does NOT mark source enrollment as COMPLETED** → old enrollment stays ACTIVE

## Impact
- Duplicate active enrollments in same academic year
- New academic year balance card double-counts (iterates all active enrollments)
- Dashboard "active this semester" works correctly (filters by specific semester)

## Fix
In `school/views.py` `bulk_progress_students` function (around line 922), after creating new enrollment:
```python
# Mark the old enrollment as completed
current.status = Enrollment.COMPLETED
current.save(update_fields=["status"])
```

## Files to Modify
- `school/views.py` - `bulk_progress_students` view

## Validation
1. Progress a student from Semester 1 → Semester 2
2. Check: Old enrollment status = COMPLETED
3. Check: New enrollment status = ACTIVE
4. Check: Student list shows Semester 2
5. Check: Academic year balance card shows correct single enrollment per semester