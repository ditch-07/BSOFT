# NRZ Student Management — Capabilities and Functionality

Reference date: 2026-10-30. This document describes what the application does today,
grounded in the code in `school/`, `config/` and the packaging scripts. It is a
capability map, not an installation guide — see `DEPLOYMENT_FIXES.md` for build and
installer steps and `docs/proj.md` for the system inventory.

---

## 1. What NRZ Student Management is

A single-tenant student administration and fee-collection system for a technical
college or trade school. It runs as a local Windows application: a Django server
launched by `launcher.py`, opened in the browser at `http://127.0.0.1:8000`, with an
SQLite database stored beside the executable (or in `%ProgramData%` when installed).

The product supports the full student money cycle: register a student → place them in
a trade and course year → bill them per semester from a fee structure → record
receipts → chase outstanding balances → progress or graduate them at semester end →
report on collections and audit every change.

Two interfaces are shipped:

| Surface | Location | Notes |
| --- | --- | --- |
| Server-rendered UI | `templates/` + `school/views.py` | The primary, complete interface (Bootstrap, offline assets). |
| JSON API | `school/api.py` | Session-authenticated REST-style endpoints covering every domain area. |
| Nuxt SPA | `frontend/` | Consumes the JSON API; `config/urls.py` serves `templates/spa.html` as a catch-all. |

Verified stack: Python 3.14, Django 6.1, SQLite, APScheduler 3.11, openpyxl 3.1,
ReportLab 5.1, whitenoise, django-cors-headers. Settings timezone is `Africa/Harare`.

---

## 2. Capability map

| Area | Capabilities | Primary routes |
| --- | --- | --- |
| Dashboard | Semesters progress, collection KPIs, outstanding students, today's cash, next-step prompts | `/` |
| Students | Register, search, edit, detail statement, status change, bulk spreadsheet import | `/students/…` |
| Archive | Read-only search of every student regardless of status | `/students/archive/…` |
| Reminders | Active students with incomplete contact/address details | `/reminders/` |
| Academic setup | Academic years, semesters, date validation, semester status | `/academic-years/`, `/semesters/…` |
| Trades (programs) | Program register with code, duration, category, active flag | `/programs/…` |
| Fee management | Fee structures per trade/course year/semester, bulk apply, copy forward, completion lock | `/semesters/<id>/fee-structures/…` |
| Enrollment | Automatic enrollments and charges per academic year; automatic and manual progression | Dashboard, `/semesters/`, management command |
| Payments | Receipt capture against a semester, live balance, financial records | `/payments/new/`, `/financial-records/` |
| Reports | Eight report views with filters, CSV and PDF export | `/reports/…` |
| Administration | Users and role groups, audit trail, backups, time override | `/users/`, `/audit-log/`, `/backups/`, `/time-override/` |
| API | Auth plus ~55 JSON endpoints across all domains | `/api/…` |

---

## 3. Functional capabilities

### 3.1 Dashboard

The landing page is permission-aware and builds its tiles from the "working semester"
(the current semester, otherwise the next future one).

- Current academic year, active student count, and semester position: week number,
  total weeks, days until start, and a percentage progress bar.
- Financial tiles for the working semester: billed, collected, collection rate,
  expected revenue for the academic year, today's receipt count and total, and the
  eight most recent payments.
- Outstanding panel: total owed, number of students, top five balances with relative
  bars, and a link into the full outstanding report.
- "Next steps" prompts, shown only to people who can act on them:
  - semesters that have ended while students are still actively enrolled → progress
    them, or create the missing next semester;
  - within 30 days of the academic year ending → create next-year semesters and set
    up next-year fees, linking straight to the fee grid filtered to `needs`.
- Sidebar counters for reminders and unset fee cells, cached for 45 seconds
  (`school/context_processors.py`).

Visibility rules: financial tiles require `can_view_financial_reports` or
`can_record_payments`; the outstanding panel requires `can_view_outstanding_reports`;
progression prompts require `change_student`; fee prompts require `add_feestructure`.

### 3.2 Student records

- **Registration** captures student number, names, national ID, date of birth, gender,
  guardian name/phone, student phone, address, trade, intake year and status.
  You also choose the starting semester and course year. Registration creates the
  enrollments and fee charges for every semester from that point to the end of the same
  academic year, capped at the program duration
  (`create_academic_year_enrollments`), and writes an `AuditLog` entry with action
  `REGISTER`.
- **List and search** support query by student number or name, with two lightweight
  JSON endpoints (`/students/search/`, `/students/list-search/`) used by the type-ahead
  pickers in payments and navigation.
- **Detail** is the student's full statement: current enrollment and course year, a
  year selector across every year the student belongs to, and per-semester rows showing
  charges, payments, balance, and whether the fee structure is set up at all. Rows for
  unset fees link to the exact fee grid cell when the user can add fees.
- **Status changes** (Active, Deferred, Withdrawn, Completed) always require a note and
  are written to `StudentStatusLog` plus `AuditLog`. Moving a student to `WITHDRAWN`
  deletes unpaid charges for semesters that have not yet ended and logs a
  `WITHDRAWAL` financial adjustment; receipts already captured are never touched.
- **Bulk import** accepts `.xlsx` or `.csv`. The parser scans up to ten rows for a
  header containing student-number-like and surname-like columns, then maps
  `STUDENT NO`, `SURNAME`, `NAME` and `TRADE`. You choose the intake year, starting
  semester, starting year level and status. The first pass is a preview: rows to import
  and rows to skip (missing data, duplicate student number, or a trade code that does
  not match an existing `Program.code`) are listed before anything is saved. Confirmed
  rows create students, their enrollments and their charges, and a summary is audited.
- **Archive** offers a searchable, read-only view of all students, including withdrawn
  and completed records, with full detail pages.

### 3.3 Reminders

`/reminders/` lists active students missing any of: guardian name, guardian phone,
student phone or address. The same count drives the sidebar badge and the dashboard, so
data hygiene is visible without hunting for it.

### 3.4 Academic structure

- **Academic years** have a name, start/end dates and a current flag. A database
  constraint allows exactly one current year, and a year must end after it starts.
  Academic years are seeded automatically on startup and again from the launcher
  (`seed_academic_years --back 5 --forward 10`), so a fresh install has usable years
  immediately.
- **Semesters** are two per academic year (period 1 and 2), unique per year. Validation
  rejects a semester that ends before it starts, starts before its academic year, or
  ends after it. Each semester derives a live status — `ACTIVE`, `UPCOMING` or
  `COMPLETED` — from today's date (or the frozen testing date).
- **Completed semesters are locked** for fee work: create, edit, bulk apply and copy all
  reject changes server-side, not just in the UI. Completed semesters remain valid
  sources when copying fees forward.
- `generate_semesters` is an optional utility that back-fills semesters and default fee
  items for earlier years, for demonstrations or historical load.

### 3.5 Trades (programs)

A program has a unique code and name, description, duration in years, category
(National Certificate, National Qualification, Other) and an active flag. Duration
drives everything downstream: course-year dropdowns, the fee grid's "not offered"
cells, maximum enrollment year level, and when a student is considered to have
completed the program. Inactive trades are excluded from new-fee targeting and from
fee-setup checks.

### 3.6 Fee management

Fees are modelled as a structure per **trade + course year + semester**, containing any
number of named line items with amounts. A structure counts as "set up" only when it
has at least one item — the same definition is used by the dashboard, the semester
list, the fee grid, the audit report and student detail.

- **Fee grid**: trades as rows, course years as columns, one cell per pair. Each cell
  shows the total, item count, set-up status and the number of students waiting when
  unset. Clientside filter pills switch between Everything / Needs fees / Set up.
- **Single structure form**: fee lines with a name datalist, `$` prefix, a running total
  per student, and a note. Duplicate names are rejected case-insensitively after
  trimming. A line that already has charges attached cannot be removed. Editing a
  structure creates charges for students enrolled after it was first set up, but does
  not rewrite amounts already charged.
- **Bulk apply** ("Set one fee for many") applies one named fee and amount across many
  trade/course-year combinations, limited to each trade's real duration, with a live
  preview of how many trade-years and students are affected.
- **Copy forward** copies every applicable empty cell from a chosen source semester in
  one transaction. It is idempotent, skips cells that are already set up or not
  offered, and generates charges for enrolled students.
- **Billing**: saving a fee structure generates one `StudentCharge` per fee item for
  each existing enrollment, with a uniqueness constraint per
  student/enrollment/fee item. Charges are the sole basis for "billed" figures.

### 3.7 Enrollment and progression

An `Enrollment` links a student to a program, a semester and a course year, unique per
student and semester. Validation enforces that the year level does not exceed the
program duration and that the enrollment program matches the student's program.

Progression follows the semester calendar:

| Finished semester | Next state |
| --- | --- |
| Semester 1 | Same course year, next semester |
| Semester 2 | Course year + 1 |
| Semester 2 beyond program duration | Student `COMPLETED`, old enrollment `COMPLETED`, status log written |

Three ways to run it:

1. **Background job** — APScheduler runs `progress_students_by_date` every six hours,
   plus once roughly 30 seconds after startup (`school/scheduler.py`). It is skipped
   during PyInstaller analysis and whenever `NRZ_DISABLE_SCHEDULER=1`.
2. **Command line** — `progress_students_by_date --dry-run` shows the plan without
   writing; `--date YYYY-MM-DD` evaluates against an arbitrary date.
3. **Bulk action** — a POST endpoint reachable from the semester list progresses all
   active students of one ended semester into the next chronological semester in a
   single transaction, reporting how many advanced and how many graduated.

Progression warns about students carrying outstanding balances and never blocks on
them. New enrollments for the target academic year are created together with their
charges, so a progressed student is immediately billable.

### 3.8 Payments and receipts

- Payment capture starts with a student search, then a semester choice limited to
  enrollments that have charges, payments or a fee structure. The page shows charged,
  paid and balance for the selected semester plus a per-semester summary table.
- Fields captured: receipt number (unique), amount, payment date, reference and notes.
  Receipt numbers are entered by the operator; the model enforces global uniqueness.
- Payments are validated server-side (student active, positive amount, active
  enrollment, unique receipt) and written inside a transaction with an `AuditLog`
  entry of action `PAYMENT` and category `FINANCIAL`.
- Financial records (`/financial-records/`) aggregate every academic year and semester
  into billed, collected, outstanding and collection-rate figures with grand totals,
  suitable for printing.
- Student detail exposes full payment history per semester, so a receipt can always be
  traced back to the enrollment it settled.

### 3.9 Reports

Eight reports are registered in `school/reporting/registry.py`. Each declares its
permission, group, PDF orientation and filename stem; only permitted reports appear on
the index and in navigation.

| Report | Question it answers | Permission |
| --- | --- | --- |
| Financial records | How did each semester do? | `can_view_financial_reports` |
| Enrollment summary | Who is enrolled? | `view_student` |
| Outstanding balances | Who still owes fees? | `can_view_outstanding_reports` |
| Fee setup check | Which trade-years have no fees? | `view_feestructure` |
| Payment methods | How are people paying? | `can_view_financial_reports` |
| Revenue by trade | Which trades are paying? | `can_view_financial_reports` |
| Daily collections | What was collected, by receipt? | `can_view_financial_reports` |
| Status history | What changed, when and why? | `view_studentstatuslog` |

Shared reporting behaviour:

- Filters: semester, academic year, trade, course year, intake year, status, single date
  or date range, and student search — whichever the report needs.
- Exports: the same view renders as HTML, CSV (`?format=csv`) or PDF (`?format=pdf`).
  PDF uses ReportLab with the institution name in the header; the button is hidden if
  ReportLab is missing. CSV output neutralises spreadsheet formula injection.
- Every export is audited (`OTHER`, with report slug, format, filters and row count).
- Server-side pagination: 25 rows per page, 50 for status history.
- Financial definitions are fixed and documented in the UI: **Billed** = charges in the
  semester, **Collected** = payments in the semester, **Owed** = sum of positive
  student balances, **Credit** = sum of overpayments, **Net** = Billed − Collected.
  Owed and Credit are intentionally reported separately so credits never hide debt.

### 3.10 Administration

- **Users** (`/users/`): paginated list of accounts with their role groups; superusers
  create accounts with a temporary password, an optional role group and optional staff
  (Django admin) access.
- **Role groups** are seeded by `setup_roles` on every launcher start:

  | Group | Granted permissions |
  | --- | --- |
  | Registrar | `add_student`, `view_student` |
  | Finance | `can_view_financial_reports`, `can_view_outstanding_reports`, `can_record_payments`, `view_student`, `view_auditlog` |
  | Academic | program, academic year, semester and fee-structure view/add/change |

- **Audit trail** (`/audit-log/`): reverse-chronological log of registrations, bulk
  imports, status changes, withdrawal adjustments, payments and report exports, each
  with the acting user, affected student where relevant, a summary and a JSON detail
  blob. Filterable and paginated.
- **Django admin** remains available at `/admin/` for staff.
- **Backups** (`/backups/`, superuser only):
  - create a timestamped copy of the live SQLite file using SQLite's online backup API,
    so a write in progress cannot produce a torn copy;
  - every copy is accepted only after passing `PRAGMA integrity_check` and containing
    the application's migration table;
  - download any backup;
  - restore a backup: the file is verified first, a `safety_before_restore_*` copy is
    taken, Django's connections are closed and the database is swapped atomically;
  - upload a `.sqlite3`/`.db` file, with extension validation, integrity verification,
    filename sanitising and duplicate-name handling;
  - configure an external backup path, enable/disable automatic backups, set retention
    in days, and enable strict mode so the dashboard warns when the backup medium is
    missing or unwritable;
  - `backup_auto` performs the daily verified copy and prunes files older than the
    retention window.
- **Time override** (`/time-override/`, superuser only, enabled with
  `NRZ_ENABLE_TIME_OVERRIDE=1` and off by default): freeze "now" to any datetime so
  semester status, dashboard prompts, progression dates and reports can be tested out of
  season, then clear it to return to real time. All date logic flows through
  `school/utils/time_utils.py`, so one setting moves every screen consistently.

### 3.11 JSON API

`school/api.py` exposes ~55 session-authenticated endpoints, grouped below. Successful
reads return JSON; validation failures return `{"errors": {...}}` with a 4xx status.

| Group | Representative endpoints |
| --- | --- |
| Auth | `GET /api/auth/check/`, `POST /api/auth/login/`, `POST /api/auth/logout/` |
| Dashboard | `GET /api/dashboard/` |
| Trades | `GET/POST /api/programs/…`, `GET /api/programs/<id>/`, `POST /api/programs/<id>/edit/` |
| Academic years | `GET/POST /api/academic-years/…` |
| Semesters | `GET/POST /api/semesters/…` |
| Fees | `GET/POST /api/semesters/<id>/fee-structures/…`, `POST …/bulk/` |
| Students | `GET/POST /api/students/…`, `POST /api/students/<id>/status/`, `GET /api/archive/students/…` |
| Payments | `GET/POST /api/payments/…`, `GET /api/payments/<id>/receipt/`, `GET /api/financial-records/` |
| Reports | `GET /api/reports/…` for all eight reports, `GET /api/reminders/` |
| Administration | `GET/POST /api/users/…`, `GET /api/audit-logs/`, `/api/backups/…`, `/api/time-override/` |

API permissions mirror the UI: `view_student` for people data, `can_view_financial_reports`
for money data, `can_record_payments` for payment creation, `view_feestructure` for fee
work, and superuser-only for user, backup and time-override endpoints. Student listing
supports `q`, `status`, `program`, `year_level` and `page`; audit listing supports
action, user, student and date filters. CORS is limited to the Nuxt dev origins
(`localhost:3000`, `127.0.0.1:3000`).

---

## 4. Access control

- Every request is authenticated by `school.middleware.LoginRequiredMiddleware`, which
  redirects anonymous users to the login page; login, logout, static files, Django admin
  and the three auth API endpoints are exempt.
- Sessions expire after two hours of inactivity and the idle timer refreshes on every
  request (`SESSION_COOKIE_AGE = 7200`, `SESSION_SAVE_EVERY_REQUEST = True`).
- Navigation is generated from a permission table (`school/templatetags/school_tags.py`),
  so users only see links they can actually open. Groups render as Dashboard, People,
  Money, Academics and System.
- Views are protected by Django decorators: `login_required`, `permission_required`
  with `raise_exception=True`, and `user_passes_test` for superuser-only screens.
- Custom permissions live on `Student`: `can_view_financial_reports`,
  `can_view_outstanding_reports`, `can_record_payments`.

---

## 5. Business rules enforced by the system

| Rule | Where |
| --- | --- |
| Academic year end must be after start; only one current year | `AcademicYear` |
| Semester must sit inside its academic year; unique period per year | `Semester` |
| Semester status (ACTIVE/UPCOMING/COMPLETED) derived from the effective today | `Semester.status` |
| Fee work is blocked on completed semesters | fee views, server-side |
| Unique fee structure per trade + course year + semester | `FeeStructure` |
| Fee item names unique per structure (case-insensitive, trimmed) | `FeeStructureItemFormSet` |
| Year level cannot exceed program duration | `FeeStructure`, `Enrollment` |
| Enrollment program must match the student's program; one enrollment per semester | `Enrollment` |
| One charge per student/enrollment/fee item | `StudentCharge` |
| Receipt numbers are globally unique | `Payment` |
| Withdrawal clears unpaid charges for semesters not yet ended | `cancel_unpaid_future_charges` |
| Fee cells beyond a trade's duration are "not offered" | fee grid, bulk, copy |
| Credits never reduce reported debt (owed vs credit reported separately) | `reporting/definitions.py` |
| CSV exports neutralise formula injection | `reporting/renderers.py` |
| Backups are consistent SQLite copies and must pass `PRAGMA integrity_check` | `utils/backups.py` |
| Bulk progression requires `change_student` | `bulk_progress_students` |

---

## 6. Data model at a glance

| Model | Purpose | Key relationships |
| --- | --- | --- |
| `TimeOverride` | Singleton frozen datetime for testing | — |
| `AcademicYear` | Named year with date range and current flag | has many `Semester`, `Student` (intake) |
| `Semester` | Period 1 or 2 within a year | belongs to `AcademicYear` |
| `Program` | Trade/qualification with duration and category | has many `Student`, `FeeStructure` |
| `FeeStructure` | What a trade/course year owes in a semester | belongs to `Program` + `Semester` |
| `FeeStructureItem` | Named fee line and amount | belongs to `FeeStructure` |
| `Student` | Person record with status and contact details | belongs to `Program` + `AcademicYear` |
| `Enrollment` | Student's registration in a semester and course year | student + program + semester |
| `StudentCharge` | Billed amount per fee item for an enrollment | enrollment + fee item |
| `Payment` | Receipt against a student and semester | student + semester |
| `StudentStatusLog` | Dated status changes with notes | student |
| `AuditLog` | Who did what, with JSON details and category | user, optional student |
| `BackupConfig` | Singleton backup path, auto flag, retention, strict mode | — |

Money is `Decimal` with two places throughout; balances are always computed as charges
minus payments for the semester in question.

---

## 7. Automation and startup behaviour

| Trigger | Behaviour |
| --- | --- |
| Launcher start | Verify the data directory is writable, run migrations, seed academic years, seed role groups, start Django, open the browser |
| App ready | Seed the current academic year range (guarded by table existence) and start APScheduler |
| APScheduler | Progression check ~30 seconds after start, then every six hours |
| First request | Navigation summary (reminder and fee counts) cached for 45 seconds |
| Dashboard visit | Recommends progression, missing semesters, and next-year fee setup based on dates and permissions |
| Packaged start | Migrations run automatically, so a fresh install is usable without manual steps |

---

## 8. Configuration reference

| Setting / variable | Default | Effect |
| --- | --- | --- |
| `NRZ_DATA_DIR` | `data/` beside the app | Location of `school.sqlite3` and `backups/` |
| `NRZ_DISABLE_SCHEDULER` | unset | Skips APScheduler (used during packaging and tests) |
| `DJANGO_DEBUG` | `0` | Enables Django debug pages; on only when set to `1` |
| `DJANGO_SECRET_KEY` | generated into `<data>/.secret_key` | Signing key; set explicitly to share one key across data directories |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated hosts Django will serve |
| `NRZ_ENABLE_TIME_OVERRIDE` | `0` | Enables the superuser time-freeze screen and its date logic |
| `BACKUP_DIR` | `<data>/backups` | Default backup destination when none is configured |
| `SESSION_COOKIE_AGE` | 7200 s | Inactivity logout |
| `TIME_ZONE` | `Africa/Harare` | All date arithmetic and display |
| `CORS_ALLOWED_ORIGINS` | `:3000` origins | Only the Nuxt dev server may call the API cross-origin |
| `NRZ_DATA_DIR` (installer) | `%ProgramData%\NRZ Student Management` | Machine-wide writable data location |

---

## 9. Deployment and packaging capabilities

- `launcher.py` is the single entry point: no arguments starts the server; any arguments
  are forwarded to Django management commands (for example
  `NRZ Student Management.exe createsuperuser`), with migrations run first.
- `nrz_student_management.spec` freezes the app with PyInstaller, bundling configs,
  templates, static files, Django, APScheduler, openpyxl and ReportLab.
- `NRZ_Student_Management.iss` builds an Inno Setup installer that installs the app to
  `Program Files`, creates writable data folders in `ProgramData`, sets `NRZ_DATA_DIR`,
  and adds desktop and Start Menu shortcuts.
- Application code and user data are deliberately separated so updates never risk the
  database.
- `.github/workflows/ci.yml` installs `requirements.txt` and runs `manage.py check`,
  a missing-migrations check and the full `school` test suite on every push and pull
  request.

---

## 10. Current limits and non-capabilities

Useful to know before promising a feature:

- **Scope**: no attendance, timetable, grades/results, transcripts, library, hostel or
  staff/payroll modules. The academic record stops at enrollment and progression.
- **Payments**: the server-rendered payment screen does not expose the payment-method
  field, so payments captured there are recorded as `CASH`. The model and API support
  Cash, Bank, EcoCash and Other, and the payment-methods report groups by that field.
- **No reversal workflow**: there is no void, edit or refund for a payment; corrections
  require a new entry or direct data work, and receipts are immutable once saved.
- **No outbound communication**: no email, SMS or statement messaging. Reminders are
  in-app only.
- **No online payments or invoicing**: receipts are internal records; there is no
  gateway, card processing or PDF invoice per student.
- **Audit coverage is partial**: student, status, payment and export events are logged,
  but fee-structure changes, backups and user edits are not written to `AuditLog`
  (backups and user creation are superuser-only and visible in their own screens).
- **Reports are on-demand only**: no scheduling, emailing or saved report
  subscriptions; CSV and PDF are generated per request.
- **Single-database, single-machine**: SQLite serves the local browser session. It is
  not built for many concurrent editors over a network share.
- **Transport is plain HTTP on loopback**: there is no TLS, and `ALLOWED_HOSTS` defaults
  to local addresses. Put a reverse proxy with HTTPS in front before serving other
  machines, and set `DJANGO_ALLOWED_HOSTS` accordingly.
- **Local-only backups**: verified copies are written to the configured path; off-site
  replication and encryption are not included. Restore replaces the live database in
  place, so take a copy off the machine before a major upgrade.

---

## 11. Where things live

| Path | Contents |
| --- | --- |
| `config/settings.py` | Installed apps, middleware, database path, sessions, CORS, timezone |
| `config/paths.py` | Portable path resolution for development and frozen builds |
| `school/models.py` | Schema, validation, and financial/report helper queries |
| `school/views.py` | All server-rendered screens, fee grid logic, progression, backups |
| `school/api.py` | JSON endpoints for the Nuxt frontend |
| `school/forms.py` | Model forms, fee formset validation, bulk fee and import forms |
| `school/reporting/` | Report registry, builders, CSV/PDF renderers, report view |
| `school/utils/` | Time override helpers, audit logging, spreadsheet import parser, verified backup/restore |
| `school/management/commands/` | Seed years, seed students, roles, progression, semesters, auto backup |
| `school/scheduler.py` | APScheduler wiring |
| `templates/` | Base layout, sidebar, all screens and reports |
| `frontend/` | Nuxt SPA consuming the JSON API |
| `docs/` | This reference plus migration, changelog and UX overhaul records |

---

## Summary

NRZ Student Management covers the registrar-and-finance workflow end to end for a single campus:
structured academic setup, per-semester billing from reusable fee structures, receipt
capture with live balances, automatic semester progression, eight operational reports
with CSV/PDF exports, role-based access, an audit trail, and a backup/restore path that
suits a non-technical operator. It is a local Windows application by design, with a JSON
API alongside the server-rendered screens for a modern frontend and further integrations.
