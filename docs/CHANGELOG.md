# Change Log

## 2026-10-10

### Completed work (Segment 6: Administration, Audit Logs, Backup/Restore, Time Override)
- Added Django API endpoints in `school/api.py` for administration:
  - `api_user_list` — paginated user listing with groups
  - `api_user_create` — user creation with group assignment
  - `api_user_update` — user status, staff, and group updates
  - `api_audit_log_list` — audit trail with action/user/date filters and pagination
  - `api_backup_list` — backup listing with config status
  - `api_backup_create` — create new database backup
  - `api_backup_download` — download backup file
  - `api_backup_restore` — restore with safety backup
  - `api_backup_upload` — upload backup file with validation
  - `api_backup_settings` — backup configuration (GET/PATCH)
  - `api_time_override` — get/set/clear time override
- Reused existing models: `User`, `Group`, `AuditLog`, `BackupConfig`, `TimeOverride`
- Permissions enforced: superuser-only for user/backup/time-override; `view_auditlog` for audit logs
- Created Nuxt pages:
  - `frontend/pages/users.vue` — user listing with role editing, status toggles, pagination
  - `frontend/pages/users/new.vue` — user creation with group assignment
  - `frontend/pages/audit-logs.vue` — audit trail with filters, collapsible details
  - `frontend/pages/backups.vue` — backup list with create/download/restore/upload
  - `frontend/pages/backup/settings.vue` — backup configuration with quick paths
  - `frontend/pages/time-override.vue` — time freeze/clear with status display
- Updated `frontend/app/app.vue` navigation for Backups, Audit Log, Users, Time Override
- Registered API routes in `school/urls.py`

### Completed work (Segment 5: Reports, Analytics, Reminders, Exports)
- Added Django API endpoints in `school/api.py`:
  - `api_reports_index` — report catalog
  - `api_enrollment_report` — enrollment by program/year/status
  - `api_outstanding_report` — student balances with totals
  - `api_fee_audit_report` — missing fee structures
  - `api_payment_methods_report` — method breakdown
  - `api_program_revenue_report` — revenue by program
  - `api_daily_collections_report` — daily cashbook
  - `api_status_history_report` — status change log
  - `api_reminders` — students with missing details
- Reused existing report helpers: `enrollment_summary`, `outstanding_students`, `unconfigured_fee_structures`, `payment_methods_breakdown`, `program_revenue`, `daily_collections`, `student_status_history`, `students_with_missing_details`
- Permissions enforced per report type
- Created Nuxt pages:
  - `frontend/pages/reports.vue` — reports landing page
  - `frontend/pages/reports/enrollment.vue` — enrollment summary with filters, CSV
  - `frontend/pages/reports/outstanding.vue` — outstanding balances with summary cards
  - `frontend/pages/reports/fee-audit.vue` — missing fee structures with config links
  - `frontend/pages/reports/payment-methods.vue` — method breakdown with percentages
  - `frontend/pages/reports/program-revenue.vue` — revenue comparison with totals
  - `frontend/pages/reports/daily-collections.vue` — daily cashbook with date range
  - `frontend/pages/reports/status-history.vue` — status change log with filters
  - `frontend/pages/reminders.vue` — students with missing details, edit links
- Updated `frontend/app/app.vue` navigation for Reports and Reminders

### Completed work (Segment 4: Payments, Receipts, Financial Records)
- Added Django API endpoints in `school/api.py` for payments and financial records:
  - `api_payment_list` — paginated payment listing with filters
  - `api_payment_create` — payment recording with server-side validation, audit logging, transaction safety
  - `api_payment_detail` — individual payment retrieval with balance context
  - `api_payment_receipt` — receipt data for printable confirmation
  - `api_financial_records` — institution-wide financial summaries grouped by academic year/semester
  - `api_student_payment_history` — student-specific balances, semester breakdowns, and payment history
  - `api_student_balance` / `api_student_enrollments_for_payment` — helper endpoints for payment form
- Reused existing financial helpers (`student_balance`, `semester_financials`) and form validation (`PaymentForm`)
- Enforced permissions: `can_record_payments` for creation, `can_view_financial_reports` for records/receipts
- Created Nuxt pages:
  - `frontend/pages/payments/new.vue` — payment entry with student search, semester dropdown, real-time balance
  - `frontend/pages/payments/index.vue` — payment history with filters and pagination
  - `frontend/pages/payments/[id]/receipt.vue` — printable receipt page
  - `frontend/pages/financial-records.vue` — financial records with year filter, grand totals, print styles
  - Updated `frontend/pages/students/[id].vue` — integrated payment history and semester balances
  - Updated `frontend/app/app.vue` navigation for Payments and Financial Records
- Registered all API routes in `school/urls.py`

### Validation performed
- Django project health check: `python manage.py check` — passed.
- Django school suite: `python manage.py test school --verbosity 2` — passed.
- Nuxt production build: `npm run build` in `frontend/` — passed (4m 15s).

### Status
- Segments 4, 5, 6 complete: All core application modules migrated to Nuxt with Django API backend.
- Existing Django views remain functional as fallback.
- Ready for Segment 7: Production integration, Windows packaging, final verification.

## 2026-10-09

### Completed work
- Added a Nuxt-ready API layer in `school/api.py` for dashboard and student payloads.
- Registered the API endpoints in `school/urls.py` so the frontend can consume them through Django without custom routing hacks.
- Updated the Nuxt shell in `frontend/app/app.vue` to provide a simple dashboard navigation and page layout.
- Added runtime API configuration to `frontend/nuxt.config.ts` for the backend base URL.
- Extended the migration backend and frontend to cover the academic setup segment: programs, academic years, semesters, and fee setup views.
- Added reusable API helpers in `frontend/composables/useApi.ts` and page screens for the academic setup flow.

### Validation performed
- Django project health check: `python manage.py check` (via project venv) — passed.
- Django school suite: `python manage.py test school --verbosity 2` — passed.
- Nuxt production build: `npm run build` in `frontend/` — passed.

### Status
- The backend and scaffolded frontend are now in a working prototype state.
- The migration remains incremental, but the API integration required for the first frontend slices is now in place.
- The academic/fee setup segment has been implemented and connected to the real Django domain logic.
