# Fee Management UX Overhaul — Report

Date: 2026-10-27 · Django server-rendered app · no model or migration changes.

## What changed, per screen

**Semesters** (`semester_list.html`)
One bordered row per semester with a status dot and word, dates as `12 Jan 2027`, a fees progress line (`9 of 10 set up`) with a thin bar, and one primary action per row. Incomplete rows get a filled **Set up fees** linking to `?filter=needs`; complete rows get outlined **Review fees**. **Edit dates** is a quiet secondary. Completed rows use **View fees** and a muted row background. Empty state points at **New semester**. Progress is batched for all rows, so the list does not query per semester.

**New / edit semester** (`semester_form.html`)
Short two-card form with numbered badges. Card 2 exists only on create: copy fees from a previous semester (default when a source exists) or start empty. After create it redirects to the Fees page with a banner. Date inputs now use the same flatpickr `YYYY-MM-DD` field as Register Student; the broken placeholder/`id_name` script is gone.

**Fees grid** (`fee_structure_list.html`, `fee_structure_copy.html`)
Title `FEES: 2027 · SEMESTER 1`, Back button, progress strip with bar and waiting counts, then **Copy from previous** (filled when nothing is set up) and **Set one fee for many**. The grid lists trades as rows and course years as columns, with no pagination. Set-up cells show total, fee count and status; needs cells show `+ Set up fees` plus waiting students; years beyond a trade’s duration read `Not offered`. Pills filter Everything / Needs fees / Set up client-side while keeping grid alignment, and update the URL. Copy has its own preview page: source picker, “will be copied / already set up / not offered” per row, and a summary bar. Copy is idempotent, only fills empty applicable cells, skips inactive trades and over-duration years, and charges enrolled students in one transaction.

**Single fee form** (`fee_structure_form.html`)
Opening a cell locks the trade and course year as text; the legacy URL keeps Trade and Course year selects limited to the trade’s duration. Shows the enrolment impact (“5 students are enrolled here”), fee lines with a name datalist, `$` prefix, right-aligned amount, a note hidden behind `+ Add note`, a running **Total per student**, and `Start from…` to prefill from an existing set. The first line of a new structure starts as **Tuition**; added lines stay empty. Charged lines cannot be removed and say so. The sticky bar reads back the impact and total, with Cancel, Save, Save and set up next (only when needs remain), and a Ctrl+Enter hint. Invalid input keeps the bound trade, lines and values.

**Set one fee for many** (`bulk_fee_form.html`)
Three numbered cards: trades with Select all/None, course-year chips limited to selected trades (others disabled, All years/Clear), and the fee name/amount/note. A live sentence previews added/changed/unchanged trade-years and students. The button reads `Apply to N trade-years`; the result message reports only non-zero outcomes.

**Completed semesters**
Server-side rejection on create, edit, bulk and copy; the grid and edit page render read-only with “This semester is completed. Fees are locked.” Completed semesters remain valid copy sources.

**Links**
Dashboard fee nudge and year-end alert point to `?filter=needs` and say **Set up fees**. Student detail and statement “fees not set” rows link to the exact grid cell when the user can add fees. Sidebar label is now **Fees**.

Screenshots: `docs/fee-overhaul/01`–`10`.

## Acceptance checks

| Test | Result | Clicks / notes |
| --- | --- | --- |
| 1. Same fees as last semester | Passed live: created 2028 S1 from 2027 S2, 5 sets copied, banner shown, no line re-entry | 6 form interactions + Create; semester then deleted after the test |
| 2. One fee everywhere | Passed live: Exam $25 to DPF year 1; progress moved 5→6, message “1 new” | 3 selections + 2 fields + Apply; test fee removed afterwards |
| 3. List → edit one trade/year | Passed: 2 clicks (Set up fees → cell), trade/year already locked | locked context verified |
| 4. At a glance | Passed: progress bar, needs/waiting counts, pills, per-cell status | — |
| 5. Mistakes forgiven | Passed: cleared amount kept Tuition/trade and showed inline “This field is required.” | no structure created |

Timing was not stopwatch-recorded; automated interaction timings are not representative of a person. Click counts are exact. Verified at 1440, 1280 and 1024 px; the grid scrolls inside its container.

## Defect status (brief section 4)

1. Empty-select JS wiping the trade — fixed; locked context uses hidden fields.
2. Invalid input rebuilt as blank — fixed; bound form/formset and errors preserved.
3. Duplicate trade+year 500 — fixed: redirects to edit; `FeeStructure.clean()` guards `year_level=None`.
4. Half-saved structure — fixed: form and formset validated independently.
5. Charged line removal 500 — fixed: blocked at formset validation and remove disabled with explanation.
6. Edit never created charges — fixed: charges are created after edit.
7. Existing charge amounts not updated — kept; fee-line help and message state that earlier amounts are kept.
8. Completed lock only in UI — fixed server-side on grid actions, create, edit, bulk and copy.
9. Two definitions of “set up” — one definition (structure with ≥1 item) in `fee_progress`, `unconfigured_fee_structures`, dashboard and student detail.
10. Every added row autofilled Tuition — fixed: only the first line is prefilled.
11. Fragile row cloning — replaced with `formset.empty_form` + `__prefix__` reindexing, prefix still `items`.
12. Decorator duplication on bulk — removed.
13. Wrong icons on semester list — removed.
14. Date style/placeholder JS mismatch — fixed; now matches Register Student.
15. Bulk hardcoded 1–6 years and program codes — fixed; years come from selected trade durations, labels use trade names.
16. Dead templates — confirmed unreferenced and deleted (`fee_setup.html`, `semester_create_with_fees.html`).
17. Duplicate fee names — kept and extended to case-insensitive, trimmed comparison.

## Tests

`python manage.py test school` → **20 tests, OK**. New `school/test_fees.py` covers copy idempotence/overwrite/duration/charges, bulk invalid years and duplicate lines, edit creating missing charges, completed rejection on every fee view, permission and login gating, set-up definition, query budget, invalid-form preservation, duplicate redirect, and the copy preview/POST. The query test asserts the grid cost does not grow when going from 2 to 10 trades.

## Report-only items (sections 8 and 11)

- Changing a fee amount still does not update charges already recorded. The UI now says so on charged lines and in the save message; changing it would be a financial migration decision.
- Charged line removal is blocked rather than cascading deletes. Recommendation: keep this, and edit charges through an explicit adjustment flow later.
- Completed locking is now enforced in views. Recommendation: add a shared guard/constraint so future fee views cannot forget it.
- Old vocabulary remains outside the fee pages: `reports/fee_audit.html` (“Configure”), `student_register.html` and `student_import.html` (“year level”), the Programs nav/page, and some dashboard cards still format semesters with “2027 - Semester 1” via `Semester.__str__` or direct text.
- `bulk_progress_students` still has no permission decorator (login is covered by middleware).
- Progression still only charges existing structures.
- Context processors still run queries on every request.
- Before screenshots were not captured; this overhaul was completed in place, so only the after state is shown.
- A mistyped URL falls through to the Nuxt SPA shell, which 500s because `spa.html` uses `{% static %}` without loading it. Ignored per instruction.
