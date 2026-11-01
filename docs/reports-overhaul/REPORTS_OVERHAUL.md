# Reports Overhaul

## Status
Shared report infrastructure, all eight existing web report routes, CSV and PDF export paths are implemented. The acceptance matrix below is **partially verified**; full manual/visual and role-matrix QA remains outstanding. Baseline artifacts came from the isolated QA copy under `docs/reports-overhaul/baseline/`; no live database was changed.

## Changed by area
- **Hub/design:** permission-filtered question-first groups and quick-answer links; shared `reports.css` uses dashboard UI tokens, loads through the existing `extra_head` block, and print rules unclip `.main-content`. The dashboard wave SVG is reused on the hub only; it is not embedded in PDFs.
- **Shared reports:** registry, canonical billing definitions, result builders, shared template, CSV/PDF renderers, export audit entries and query parameter preservation. Existing report URL names remain. Reports render with the full content width; old report-specific templates remain on disk but are no longer selected by the HTML views.
- **Outstanding:** Course year filter, optional guardian contacts (requires `view_student`, off by default), aggregate-derived balance detail, PDF/CSV and printable page; legacy CSV schema retained.
- **Daily collections:** defaults to today, applies paired date ranges, emits one aggregate count/amount, includes method cash-up rows and prepared/checked lines in its landscape PDF.
- **Fee setup check:** rows now include students waiting and a direct link to the exact Fees grid cell for that trade/course year.
- **Data correctness/performance:** transaction count now uses `Count`; revenue balances are grouped from student charge/payment aggregates rather than per-trade queries; financial records exports and reconciles Owed/Credit/Net from grouped charge/payment rows. Revenue-by-trade legacy CSV columns remain unchanged, so its new Credit and Net values are currently HTML/PDF-only; this is an unresolved conflict between CSV schema compatibility and the new reconciliation fields. No model helper signature changed.

## Acceptance checks
| Requirement | Status / evidence |
|---|---|
| Outstanding list incl. contacts in ≤3 clicks, PDF in one more | Implemented; no manual click-path observation recorded. Contacts require `view_student`, default off. |
| Daily cash-up defaults to today, methods and prepared/checked PDF | Focused automated test verifies date default, PDF response and audit entry; manual print/signoff review remains. |
| Figures match HTML/CSV/PDF and reconcile | Financial records, Outstanding and Revenue by trade credit fixture values are verified in CSV; all eight PDF endpoints return valid PDF responses. Revenue by trade CSV intentionally retains the old schema and therefore omits its new Credit/Net fields: the cross-format acceptance item is not fully met. PDF/table content was not visually compared page-by-page. |
| A4/grayscale/repeated headings/page numbers/filters/byline | Implemented in PDF renderer; not visually inspected page-by-page or in grayscale. PDF responses are smoke-tested as valid `%PDF-` outputs. |
| No permission dead ends | Route decorators retained; hub and report menus filter via registry; reader denial and report page/export role checks are automated in part. Full three-user × all-form matrix remains. |
| Trade/Course year vocabulary and dashboard design | New shared template and CSS follow this; CSV legacy headers intentionally retained. |
| Legacy routes/query strings | Named routes retained and old `program`, `semester`, `date_from`, `date_to`, `page`, and `format=csv` read; route-contract coverage is incomplete. |
| Responsive widths, 390px, focus, contrast, long print | Not fully verified. Baseline files include hub screenshots at 1440/1280/1024/768 and one Outstanding 390px image; no after screenshots or computed contrast/focus/long-print review is recorded. |
| Query growth, export fallback, full suite | Full school suite passes (83 tests); focused report suite passes (9 tests). Flat query-growth and missing-ReportLab fallback tests remain unimplemented. |

## Permission map
| Report | Permission | Superuser | Finance bursar | Read-only student viewer |
|---|---|---|---|---|
| Financial records | `can_view_financial_reports` | View/export | View/export | Hidden; direct access denied |
| Daily collections | `can_view_financial_reports` | View/export | View/export | Hidden; direct access denied |
| Payment methods | `can_view_financial_reports` | View/export | View/export | Hidden; direct access denied |
| Revenue by trade | `can_view_financial_reports` | View/export | View/export | Hidden; direct access denied |
| Outstanding balances | `can_view_outstanding_reports` | View/export | View/export | Hidden; direct access denied |
| Enrollment summary | `view_student` | View/export | View/export | View/export |
| Fee setup check | `view_feestructure` | View/export | View/export | Hidden; direct access denied |
| Status history | `view_studentstatuslog` | View/export | View/export | Hidden; direct access denied |

*Bursar test user has the five report permissions plus `view_student`; a production bursar’s exact grant set remains administrator-defined. `Open` and `Pay` actions are separately gated by `view_student` and `can_record_payments`.*

## Route and parameter contract
| Route / parameter | Before | After |
|---|---|---|
| `reports_index` | Login-only list of all eight | Same named route; reports shown only when registry permission permits |
| Eight HTML report routes | Individual templates/views | Same route names; shared result template; decorators unchanged |
| `?format=csv` | Inconsistent CSVs; Financial Records had none | Shared UTF-8 BOM CSV and audited exports; legacy headers/order retained except corrected count |
| `?format=pdf` | Not present | A4 PDF attachment; daily/reports orientation from registry |
| `semester`, `program`, `date_from`, `date_to`, `page` | Existing partial filters | Existing keys still parsed; `course_year`, `show_contact`, `date`, intake/status/year filters added |
| CSV schema changes | Existing report-specific headers | Proposed header renames not applied (see below) |

## Defects (section 5)
| Defect | Status |
|---|---|
| Report CSS/print CSS not loaded; fixed scrolling content clips | Fixed by base `extra_css` block and scoped print CSS |
| Transactions showed money | Fixed to actual payment count |
| Outstanding definitions differ from net | Canonical definitions and Owed/Credit/Net columns added; trade attribution caveat below |
| Hub/nav showed forbidden reports | Hub/menu registry permission filter added |
| Duplicate in-page navigation | Removed from migrated pages via shared template; old templates still remain |
| Daily date range and repeated count | Pair-based parsing; single aggregate count/amount; applied range label |
| Status history loaded every student | Shared page has typeahead input; suggestions use existing search endpoint; needs interaction QA |
| Query loops | Program revenue grouped; financial records uses grouped rows; query-growth tests still needed |
| CSV BOM/injection/filenames/audit | Implemented BOM, text formula escaping, consistent names and `OTHER` audit logging |
| Template percentage logic | New report template renders builder percentages |
| Duplicated report context/plumbing | Shared renderer/builders used by eight report views |
| Vocabulary/status/table/empty patterns | Updated shared template; some legacy CSV headers are preserved |
| Guardian contact data unused | Optional Outstanding columns, permission-checked, off by default |
| Fee audit link target | Fixed: each missing trade/course-year row links to its matching Fees grid cell; active enrolled waiting count is included |

## Definitions and known attribution caveat
- Billed = charges; Collected = payments; Owed = sum of positive student balances; Credit = student overpayments; Net outstanding = Billed − Collected = Owed − Credit.
- **Revenue by trade** preserves existing billed/collected attribution: charges go to fee-structure trade; payments go to the student’s current trade. Owed and Credit are calculated from student balances grouped by current trade. If a student changes trade, billed/collected can differ from those balance groupings. No representative changed-trade sample was available in QA, so this remains an explicit limitation rather than silently reassigning the historic columns. The legacy CSV schema also omits the new Credit/Net fields; resolve this compatibility-vs-reconciliation decision before claiming full cross-format parity.
- Outstanding includes only positive student balances; credits are excluded.

## Decisions flagged
1. **PDF dependency:** ReportLab **5.1.0**, pinned in `requirements.txt`; PyInstaller spec explicitly imports ReportLab font data. Helvetica used; no Archivo TTF embedded. Offline Windows/PyInstaller bundle itself has not been rebuilt/verified. Missing-library behavior hides PDF links and returns 404 if requested.
2. **School name:** renderer setting `SCHOOL_NAME`, fallback “NRZ Student Management”.
3. **Contact columns:** guardian name/phone require `view_student`; explicitly opt-in (`show_contact=1`), off by default.
4. **CSV header renames proposed, not applied:** Outstanding `Program` → `Trade`; Enrollment `Program` → `Trade`; Fee setup `Program` → `Trade` and `Year Level` → `Course year`; Revenue `Program` → `Trade`; Status history `Program` → `Trade`. Existing CSV headers remain for compatibility.
5. **Beyond-credit discrepancies:** trade attribution can cause a trade-level split mismatch as above; no verified sample numbers to cite. Payments without matching semester charges and withdrawn enrollment cases also need dedicated fixtures before claiming complete reconciliation.
6. **Wave art:** dashboard wave reused on hub; omitted from PDFs.
7. **PDF cap:** first 10,000 data rows; renderer includes a cap note. Not load-tested at cap.
8. **Navigation/templates:** duplicate in-page report navigation is removed from new views; legacy templates are retained, not deleted.

## Measured component styles
Values implemented from dashboard references (CSS declarations, not browser-computed measurements): title `clamp(1.5rem, 1.2rem + 1vw, 2rem)`, weight 800, stretch 106%; KPI label `.8125rem/650`, value `clamp(1.8rem, 2.7vw, 2.5rem)` with tabular figures; table header `.6875rem`, body `.75rem`, cells `.8rem .55rem`; student `.8125rem/750` uppercase, number `.6875rem`; controls/buttons minimum 44px; cards use `--paper`, `--line`, `--radius`. Computed styles/component-sheet comparison and contrast measurements remain unrecorded.

## Tests run
- `python -m py_compile school/reporting/*.py school/views.py school/models.py school/test_reports_overhaul.py` — passed after the final builder/view/test edits.
- `NRZ_DISABLE_SCHEDULER=1 python manage.py test school.test_reports_overhaul --verbosity 2` — 9 tests passed, covering legacy CSV schemas, BOM/count correction, all eight HTML/PDF responses, daily default and audit, hub/contact permissions, formula injection, and Owed/Credit/Net reconciliation.
- `NRZ_DISABLE_SCHEDULER=1 python manage.py test school --verbosity 1` — all 83 school tests passed after the final fee-grid and reconciliation changes.
- Not covered by those runs: query-count growth, PDF-unavailable fallback, three-role × four-format matrix, route-query parameter edge cases, and visual/manual checks.

## Artifacts and follow-ups
- Isolated QA data and captured baselines: [`baseline/`](baseline/). Available image captures are hub baseline widths 1440/1280/1024/768 and Outstanding at 390px; captured CSV samples and a QA SQLite copy are present. The requested full three-user/four-width baseline matrix, after screenshots, and sample PDFs were not completed.
- Ten-line phase plan: [`PLAN.md`](PLAN.md).
- Rebuild PyInstaller package; finish three-user form matrix, visual/long-print/grayscale/responsive checks, query-growth assertions, PDF fallback tests, and route/query contract tests. Fees-grid link is now implemented.
- Subsequent visual overhaul order: Semesters and Programs; Archive and Users; Audit trail and Backups; Reminders.
- Noticed but out of scope: `bulk_progress_students` permission; `console.log` in base Flatpickr setup; adding `EXPORT` AuditLog choice/migration; remaining Bootstrap-default pages.
