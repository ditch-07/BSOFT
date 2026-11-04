# Reports Overhaul Completion Progress

- [x] Safety snapshot before completion edits: `pre-completion.patch` (tracked diff) and `pre-completion-untracked.txt` (untracked path inventory), written before source edits. The diff includes existing build artifacts; leave both untouched as the requested snapshot.
- [x] WP0 baseline/sanity: `python manage.py check` clean; `BSOFT_DISABLE_SCHEDULER=1 python manage.py test school --verbosity 1` passed 83 tests. `extra_css` audit: `base.html` now defines the block; only `school/financial_records.html` and legacy `reports/_base.html` define it. Active report hub/shared report load `reports.css` from `extra_head`; `financial_records` returns the shared template before the legacy template, so the newly-live financial_records print CSS is not used by its active route. `school_tags` and protected UI/reference hashes captured in `pre-completion-protected.sha256`.
- [ ] WP1 CSV parity: append missing on-screen fields without changing legacy CSV prefixes; test builder/CSV/PDF parity.
- [ ] WP2 Revenue by trade reconciliation: old-trade charges/current-trade payments and student credit fixture; assert row and total identities or add adjustment row.
- [ ] WP3 automated matrix/contracts: permissions, hub/menu, query growth, legacy/hostile params, ReportLab missing, PDF edge cases/cap, injection, audit, daily defaults, counts, sorting/page size, typeahead permissions.
- [ ] WP4 template hygiene/protected hashes: remove only unreferenced legacy templates/dead CSS; verify references, `school_tags`, and protected file hashes.
- [ ] WP5 visual QA: QA-copy seeding, screenshots, computed styles, contrast, keyboard/focus/reduced motion, console, browser print, server PDF samples/renders/grayscale; record every gap.
- [ ] WP6 final report: every acceptance item Verified with evidence or Not verified with reason and manual script.
