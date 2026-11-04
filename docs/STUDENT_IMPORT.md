# Student Spreadsheet Import

The Django interface provides a spreadsheet import workflow at
`/students/import/`. The route, view, form, parser, and template are already
wired into the application.

## Model migration

`Student.national_id` is now `blank=True, default=""` so imported students
without an ID on file can be saved. Run:

```bash
python manage.py makemigrations school
python manage.py migrate
```

Everything else you're missing per-row (national ID, DOB, gender, guardian
info, address, phone) was already optional on the model, so nothing else
needs a migration.

## Dependency

The parser uses `openpyxl` for `.xlsx` files (CSV uses the standard library).
`openpyxl` is included in `requirements.txt`.

## How the import works

1. **Upload page** (`/students/import/`): pick the file, the intake year
   (e.g. 2026), starting semester (e.g. Semester 1), starting year level,
   and the status to assign (defaults to Active).
2. **Parsing**: the file is scanned for a header row containing
   student-number-like and surname-like columns (handles the extra
   title/merged-cell rows and fee columns your sheet has — it only pulls
   `STUDENT NO`, `SURNAME`, `NAME`, `TRADE`).
3. **Preview**: nothing is saved yet. You see two tables — rows that will
   be imported, and rows that will be skipped with a reason (missing data,
   duplicate student number, or a trade/program code that doesn't match any
   existing `Program.code`).
4. **Confirm**: only the valid rows are created as `Student` records
   (`national_id` etc. left blank) plus their first `Enrollment` and any
   configured fee charges, using the same `create_academic_year_enrollments`
   helper your manual registration flow uses.

## Note on "trade" matching

The importer matches the spreadsheet's `TRADE` column against your
`Program.code` field (e.g. `DPF`), case-insensitively. Make sure every trade
code in the spreadsheet already exists as a `Program` in the system before
importing — rows with an unrecognised code will show up in the "skipped"
table with that reason, rather than silently failing.
