# Dashboard and Sidebar Overhaul — Report

Date: 2026-10-28 · Django templates / Bootstrap / vanilla JS · runserver only.

## What changed

- **Foundation:** `.ui` tokens/components in `static/css/ui.css`, reusing the existing local Archivo Navbar declaration. Buttons, lamps, chips and figures match the Student detail reference in measured dimensions, weights, padding and numeric settings. Dashboard-specific density lives in `dashboard.css`. The generated 2,188-byte light contour SVG derives paths/palette from `nav-waves.svg`; it is decorative, static and hidden in print.
- **Sidebar:** People / Money / Academics / System, one SVG sprite, exact permission gates and route ownership, automatic opening of the current section, per-user guarded localStorage, a persistent 64px rail with tooltips, and Bootstrap offcanvas at 768px and below. System starts closed unless active. Empty groups disappear; no group exceeds five links.
- **Backend:** dashboard and cached navigation share `get_working_semester()` (current, otherwise upcoming). Navigation retains its 45-second cache. Financial computation is permission-gated; progression uses grouped enrollment counts plus one ordered semester list; outstanding students are evaluated once; receipts/trades and course years avoid per-row queries. Credits never offset another student's positive balance.
- **Dashboard:** compact semester rail/header, four conditional figures, eight recent receipts, five highest balances with Open/Pay shortcuts, and one conditional Next steps card. Progression uses a CSRF-protected Bootstrap modal. No current-semester fee nudge or generic Register/Record duplication. Missing setup has explanatory empty states. Ordinary flash messages sit below the dashboard rather than creating extra banners above the figures.

## Acceptance checks

| Admin test | Result / evidence |
| --- | --- |
| Four figures without scrolling at 1280×720 | Pass: all four end at **378px** in the standard state; **434px** with the blocking banner and no semester. |
| At most one banner; setup in Next steps | Pass: strict backup takes priority over missing academic year. Progression and year-end readiness remain in Next steps; working-semester fee gaps remain in the bell. |
| No duplicated navbar/bell actions | Pass: no generic Register student, Record payment, fee-gap or missing-detail prompt inside the dashboard. Student-specific Pay shortcuts remain. |
| One click from either list | Pass with a non-superuser bursar: Open reaches the correct record; Pay opens a form with the correct student already selected. Deferred Pay is disabled, focusable and carries a reason. Modal Cancel/focus return and successful progression POST also pass. |
| Exact permissions | Pass: 16 financial/student permission combinations, sidebar gates/active routes, and no financial-helper execution for unauthorized readers. Add-only fee users get a direct-create bell link, not a forbidden grid. |
| Same product language | Pass: side-by-side component comparison, 44px reference buttons, tabular Archivo figures, navy/white surfaces, lamps with words and no Bootstrap colour badges. |

### Dashboard permission mapping and tested users

| Surface/action | Required permission |
| --- | --- |
| Active student count | Authenticated; link requires `view_student` |
| Billed, Collected, Recent payments | `can_view_financial_reports` **or** `can_record_payments` |
| Financial records / daily-collection links | `can_view_financial_reports` |
| Still owed / Highest balances | `can_view_outstanding_reports` |
| Student record links / Pay links | `view_student` / `can_record_payments`; Pay also requires active student |
| Progress now | `change_student` |
| Missing/next-year semesters / next-year fees | `add_semester` / `add_feestructure` |

**Superuser:** four figures, both lists, all permitted navigation and applicable setup tasks. **Payments-only** (`can_record_payments`): student count, Billed, Collected and receipts/Pay; no debt widget, student-record or restricted report links. **Read-only** (`view_student`, `view_feestructure`): student count, People and permitted Fees/Fee audit navigation; no dollar amounts. An additional bursar with the three money permissions plus `view_student` verified all one-click workflows.

## Every old sidebar destination

Route names identify the original Django `href` targets; paths and views are preserved.

| Old item / href target | New location | Access |
| --- | --- | --- |
| Dashboard · `dashboard` | Dashboard | Login |
| Reminders · `reminders` | Navbar attention menu; page retained | Existing bell visibility |
| Students · `student_list` | People → Students | `view_student` |
| Archive · `archive_list` | People → Archive | `view_student` |
| Payments · `payment_create` | Navbar Record payment; student Pay shortcuts | `can_record_payments` |
| Academic years · `academic_year_list` | Academics → Academic years | `view_academicyear` |
| Semesters · `semester_list` | Academics → Semesters | `view_semester` |
| Programs · `program_list` | Academics → Trades; list heading retitled | `view_program` |
| Fees · `fee_structure_list(semester)` | Academics → Fees, working semester | `view_feestructure` |
| Fees fallback · `semester_list` | Same fallback; hidden if inaccessible | `view_semester` |
| All Reports · `#reportsSubmenu` | Removed presentation-only toggle; links redistributed | — |
| Index · `reports_index` | Standalone Reports index below groups | Login |
| Financial records · `financial_records` | Money → Financial records | `can_view_financial_reports` |
| Enrollment · `enrollment_report` | People → Enrollment report | `view_student` |
| Outstanding · `outstanding_report` | Money → Outstanding | `can_view_outstanding_reports` |
| Fee audit · `fee_audit_report` | Academics → Fee audit | `view_feestructure` |
| Payment methods · `payment_methods_report` | Money → Payment methods | `can_view_financial_reports` |
| Revenue · `program_revenue_report` | Money → Revenue | `can_view_financial_reports` |
| Daily collections · `daily_collections_report` | Money → Daily collections | `can_view_financial_reports` |
| Status history · `status_history_report` | People → Status history | `view_studentstatuslog` |
| Administration · `/admin/` | System → Administration; user menu retained | Staff |
| Backup & Restore · `backup_index` | System → Backups | Superuser |
| Backup Settings · `backup_settings` | Backups header; existing return link retained | Superuser |
| Audit Trail · `audit_log_list` | System → Audit trail | `view_auditlog` |
| Users · `user_list` | System → Users | Superuser |
| Add User · `user_create` | Existing Add user button on Users | Superuser |
| Time Override · `time_override` | System → Time override | Superuser + `ENABLE_TIME_OVERRIDE` |

## Decisions and verification

- `--side-w: 232px` replaces `16.6667%`; desktop rail is 64px and mobile main offset is zero. The old percentage dependencies were confined to `base.html`; application-template/style searches now find none. Register Student's action bar is sticky, not percentage-positioned, and was left unchanged.
- Global body background remains `#f8f9fa`. Small secondary/sidebar text uses `--ink-2` rather than low-contrast `--grey`. Computed dashboard/sidebar text contrast: **5.04:1–14.50:1**. The header note has a nearly opaque wash backing over the decorative contours.
- All four `base.html` blocks are preserved. Student detail and Register Student match their pre-task SHA-256 hashes. Three token copies intentionally remain: their two inline sets and `.ui`; migrate the reference pages to `.ui` in a separate follow-up.
- `BSOFT_DISABLE_SCHEDULER=1 python manage.py test school` → **74 tests, OK**, including **43 dashboard/sidebar tests**. Coverage includes permissions, relocation, active ownership/404 safety, modal CSRF, clock boundaries, positive balances, empty states, banner priority, flash-message placement and query stability for 2→10 ended semesters and 5→50 payments. JavaScript syntax, template/system checks and scoped `git diff --check` pass.
- Live Edge/runserver QA used a separate SQLite copy with scheduling disabled; no real enrollments/payments were changed. Required 1440/1280/1024/768 matrix passed; extra 390px checks caught and fixed screen-reader text escaping the table scroller. Also verified rail/group persistence, tooltips, 49 visible focus targets, drawer focus trap/Escape/return focus, reduced motion, print, navbar search/attention stacking, Fees, Student list/detail and Register Student. No browser runtime/network errors occurred in successful checks.
- **Screenshots:** `docs/dashboard-overhaul/before-{superuser,payments,reader}-{1440,1280,1024,768}.png` and matching `after-*` files; supplementary modal, deferred Pay, bursar, rail/drawer, year-end, empty/backup states, component comparison, navbar and reference-page captures. The standard matrix uses the same data before/after; extra scenario captures use isolated QA fixtures.
- **Logical diffs:** `docs/dashboard-overhaul/phase-1-foundation.patch` through `phase-5-tests-report.patch` compare against the pre-task source snapshot, excluding unrelated pre-existing edits. No commits: the working tree contains overlapping uncommitted earlier work, and the view/template phases are coupled. Screenshot binaries are delivered separately.

## Not changed / follow-up

- **Security follow-up:** `bulk_progress_students` still lacks a permission decorator, as explicitly scoped to report-only. Hiding Progress now with `change_student` is not endpoint authorization; add matching server-side enforcement separately.
- Reminders redesign, existing Flatpickr console logging and older Bootstrap-styled pages remain out of scope. Suggested visual follow-up order: Semesters/academic setup → financial reports → Reminders/system pages.
- Optional collected-by-trade strip and login artwork were not added; the dashboard stays focused on the required figures/lists. No artwork was added elsewhere.
- No API changes, models/migrations, new dependencies, remote assets or chart libraries.
