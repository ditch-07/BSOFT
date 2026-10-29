# Navbar UX Overhaul — Report

Date: 2026-10-28 · Django server-rendered app · no model or migration changes.

## What changed

**Global bar** (`base.html`, `navbar.css`, `nav-waves.svg`)
The 48px bar is now 60px, driven by one `--nav-h` variable. Six offset occurrences in `base.html` use it; no application template or stylesheet retains a hard-coded 48px offset. The original 2.6KB local SVG has six layered navy ridge/contour groups with teal/aqua strokes, a solid fallback, a quiet scrim, and no animation or remote assets. Brand casing is consistently **Bsoft**.

**Semester and testing clock**
The chip uses `get_current_date()` to select the active semester, falling back to the next upcoming semester with an **Upcoming** label. It links to Semesters. An active testing override changes the chip to an amber warning and shows `Testing clock: 12 Jan 2027`, linking to Time Override. At 1100px and below, this information moves into the user menu.

**Student search**
The centre combobox searches active and deferred students by partial name or student number. It debounces for 200ms, starts at two characters, returns at most eight results, aborts superseded requests, and shows `Search unavailable. Try again.` on failure. Results include name, number, trade, course year, status word/dot, **Open**, and **Pay**. Pay is disabled for deferred students because the existing payment view accepts active students. Enter opens the first/active result; arrows move, Escape closes, `/` and Ctrl/⌘ K focus search, and a live region announces counts. Result text is built with `textContent`.

**Actions, attention, and user**
Record payment and Register student mirror `can_record_payments` and `add_student`. On Student detail only, the global payment action includes `?student=<pk>`. The attention menu reuses `unconfigured_fee_structures()` and `students_with_missing_details()`; fee rows require `add_feestructure` and link to the exact current/upcoming Fees grid with `?filter=needs`. One 45-second Django-cache entry backs both the attention summary and sidebar reminder badge; warm processor calls add zero queries. The user menu shows initials, username, name/role, Administration for staff, and POST Logout with CSRF.

**Sidebar and responsive behaviour**
Academic years is now before Semesters. The old navbar Students and Academics buttons are gone; Students remains in the sidebar and Academic years remains reachable. Logout moved from the sidebar to the user menu. Fees now resolves directly to the current/upcoming fee grid when the user has `view_feestructure`; it falls back to Semesters otherwise. Search collapses to an icon at 900px, quick actions become icon-only with tooltips, and the existing stacked layout remains at 768px. Print CSS hides the navbar and sidebar.

Screenshots: `docs/navbar-overhaul/` contains before/after captures at 1440, 1280, 1024 and 768px, plus search, attention, user, testing-clock, Fees, Student list/detail and sticky-form states.

## Acceptance checks

| Test | Result | Interactions / evidence |
| --- | --- | --- |
| 1. Find and open a student | Passed live from Dashboard | 2: type `Ema`, Enter → `/students/2/`; arrows and active descendant verified |
| 2. Start a payment for a student | Passed live | 2: search `Ema`, Pay → `/payments/new/?student=2`; Ema and semester preselected |
| 3. Working semester always visible | Passed | Current/upcoming chip; 1024px user-menu fallback; testing warning screenshot |
| 4. Reach attention items exactly | Passed live | Badge 20 = 5 fee cells + 15 missing-detail students; rows link to Fees `?filter=needs` and Reminders |
| 5. Existing destinations remain | Passed | Students sidebar, Academic years sidebar, POST Logout test |
| 6. Recognisable calm Bsoft bar | Passed | Original contour artwork; no clipping/overflow; text contrast 6.80:1–18.13:1 |

Layout checks passed at 1440, 1280, 1024 and 768px. Focus is visible at every width (3px outline or search box-shadow). Dropdowns render above page/sidebar content and stay inside the viewport. Fees, Student list, Student detail, Register Student’s sticky action bar, and report print media were checked.

## Section 8 decisions

1. **Height:** 60px; six occurrences, all in `base.html`, replaced with `--nav-h`.
2. **Fees sidebar:** repointed to the current/upcoming Fees grid when permitted; fallback is Semesters.
3. **Moved/removed:** Academics → Academic years sidebar link; Logout → user menu; old Students button removed, sidebar Students retained.
4. **Search extension:** `include_deferred=1` opts the global search into Active + Deferred. The existing payment-form request remains active-only. Results are capped at eight and now include course year, status, detail URL, and permission-aware payment URL.
5. **Casing:** **Bsoft** in both the title and brand.

## Tests

`python manage.py test school` → **31 tests, OK**. New `school/test_navbar.py` covers superuser, payment-only and read-only rendering; permission-gated actions; student-aware payment links; POST logout; testing-clock state; dashboard/sidebar count consistency; zero-query warm cache reads; partial name/number search; deferred inclusion; active-only legacy payment search; and the eight-result cap. `node --check static/js/navbar.js` and `git diff --check` also pass.

## Not changed / notes

- No API, Nuxt, SPA, dashboard, payment, fee-page, sidebar-general, model, migration, framework, build-step, or remote-asset work was done.
- Flatpickr `console.log` initialisation remains unchanged.
- Sidebar still says Programs rather than Trade.
- `request.resolver_match.url_name` checks remain unchanged on unmatched 404 routes.
- Semesters and Fees share a fallback destination only when no resolvable/permitted fee grid exists; otherwise the previous redundant link is removed.
- No commits were created: the working tree already contained unrelated and overlapping uncommitted work, so phase commits could not be isolated safely.
