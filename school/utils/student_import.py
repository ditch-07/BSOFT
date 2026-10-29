"""
Helpers for bulk-importing students from an Excel (.xlsx) or CSV spreadsheet.

The spreadsheets we've seen in the wild (see the sample register) have a
couple of title/merged-cell rows above the real header row, and a header row
that reads roughly: STUDENT NO | SURNAME | NAME | TRADE | 1st sem | 2nd sem...

We only care about four columns — student number, surname, name, trade — and
we detect them by header text rather than fixed position, so minor column
reordering or extra fee columns don't break the import.
"""
import csv
import io
import re

from openpyxl import load_workbook

from school.models import Program, Student


# Header aliases, normalised to UPPERCASE with non-alphanumeric characters
# stripped, so "Student No", "STUDENT NO.", "student_no" all match.
HEADER_ALIASES = {
    "student_number": {"STUDENTNO", "STUDENTNUMBER", "STUDENTID", "REGNO", "REGISTRATIONNO"},
    "last_name": {"SURNAME", "LASTNAME"},
    "first_name": {"NAME", "FIRSTNAME", "FIRSTNAMES", "GIVENNAME", "GIVENNAMES"},
    "program_code": {"TRADE", "TRAD", "PROGRAM", "PROGRAMME", "COURSE", "PROGRAMCODE"},
}

REQUIRED_FIELDS = ("student_number", "last_name", "first_name", "program_code")


def _normalise(value):
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _cell(row, index):
    if index is None or index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    return str(value).strip()


def _detect_header_row(rows, max_scan=10):
    """
    Scan the first `max_scan` rows and return the index of the first one that
    contains both a student-number-like header and a surname-like header.
    """
    for row_index, row in enumerate(rows[:max_scan]):
        normalised = [_normalise(cell) for cell in row]
        has_student_no = any(n in HEADER_ALIASES["student_number"] for n in normalised)
        has_surname = any(n in HEADER_ALIASES["last_name"] for n in normalised)
        if has_student_no and has_surname:
            return row_index, normalised
    return None, None


def _map_columns(normalised_header):
    column_map = {}
    for field, aliases in HEADER_ALIASES.items():
        for col_index, header in enumerate(normalised_header):
            if header in aliases:
                column_map[field] = col_index
                break
    return column_map


def _read_rows_xlsx(file_obj):
    wb = load_workbook(file_obj, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    return [list(row) for row in ws.iter_rows(values_only=True)]


def _read_rows_csv(file_obj):
    text = io.TextIOWrapper(file_obj.file if hasattr(file_obj, "file") else file_obj,
                             encoding="utf-8-sig")
    return [row for row in csv.reader(text)]


def parse_student_spreadsheet(uploaded_file):
    """
    Parse an uploaded .xlsx or .csv file into a list of row dicts:
        {"row_number": int, "student_number": str, "first_name": str,
         "last_name": str, "program_code": str}

    Raises ValueError with a user-facing message if no recognisable header
    row (or a required column) is found.
    """
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        rows = _read_rows_csv(uploaded_file)
    else:
        rows = _read_rows_xlsx(uploaded_file)

    header_row_index, normalised_header = _detect_header_row(rows)
    if header_row_index is None:
        raise ValueError(
            "Couldn't find a header row with recognisable 'Student No' and "
            "'Surname' columns in the first 10 rows of the file."
        )

    column_map = _map_columns(normalised_header)
    missing = [f for f in REQUIRED_FIELDS if f not in column_map]
    if missing:
        raise ValueError(
            "Missing required column(s) in the spreadsheet: " + ", ".join(missing)
        )

    parsed_rows = []
    for offset, row in enumerate(rows[header_row_index + 1:], start=1):
        student_number = _cell(row, column_map["student_number"])
        last_name = _cell(row, column_map["last_name"])
        first_name = _cell(row, column_map["first_name"])
        program_code = _cell(row, column_map["program_code"])

        # Stop counting once we hit a fully blank row (end of the data block).
        if not any([student_number, last_name, first_name, program_code]):
            continue

        parsed_rows.append({
            "row_number": header_row_index + 1 + offset,
            "student_number": student_number,
            "first_name": first_name,
            "last_name": last_name,
            "program_code": program_code,
        })

    return parsed_rows


def validate_rows(parsed_rows):
    """
    Cross-check parsed rows against the database. Returns a list of dicts,
    each of the input rows plus 'errors' (list of str) and 'program'
    (a Program instance or None). Does not touch the database.
    """
    existing_numbers = set(Student.objects.values_list("student_number", flat=True))

    # Match on either code or name — some setups put the trade abbreviation
    # (e.g. "ECS") in Program.name rather than Program.code, so check both.
    # If a value collides across programs, code wins.
    programs_by_lookup = {}
    for p in Program.objects.all():
        programs_by_lookup.setdefault(p.name.upper(), p)
    for p in Program.objects.all():
        programs_by_lookup[p.code.upper()] = p

    seen_in_file = set()
    results = []
    for row in parsed_rows:
        errors = []
        student_number = row["student_number"]
        program_code = row["program_code"]

        if not student_number:
            errors.append("Missing student number.")
        elif student_number in existing_numbers:
            errors.append(f"Student number '{student_number}' already exists.")
        elif student_number in seen_in_file:
            errors.append(f"Duplicate student number '{student_number}' in this file.")

        if not row["first_name"] or not row["last_name"]:
            errors.append("Missing first or last name.")

        program = programs_by_lookup.get(program_code.upper()) if program_code else None
        if not program_code:
            errors.append("Missing trade/program code.")
        elif not program:
            errors.append(
                f"No program found matching '{program_code}' (checked both code and name)."
            )

        if student_number:
            seen_in_file.add(student_number)

        results.append({**row, "errors": errors, "program": program})

    return results
