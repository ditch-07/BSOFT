# Implementation History and Migration Record

Historical implementation and migration notes. Some references below describe
the retired Nuxt frontend and Windows packaging; the current application uses
Django templates and runs through `manage.py`.

## A. Project overview

### Application purpose and workflows
The project is a student management and fee administration system for a school or college. The current Django app supports:

- Dashboard summarization and reminders
- Student registration, archive, detail views, and status management
- Academic year and semester administration
- Program setup and fee structure configuration
- Payment capture and financial reporting
- Enrollment and progression logic with semester-based year-level progression
- Daily/periodic reports and audit trails
- Backup configuration and restore workflows
- Background progression jobs and startup seeding

This is a server-rendered web application using Django templates and Bootstrap-based styling.

### Verified Python and Django versions
Verified in the local project environment:

- Python: 3.14.6
- Django: 6.1

Additional dependency versions confirmed in the environment:

- whitenoise: 6.12.0
- APScheduler: 3.11.3
- openpyxl: 3.1.5

### Installed dependencies and important packages
Important packages visible from the current environment and project configuration:

- Django 6.1
- django.contrib.* modules (admin, auth, contenttypes, sessions, messages, staticfiles)
- whitenoise for static serving
- APScheduler for background tasks
- openpyxl for Excel student import workflows
- SQLite as the database backend
- Local vendor assets: Bootstrap, Bootstrap Icons, Flatpickr

Runtime dependencies are listed in `requirements.txt`; development and demo-data dependencies are listed in `requirements-dev.txt`.

### Django settings modules and environment variables
Main settings module:

- `config/settings.py`

Project root URL config:

- `config/urls.py`

Path helpers:

- `config/paths.py`

Environment variables and runtime overrides currently used:

- `BSOFT_DATA_DIR`: overrides the writable data directory for SQLite database and backup storage.
- `BSOFT_DISABLE_SCHEDULER`: disables scheduler startup during PyInstaller analysis/build and when explicitly set.

Observed startup and deployment behavior:

- `launcher.py` ensures the data directory exists and is writable before running Django.
- `config/settings.py` resolves `APP_DATA_DIR` from the environment or default path, then stores `school.sqlite3` there.
- `config/settings.py` also configures `STATIC_ROOT` and `STATICFILES_DIRS` for packaged static assets.

### Repository directory structure
Verified structure at the project root:

- `config/` — Django settings and URL config
- `school/` — main Django app with models, views, templates, reports, utilities, middleware, management commands, scheduler
- `templates/` — base templates and app templates
- `static/` — CSS, images, local vendor assets
- `staticfiles/` — collected static output
- `data/` — writable application data directory (SQLite and backups)
- `backups/` — backup directory used by application backup workflows
- `build/`, `dist/`, `installer/` — packaged and installer artifacts
- `launcher.py` — Windows launcher that runs migrations and starts Django
- `manage.py` — standard Django management entry point
- `BSOFT_Student_Management.iss` — Inno Setup installer script
- `BSOFT_student_management.spec` — PyInstaller spec

### Existing frontend technologies and asset pipelines
Current frontend technology is not Nuxt; it is Django template rendering with Bootstrap.

Verified frontend characteristics:

- Django template engine
- `templates/base.html` and `templates/base_login.html` define shared layout
- `templates/school/*.html` render page-specific HTML
- Bootstrap CSS from static vendor assets
- Bootstrap Icons loaded via offline stylesheet (`static/css/bootstrap-icons-offline.css`)
- Flatpickr used for date pickers
- No JavaScript build system or frontend bundle pipeline was found in the project root as a normal Nuxt/Vite setup

### Database engine and configuration
Database engine:

- SQLite (`django.db.backends.sqlite3`)

Database path:

- `APP_DATA_DIR / "school.sqlite3"`
- `APP_DATA_DIR` resolves to `BSOFT_DATA_DIR` if set, else the project or packaged data directory

This architecture is intentionally separated from the application installation directory to support portable Windows packaging.

### Authentication and authorization mechanisms
Current authentication:

- Standard Django auth (`django.contrib.auth`) with `LoginView` and `LogoutView`
- `school.middleware.LoginRequiredMiddleware` redirects unauthenticated users to login for non-exempt paths
- `settings.LOGIN_URL = "login"`

Authorization roles are created via management command:

- `Registrar`
- `Finance`
- `Academic`

The group setup command assigns Django permissions such as add/view student, financial reports, payment capability, and academic setup permissions.

### Background jobs, APScheduler, signals, and application startup behavior
Verified startup behavior:

- `school/apps.py` defines `SchoolConfig.ready()`
- On app startup, it seeds academic years and starts the scheduler unless disabled by `BSOFT_DISABLE_SCHEDULER` or PyInstaller environment checks
- `school/scheduler.py` creates a `BackgroundScheduler` and schedules `run_auto_progression`
- The job runs every 6 hours and also runs once on startup after a short delay
- `run_auto_progression()` invokes the Django management command `progress_students_by_date`

Important startup command flow:

- `launcher.py` calls `run_migrations()` then `run_startup_commands()` before starting the Django server
- `run_startup_commands()` runs `seed_academic_years` and `setup_roles`

### Development, build, packaging, and installation workflows
Verified flows:

- Local development: `python manage.py runserver`
- Packaged launch: `python launcher.py` or packaged `.exe`
- PyInstaller packaging: `BSOFT_student_management.spec`
- Windows installer: `BSOFT_Student_Management.iss`
- Application startup in packaged mode includes automatic migrations and environment setup

The deployment documentation in `DEPLOYMENT_FIXES.md` explains that the packaged architecture intentionally splits writable data into a `%ProgramData%` style location and bundled code into the application folder.

## B. Django applications and business logic

### Django apps
Only one Django app is currently installed at the application level:

- `school` — the core student management, enrollment, fee, payment, reporting, and admin app

`config/urls.py` includes `school.urls` at the root path, so the app owns the main application UI.

### Models and relationships
Core model relationships (verified from `school/models.py`):

- `AcademicYear` → contains semesters and student intake years
- `Semester` → belongs to an academic year, contains enrollment periods
- `Program` → student study program, linked to fee structures and enrollments
- `FeeStructure` → `Program + Year Level + Semester`
- `FeeStructureItem` → individual charges inside a fee structure
- `Student` → person enrolled in a program, has status and personal details
- `Enrollment` → student + program + semester + year-level state
- `StudentCharge` → generated fee item charges for a student enrollment
- `Payment` → receipt-based payment records with semester association
- `StudentStatusLog` → audit trail of student status changes
- `AuditLog` → general actions and user activity log
- `BackupConfig` → singleton backup settings for backup path and retention configuration
- `TimeOverride` → singleton freeze time mechanism for testing and semester logic

Important business rules verified in models:

- Academic years and semesters validate date ordering
- Unique constraints prevent duplicate semester periods per year and duplicate fee structures per program/year/semester
- Student enrollments validate program/year level against program duration
- Fee compositions and charges are generated using enrollment + fee structure logic
- Payment balance helpers calculate charged vs paid amounts

### Views and responsibilities
The project uses function-based views in `school/views.py`. High-level responsibilities include:

- Dashboard and reminders
- Student list, create, edit, detail, archive, status change, import
- Academic year and semester management
- Fee structure management and bulk fee configuration
- Payment recording and financial records
- Reports: enrollment, outstanding balances, fee audit, payment methods, revenue, daily collections, status history
- User management
- Audit log and backup management
- Time override testing page

The route names in `school/urls.py` make the functional surface explicit.

### URL configuration and route names
Verified route groups from `school/urls.py`:

- Authentication: `login`, `logout`
- Dashboard: `dashboard`
- Reminders: `reminders`
- Reports: `reports_index`, `enrollment_report`, `outstanding_report`, `fee_audit_report`, `payment_methods_report`, `program_revenue_report`, `daily_collections_report`, `status_history_report`
- Academic management: `academic_year_list`
- Semester management: `semester_list`, `semester_create`, `semester_edit`
- Fee configuration: `fee_structure_list`, `fee_structure_create`, `bulk_fee_configuration`, `fee_structure_edit`
- Program management: `program_list`, `program_create`
- Student management: `student_list`, `student_create`, `student_import`, `student_edit`, `student_search`, `student_list_search`, `student_detail`, `student_status_change`
- Archive: `archive_list`, `archive_search`, `archive_detail`
- Payment and records: `payment_create`, `financial_records`
- Backups: `backup_index`, `backup_create`, `backup_download`, `backup_restore`, `backup_upload`, `backup_settings`
- Admin/debug: `time_override`
- User management: `user_list`, `user_create`
- Audit log: `audit_log_list`

### Forms, serializers, managers, services, signals, middleware
Verified forms:

- `school/forms.py` contains model forms and custom formset validation for fee structures
- Bootstrap styling is injected via `BootstrapFormMixin`
- `FeeStructureItemFormSet` validates duplicate fee names within a structure
- `BulkFeeForm` is used for bulk fee configuration

Verified services and helpers:

- `school/models.py` includes helper functions such as `student_balance`, `semester_financials`, `outstanding_students`, `payment_methods_breakdown`, `program_revenue`, `daily_collections`, `enrollment_summary`, and `student_status_history`
- `school/views.py` contains service-like helpers such as `create_charges_for_fee_structure` and `create_academic_year_enrollments`

Signals: none verified in the app itself. Startup behavior is implemented in `AppConfig.ready()` and management command startup rather than Django signals.

Middleware:

- `school.middleware.LoginRequiredMiddleware` enforces auth on non-exempt paths

Permissions and access restrictions:

- Standard login requirement is enforced globally for application pages
- Group-based permission model exists through `setup_roles.py`
- Views use `@login_required`, `@permission_required`, and `@user_passes_test` patterns in the view layer where applicable

### Important validation and business rules
Validated or clearly implemented rules include:

- Academic years must start before they end
- Semesters must fit within their academic year and not overlap invalidly
- Program duration determines maximum year level
- Fee item names must be unique within a fee structure
- Student enrollments are unique per student + semester
- Student status flows are tracked in `StudentStatusLog`
- Automatic progression logic uses semester and date-based progression rules

### Existing integrations and background tasks
Verified integrations and background tasks:

- `seed_academic_years` management command seeds academic year data
- `progress_students_by_date` command advances students according to date rules
- Backup system and `backup_auto` management command
- Student import capability using `openpyxl`, likely via `school.utils.student_import` and forms
- Local file-system backup configuration using `BackupConfig`

## C. Complete template inventory

Current template root:

- `templates/base.html`
- `templates/base_login.html`
- `templates/school/`
- `templates/school/reports/`

### Base layouts and shared templates

| Template | Purpose | Notes |
| --- | --- | --- |
| `templates/base.html` | Shared authenticated app shell, navbar, sidebar, report menus | Core layout; includes Bootstrap, Flatpickr, icons, app CSS |
| `templates/base_login.html` | Login page shell | Separate unauthenticated login layout |

### Application templates

| Template path | Purpose | View / route | Migration status |
| --- | --- | --- | --- |
| `templates/school/dashboard.html` | Main dashboard overview | `dashboard` | Not started |
| `templates/school/reminders.html` | Reminder and follow-up list | `reminders` | **Migrated** (`frontend/pages/reminders.vue`) |
| `templates/school/student_list.html` | Student listing and search | `student_list` | Not started |
| `templates/school/student_register.html` | Student registration form | `student_create` | Not started |
| `templates/school/student_detail.html` | Student detail record | `student_detail` | Not started |
| `templates/school/student_archive_list.html` | Archived students list | `archive_list` | Not started |
| `templates/school/student_archive_detail.html` | Archived student detail | `archive_detail` | Not started |
| `templates/school/student_status_form.html` | Status change workflow | `student_status_change` | Not started |
| `templates/school/student_import.html` | Spreadsheet import workflow | `student_import` | Not started |
| `templates/school/payment_create.html` | Payment entry form | `payment_create` | **Migrated** (`frontend/pages/payments/new.vue`) |
| `templates/school/financial_records.html` | Semester financial summary | `financial_records` | **Migrated** (`frontend/pages/financial-records.vue`) |
| `templates/school/academic_year_list.html` | Academic year overview | `academic_year_list` | Not started |
| `templates/school/semester_list.html` | Semester listing | `semester_list` | Not started |
| `templates/school/semester_form.html` | Semester create/edit form | `semester_create`, `semester_edit` | Not started |
| `templates/school/semester_create_with_fees.html` | Fee-oriented semester creation flow | likely part of semester setup | Not started |
| `templates/school/program_list.html` | Program list | `program_list` | Not started |
| `templates/school/program_create.html` | Program create form | `program_create` | Not started |
| `templates/school/fee_structure_list.html` | Fee structure summary by semester | `fee_structure_list` | Not started |
| `templates/school/fee_structure_form.html` | Fee structure create/edit form | `fee_structure_create`, `fee_structure_edit` | Not started |
| `templates/school/bulk_fee_form.html` | Bulk fee configuration | `bulk_fee_configuration` | Not started |
| `templates/school/fee_setup.html` | Fee setup and configuration dashboard | likely internal setup helper | Not started |
| `templates/school/form.html` | Generic form wrapper | template helper | Not started |
| `templates/school/login.html` | Login screen | `login` | Not started |
| `templates/school/audit_log_list.html` | Audit trail list | `audit_log_list` | **Migrated** (`frontend/pages/audit-logs.vue`) |
| `templates/school/user_list.html` | User/admin management list | `user_list` | **Migrated** (`frontend/pages/users.vue`) |
| `templates/school/user_form.html` | User create form | `user_create` | **Migrated** (`frontend/pages/users/new.vue`) |
| `templates/school/backup_index.html` | Backup landing page | `backup_index` | **Migrated** (`frontend/pages/backups.vue`) |
| `templates/school/backup_settings.html` | Backup configuration form | `backup_settings` | **Migrated** (`frontend/pages/backup/settings.vue`) |
| `templates/school/time_override.html` | Testing time freeze for date logic | `time_override` | **Migrated** (`frontend/pages/time-override.vue`) |

### Reports templates

| Template path | Purpose |
| --- | --- |
| `templates/school/reports/_base.html` | Shared report page shell |
| `templates/school/reports/index.html` | Reports landing page |
| `templates/school/reports/enrollment.html` | Enrollment summary |
| `templates/school/reports/outstanding.html` | Outstanding balances report |
| `templates/school/reports/fee_audit.html` | Fee configuration audit |
| `templates/school/reports/payment_methods.html` | Payment method totals |
| `templates/school/reports/program_revenue.html` | Program revenue comparison |
| `templates/school/reports/daily_collections.html` | Daily collection report |
| `templates/school/reports/status_history.html` | Student status change history |

### Reusable fragments and dynamic selectors
Observed templating patterns:

- `base.html` is the primary authenticated shell and contains navigation and report submenu logic.
- Templates are rendered as server-side pages, not reusable Nuxt components.
- Login, logout, password reset, and admin flows are Django-native.
- Dynamic selection and permissions are determined via `request` context and Django template tags.
- `templates/school/form.html` likely serves as a generic form layout wrapper.

Important note: The repo does not appear to ship a dedicated email template system or PDF-template directory as a first-class frontend artifact; PDF/report generation is likely generated through backend logic and report templates rather than Nuxt.

## D. Static asset inventory

Asset directories verified:

- `static/css/app.css`
- `static/css/bootstrap-icons-offline.css`
- `static/img/login-illustration.svg`
- `static/vendor/bootstrap/`
- `static/vendor/flatpickr/`

Assets currently used by the Django template frontend:

- Bootstrap CSS and likely Bootstrap JS bundles from vendor package
- Flatpickr CSS for date picker UI
- Bootstrap Icons local CSS override
- Application-specific CSS in `static/css/app.css`
- Login illustration image

Static asset strategy:

- Existing server-rendered Django page styling should be preserved until the Nuxt migration defines replacement components.
- Assets that remain backend-facing, such as report images or server-generated presentations, should remain in Django/static or be rehosted by Nuxt only where appropriate.
- No Nuxt asset tree exists yet; therefore no existing frontend asset migration has been performed.

## E. Route and feature matrix

| Existing page / feature | Current Django route | Current rendering/view | Nuxt route (planned) | Required API (planned) | Status |
| --- | --- | --- | --- | --- | --- |
| Login | `/login/` | `auth_views.LoginView` | `/login` | `POST /api/auth/login/` | Planned |
| Dashboard | `/` | `dashboard` | `/dashboard` or `/` | `GET /api/dashboard/` | Planned |
| Reminders | `/reminders/` | `reminders` | `/reminders` | `GET /api/reminders/` | Planned |
| Student list | `/students/` | `student_list` | `/students` | `GET /api/students/` | Planned |
| Student create | `/students/new/` | `student_create` | `/students/new` | `POST /api/students/` | Planned |
| Student edit | `/students/<id>/edit/` | `student_edit` | `/students/:id/edit` | `PUT /api/students/:id/` | Planned |
| Student detail | `/students/<id>/` | `student_detail` | `/students/:id` | `GET /api/students/:id/` | Planned |
| Student archive | `/students/archive/` | `archive_list` | `/students/archive` | `GET /api/archive/` | Planned |
| Payment entry | `/payments/new/` | `payment_create` | `/payments/new` | `POST /api/payments/create/` | **Done** |
| Payment history | — | — | `/payments` | `GET /api/payments/` | **Done** |
| Payment receipt | — | — | `/payments/:id/receipt` | `GET /api/payments/:id/receipt/` | **Done** |
| Financial records | `/financial-records/` | `financial_records` | `/financial-records` | `GET /api/financial-records/` | **Done** |
| Student payment history | — | — | `/students/:id` (integrated) | `GET /api/students/:id/payment-history/` | **Done** |
| Academic years | `/academic-years/` | `academic_year_list` | `/academic-years` | `GET /api/academic-years/` | Planned |
| Semesters | `/semesters/` | `semester_list` | `/semesters` | `GET /api/semesters/` | Planned |
| Semester create | `/semesters/new/` | `semester_create` | `/semesters/new` | `POST /api/semesters/` | Planned |
| Fee structures | `/semesters/<id>/fee-structures/` | `fee_structure_list` | `/semesters/:id/fee-structures` | `GET /api/semesters/:id/fee-structures/` | Planned |
| Program management | `/programs/` | `program_list` | `/programs` | `GET /api/programs/` | Planned |
| Reports index | `/reports/` | `reports_index` | `/reports` | `GET /api/reports/` | **Done** |
| Enrollment report | `/reports/enrollment/` | `enrollment_report` | `/reports/enrollment` | `GET /api/reports/enrollment/` | **Done** |
| Outstanding report | `/reports/outstanding/` | `outstanding_report` | `/reports/outstanding` | `GET /api/reports/outstanding/` | **Done** |
| Fee audit | `/reports/fee-audit/` | `fee_audit_report` | `/reports/fee-audit` | `GET /api/reports/fee-audit/` | **Done** |
| Payment methods report | `/reports/payment-methods/` | `payment_methods_report` | `/reports/payment-methods` | `GET /api/reports/payment-methods/` | **Done** |
| Program revenue | `/reports/program-revenue/` | `program_revenue_report` | `/reports/program-revenue` | `GET /api/reports/program-revenue/` | **Done** |
| Daily collections | `/reports/daily-collections/` | `daily_collections_report` | `/reports/daily-collections` | `GET /api/reports/daily-collections/` | **Done** |
| Status history | `/reports/status-history/` | `status_history_report` | `/reports/status-history` | `GET /api/reports/status-history/` | **Done** |
| Reminders | `/reminders/` | `reminders` | `/reminders` | `GET /api/reminders/` | **Done** |
| Backup views | `/backups/` etc. | `backup_*` | `/backups` | `GET /api/backups/`, `POST /api/backups/create/`, etc. | **Done** |
| User management | `/users/`, `/users/new/` | `user_list`, `user_create` | `/users`, `/users/new` | `GET /api/users/`, `POST /api/users/create/`, `PATCH /api/users/:id/` | **Done** |
| Audit log | `/audit-log/` | `audit_log_list` | `/audit-logs` | `GET /api/audit-logs/` | **Done** |
| Time override | `/time-override/` | `time_override` | `/time-override` | `GET /api/time-override/`, `POST /api/time-override/` | **Done** |

This matrix is based on the verified Django URL patterns and will be refined as the Nuxt design is implemented.

## F. Deployment and packaging inventory

### Launcher and startup scripts
Verified important startup files:

- `launcher.py`
- `manage.py`
- `school/apps.py`
- `school/scheduler.py`

Launcher behavior:

- validates writable data directory
- sets `BSOFT_DATA_DIR` if present
- sets Django settings module
- triggers migrations before startup
- runs startup commands (`seed_academic_years`, `setup_roles`)
- starts a local Django webserver and opens the browser

### Path and settings configuration
Files involved:

- `config/paths.py`
- `config/settings.py`

Important path behavior:

- In development, the app uses the repository directory and project `data/` folder
- In packaged mode, it uses the frozen executable directory or environment override
- `STATICFILES_DIRS` uses the local static path under the packaged app
- settings are intentionally portable across development and packaged deployment

### PyInstaller and installer
Verified packaging files:

- `BSOFT_student_management.spec`
- `BSOFT_Student_Management.iss`

Key deployment characteristics from the packaging files and deployment doc:

- application bundle includes config, school app, templates, and static assets
- hidden imports include Django, auth, staticfiles, APScheduler, school modules, and custom commands
- installer uses Inno Setup and creates Windows desktop/Start Menu artifacts
- the Windows deployment separates writable data from install location by using ProgramData-style storage

### Database and backup locations
Verified:

- SQLite database stored in `APP_DATA_DIR / "school.sqlite3"`
- backup directory created as `APP_DATA_DIR / "backups"`

The deployment notes explicitly describe a separation between installed application files and persistent data:

- `Program Files\BSOFT Student Management` for read-only application files
- `ProgramData\BSOFT Student Management` for writable database and backups

### Environment variables and safeguards
Verified:

- `BSOFT_DATA_DIR` — persistent database and backup path override
- `BSOFT_DISABLE_SCHEDULER` — build-time or testing disable flag for the background scheduler

Additional safeguards:

- scheduler startup is skipped during PyInstaller analysis or when explicitly disabled
- migration execution is idempotent and run automatically at startup

### Runtime requirement for Node.js
No Nuxt frontend or Node build pipeline exists in the current codebase. For the existing deployment architecture, the package currently runs as a Django + Python solution, not a Node.js app. A future Nuxt frontend would add Node runtime requirements for development and build phases, but the current packaged Windows app remains Python/Django-based.

## G. Migration plan

### Baseline migration priorities
1. Create an API layer on top of the existing Django app before introducing a Nuxt frontend.
2. Migrate the dashboard and student-management workflows first, because they are central business flows.
3. Split the financial and reporting flows after the core CRUD flows are exposed as APIs.
4. Move the auth and session model first to avoid breaking login and authorization semantics.
5. Preserve the existing deployment model and Windows packaging architecture until a Nuxt integration is explicitly designed.

### Dependency and risk notes
- The repository is currently a single app and does not have a preexisting REST API layer.
- Template and form behavior are tightly coupled to Django view rendering.
- Authentication and middleware rules are global and must be preserved carefully.
- Background jobs and startup seeding must continue to run during packaged deployment or their execution must be explicitly controlled.
- The project uses server-rendered pages and local static vendor assets; a Nuxt migration must decide which assets remain backend-only and which become frontend-managed.

### Verification criteria for migration work
- Existing Django routes remain functional as a backend API source of truth.
- Student CRUD, fee structures, reports, and backup flows still pass server-side validation.
- Authentication and group permissions remain consistent.
- Database schema and migration behavior remain stable.
- The packaged Windows deployment continues to work when API server and frontend are served in the local app flow.

### Current migration status
- Project inventory: complete
- Auth and deployment baseline: documented
- Frontend migration: **Segments 1-6 completed** (Dashboard, Students, Academic Setup, Payments & Financial Records, Reports & Reminders, Administration & Backups)
- API-layer design: **completed** (all core domain endpoints implemented)
- Nuxt frontend implementation: **Segments 1-6 completed**
- Verification and packaging validation: pending
- Remaining: Segment 7 (Packaging)

## Change log

- 2026-10-10: **Segment 6 completed** — Implemented Administration, Audit Logs, Backup/Restore, and Time Override migration:
  - Added Django API endpoints in `school/api.py`:
    - `api_user_list` (GET `/api/users/`) — paginated user listing with groups
    - `api_user_create` (POST `/api/users/create/`) — user creation with group assignment
    - `api_user_update` (PATCH `/api/users/<id>/`) — user status, staff, and group updates
    - `api_audit_log_list` (GET `/api/audit-logs/`) — audit trail with filters and pagination
    - `api_backup_list` (GET `/api/backups/`) — backup listing with config status
    - `api_backup_create` (POST `/api/backups/create/`) — create new database backup
    - `api_backup_download` (GET `/api/backups/download/<filename>/`) — download backup file
    - `api_backup_restore` (POST `/api/backups/restore/<filename>/`) — restore with safety backup
    - `api_backup_upload` (POST `/api/backups/upload/`) — upload backup file with validation
    - `api_backup_settings` (GET/PATCH `/api/backup/settings/`) — backup configuration
    - `api_time_override` (GET/POST `/api/time-override/`) — get/set/clear time override
  - Reused existing models: `User`, `Group`, `AuditLog`, `BackupConfig`, `TimeOverride`
  - Permissions enforced: superuser-only for user/backup/time-override; `view_auditlog` for audit logs
  - Created Nuxt pages in `frontend/pages/`:
    - `users.vue` — user listing with role editing, status toggles, pagination
    - `users/new.vue` — user creation with group assignment
    - `audit-logs.vue` — audit trail with action/user/date filters, collapsible details
    - `backups.vue` — backup list with create/download/restore/upload, config status
    - `backup/settings.vue` — backup configuration with quick paths
    - `time-override.vue` — time freeze/clear with status display
  - Updated `frontend/app/app.vue` navigation to include Backups, Audit Log, Users, Time Override
  - Registered API routes in `school/urls.py`
  - All existing Django tests pass (`python manage.py test school`)
  - Nuxt production build succeeds (`npm run build` in `frontend/`)

- 2026-10-10: **Segment 5 completed** — Implemented Reports, Analytics, Reminders, and Exports migration:
  - Added Django API endpoints in `school/api.py`:
    - `api_reports_index` (GET `/api/reports/`) — report catalog
    - `api_enrollment_report` (GET `/api/reports/enrollment/`) — enrollment by program/year/status
    - `api_outstanding_report` (GET `/api/reports/outstanding/`) — student balances with totals
    - `api_fee_audit_report` (GET `/api/reports/fee-audit/`) — missing fee structures
    - `api_payment_methods_report` (GET `/api/reports/payment-methods/`) — method breakdown
    - `api_program_revenue_report` (GET `/api/reports/program-revenue/`) — revenue by program
    - `api_daily_collections_report` (GET `/api/reports/daily-collections/`) — daily cashbook
    - `api_status_history_report` (GET `/api/reports/status-history/`) — status change log
    - `api_reminders` (GET `/api/reminders/`) — students with missing details
  - Reused existing report helpers: `enrollment_summary`, `outstanding_students`, `unconfigured_fee_structures`, `payment_methods_breakdown`, `program_revenue`, `daily_collections`, `student_status_history`, `students_with_missing_details`
  - Permissions enforced per report type (`view_student`, `can_view_financial_reports`, `can_view_outstanding_reports`, `view_feestructure`, `view_studentstatuslog`)
  - Created Nuxt pages in `frontend/pages/reports/` and `frontend/pages/reminders.vue`:
    - `reports.vue` — reports landing page with cards
    - `enrollment.vue` — enrollment summary with program/year/status filters, CSV export
    - `outstanding.vue` — outstanding balances with summary cards, CSV export
    - `fee-audit.vue` — missing fee structures with direct config links
    - `payment-methods.vue` — method breakdown with percentages
    - `program-revenue.vue` — revenue comparison with totals
    - `daily-collections.vue` — daily cashbook with date range filter
    - `status-history.vue` — status change log with student/date filters
    - `reminders.vue` — students with missing details, edit links
  - Updated `frontend/app/app.vue` navigation to include Reports and Reminders
  - All existing Django tests pass
  - Nuxt production build succeeds

- 2026-10-10: **Segment 4 completed** — Implemented Payments, Receipts, and Financial Records migration:
  - Added Django API endpoints in `school/api.py`:
    - `api_payment_list` (GET `/api/payments/`) — paginated payment listing with filters
    - `api_payment_create` (POST `/api/payments/create/`) — payment recording with validation
    - `api_payment_detail` (GET `/api/payments/<id>/`) — individual payment detail
    - `api_payment_receipt` (GET `/api/payments/<id>/receipt/`) — receipt data for printing
    - `api_financial_records` (GET `/api/financial-records/`) — institution-wide financial summaries by year/semester
    - `api_student_payment_history` (GET `/api/students/<id>/payment-history/`) — student balances and payment history
    - `api_student_balance` (GET `/api/students/<id>/balance/<semester_id>/`) — charged/paid/balance for payment form
    - `api_student_enrollments_for_payment` (GET `/api/students/<id>/enrollments-for-payment/`) — valid semesters for payment dropdown
  - Reused existing business logic: `student_balance`, `semester_financials`, `PaymentForm`, audit logging via `log_action`
  - Permissions enforced: `can_record_payments` for payment creation, `can_view_financial_reports` for records/receipts
  - Created Nuxt pages in `frontend/pages/`:
    - `payments/new.vue` — payment entry with student search, semester selection, balance display, form validation
    - `payments/index.vue` — paginated payment history with filters (student, semester, method, date range)
    - `payments/[id]/receipt.vue` — printable receipt with student, semester, amount, method, balance summary
    - `financial-records.vue` — institution-wide financial records by academic year/semester with grand totals, print-ready
    - Updated `students/[id].vue` — integrated semester balances and payment history from new API
  - Updated `frontend/app/app.vue` navigation to include Payments and Financial Records
  - Registered API routes in `school/urls.py`
  - All existing Django tests pass (`python manage.py test school`)
  - Nuxt production build succeeds (`npm run build` in `frontend/`)

- 2026-10-09: Captured initial project inventory and migration baseline in `docs/proj.md`.
- No app logic was altered as part of this baseline audit.
