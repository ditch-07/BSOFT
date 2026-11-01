1. Recon all report templates/views/helpers, UI references, permissions, packaging configuration, and existing test/data setup; preserve the dirty worktree and exclude API/Nuxt paths.
2. Prepare a separate scheduler-disabled SQLite QA copy; capture baseline report screens at 1440/1280/1024/768 for superuser, Finance bursar, and read-only users, plus current CSVs.
3. Add report characterization tests for legacy CSV headers/row ordering and current headline calculations, marking only the specified transaction-count defect as an intentional correction.
4. Repair shared extra-CSS delivery and print overflow; extend shared ui.css minimally and add scoped reports.css, registry, definitions, Result/builders, query-string helpers, and generic renderers.
5. Replace the report hub with permitted question-first groups and live quick answers, then implement Outstanding balances end-to-end as the measured exemplar.
6. Implement Outstanding CSV/PDF/print, contact-data permission/default, sorting/pagination/export contracts, audit logging, and tests before migrating another report.
7. Migrate Daily collections, Financial records, Revenue by trade, Payment methods, Enrollment summary, Fee setup check, and Status history one at a time using shared result renderers.
8. Reconcile Owed/Credit/Net definitions and grouped aggregates; test filters, URLs, permission matrix, export equivalence, and query-count growth.
9. Run narrow and full school tests on isolated data; verify export fallbacks, long PDF/print output, responsive/focus/contrast behavior, and hash-protect untouched student/dashboard/navbar references.
10. Save logical phase patches, QA screenshots/sample PDFs, measured component styles, acceptance/permission/route/defect tables, unresolved decisions, and out-of-scope follow-ups in the final report.
