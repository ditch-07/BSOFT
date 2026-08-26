# Automatic Student Progression Plan

## Goal
Implement automatic progression of students to the next semester based on semester end dates, running frequently (daily/every 10+ hours) when computer is on.

## Current State
- Progression is manual via `bulk_progress_students` view (admin clicks "Progress" button)
- New `get_current_enrollment` method determines display but doesn't change enrollment status
- No background job exists

## Requirements
1. Create a management command `progress_students_by_date` that:
   - Finds semesters where `end_date < today` (past semesters)
   - For each such semester, progresses active students to the next semester
   - Handles edge cases (completed programs, unpaid balances, deferrals)
   - Logs results and errors

2. Schedule it to run frequently (daily/every 10+ hours) via cron/systemd timer

3. Add admin dashboard widget showing last run status and results

## Design Decisions (Resolved)

### 1. Balance Requirement
**Decision**: Progress all active students regardless of outstanding balance
- Log warnings for students with outstanding balances for admin review
- Admin can see flagged students in dashboard widget

### 2. Frequency
**Decision**: Run every 10+ hours when computer is on
- Use systemd timer or cron with `@reboot` + interval
- Or daily cron if system is always on

### 3. Reporting
**Decision**: Admin dashboard widget showing:
- Last run timestamp
- Students progressed count
- Students completed/graduated count
- Students with outstanding balances (clickable to view)
- Errors/warnings

## Implementation Steps

1. **Create management command** `school/management/commands/progress_students_by_date.py`
2. **Add dashboard widget** to `dashboard` view showing last progression results
3. **Test manually** with `python manage.py progress_students_by_date`
4. **Document cron/systemd timer setup** for deployment

## Edge Cases Handled
- Student already has enrollment in next semester (idempotent - `get_or_create` handles)
- Multiple semesters ended at once (progress one semester at a time, in chronological order)
- Student in final semester of program (mark COMPLETED)
- Deferred/withdrawn students skipped (only `Enrollment.ACTIVE` progressed)
- Uses existing `create_academic_year_enrollments` helper for charges

## Files to Create/Modify
- `school/management/commands/progress_students_by_date.py` (new)
- `school/views.py` - add last progression data to dashboard context
- `templates/school/dashboard.html` - add dashboard widget
- Deployment docs for cron/systemd timer

## Validation
- Run command manually, verify correct students progressed
- Check enrollments created for new semester
- Verify completed students marked correctly
- Verify charges created for new enrollments
- Dashboard widget shows correct last run info