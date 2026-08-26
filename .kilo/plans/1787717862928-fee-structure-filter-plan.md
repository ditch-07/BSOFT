# Fee Structure List Filter Implementation Plan

## Goal
Add program and year level filters to the fee structure list view (`/semesters/<id>/fee-structures/`) with dropdown UI above the table.

## Current State
- `fee_structure_list` view builds rows for ALL active programs × their duration_years
- Template shows all rows in a single table without filtering

## Implementation Steps

### 1. Update `fee_structure_list` view (`school/views.py:325-358`)
- Accept `program` and `year_level` query parameters
- Filter `Program.objects.filter(active=True)` by program_id if provided
- Filter year_level range by program's `duration_years` if program selected, else use max duration
- Pass filter values and filter options to template context

### 2. Update template (`templates/school/fee_structure_list.html`)
- Add filter form above table with:
  - Program dropdown (all active programs)
  - Year level dropdown (dynamic options based on selected program)
  - "Apply" and "Clear" buttons
- Use JavaScript to update year level options when program changes
- Preserve filters in edit/create links: `?program=X&year_level=Y`

### 3. Update `fee_structure_create` view (`school/views.py:361-404`)
- Accept and preserve filter params in redirect after save
- Redirect back to list with filters intact

### 4. Update `fee_structure_edit` view (`school/views.py:407-436`)
- Accept and preserve filter params in redirect after save

## Data Flow
```
GET /semesters/1/fee-structures/?program=2&year_level=3
  → fee_structure_list()
    → Filter programs (if program param)
    → Build rows for filtered program/year_level
    → Render template with filter values
  → Template shows filtered table + active filter badges
```

## Edge Cases
- Invalid program_id → ignore filter, show all
- Invalid year_level (exceeds program duration) → ignore filter
- No program selected → year level dropdown shows max possible (1-6)
- Empty results → show "No matching fee structures" message

## Validation
- Manual test: select program → year level updates → apply filter → table filters
- Test: click "Edit" on filtered row → edit → save → returns to filtered list
- Test: click "Configure" on empty row → create → save → returns to filtered list
- Test: clear filters → shows all rows again