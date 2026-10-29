# Financial Records Tab - Implementation Plan

## Goal
Create an institution-wide financial reporting page showing aggregate charged/paid/outstanding per semester, grouped by academic year, with academic year filter and print-friendly layout.

---

## 1. Backend - New View (`school/views.py`)

**Function: `financial_records(request)`**

```python
def financial_records(request):
    # Get filter param (default to current academic year)
    year_filter = request.GET.get("academic_year", "")
    current_year = AcademicYear.objects.filter(is_current=True).first()
    default_year_id = str(current_year.pk) if current_year else ""
    selected_year_id = year_filter or default_year_id

    # Base queryset - all semesters with academic year
    semesters_qs = Semester.objects.select_related("academic_year").order_by(
        "-academic_year__name", "number"
    )

    # Apply year filter if provided
    if selected_year_id:
        semesters_qs = semesters_qs.filter(academic_year_id=selected_year_id)

    # Annotate each semester with financial aggregates
    semester_data = []
    for sem in semesters_qs:
        total_charged = StudentCharge.objects.filter(
            fee_item__fee_structure__semester=sem
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        total_paid = Payment.objects.filter(
            semester=sem
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        outstanding = total_charged - total_paid
        collection_rate = (total_paid / total_charged * 100) if total_charged > 0 else 0

        semester_data.append({
            "semester": sem,
            "academic_year": sem.academic_year,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "outstanding": outstanding,
            "collection_rate": collection_rate,
        })

    # Group by academic year for display
    from itertools import groupby
    year_groups = {}
    for item in semester_data:
        year = item["academic_year"]
        if year not in year_groups:
            year_groups[year] = []
        year_groups[year].append(item)

    # Calculate year totals
    year_totals = {}
    for year, semesters in year_groups.items():
        year_totals[year] = {
            "charged": sum(s["total_charged"] for s in semesters),
            "paid": sum(s["total_paid"] for s in semesters),
            "outstanding": sum(s["outstanding"] for s in semesters),
        }

    # All academic years for filter dropdown
    all_years = AcademicYear.objects.all().order_by("-name")

    context = {
        "year_groups": year_groups,
        "year_totals": year_totals,
        "all_years": all_years,
        "selected_year_id": selected_year_id,
        "current_year": current_year,
    }
    return render(request, "school/financial_records.html", context)
```

---

## 2. URL Routing (`school/urls.py`)

Add to `urlpatterns`:
```python
path("financial-records/", views.financial_records, name="financial_records"),
```

---

## 3. Navigation Update (`templates/base.html`)

Add new "Reports" section in sidebar (after "Academic Setup"):

```html
<hr>
<div class="sidebar-heading mb-1">Reports</div>
<div class="nav flex-column gap-1">
    <a href="{% url 'financial_records' %}"
       class="sidebar-link {% if request.resolver_match.url_name == 'financial_records' %}active{% endif %}">
        Financial Records
    </a>
</div>
```

---

## 4. Template (`templates/school/financial_records.html`)

**Key features:**
- Academic year filter dropdown (auto-submits on change)
- Tables grouped by academic year with year total rows
- Semester rows: Charged, Paid, Outstanding, Collection Rate
- Grand totals at bottom
- `@media print` CSS to hide navbar, sidebar, filter dropdown, buttons
- Clean header with institution name and report title

**Template structure:**
```html
{% extends "base.html" %}
{% block title %}Financial Records{% endblock %}
{% block content %}
<!-- Filter dropdown -->
<form method="get" class="mb-4">
    <select name="academic_year" class="form-select w-auto d-inline-block" onchange="this.form.submit()">
        <option value="">All Years</option>
        {% for y in all_years %}
        <option value="{{ y.pk }}" {% if selected_year_id == y.pk|stringformat:"s" %}selected{% endif %}>
            {{ y.name }}
        </option>
        {% endfor %}
    </select>
</form>

<!-- Report header -->
<div class="print-only mb-4">
    <h2 class="fw-bold">BSOFT Student Management</h2>
    <h3>Financial Records Report</h3>
    <p class="text-muted">Generated: {{ today|date:"F d, Y" }}</p>
</div>

<!-- Data tables grouped by year -->
{% for year, semesters in year_groups.items %}
<div class="card border-0 shadow-sm mb-4">
    <div class="card-header bg-light">
        <h5 class="mb-0">{{ year.name }} - Annual Summary</h5>
    </div>
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead>
                    <tr>
                        <th>Semester</th>
                        <th class="text-end">Charged</th>
                        <th class="text-end">Paid</th>
                        <th class="text-end">Outstanding</th>
                        <th class="text-end">Collection %</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in semesters %}
                    <tr>
                        <td>{{ s.semester }}</td>
                        <td class="text-end fw-bold">${{ s.total_charged|floatformat:2 }}</td>
                        <td class="text-end text-success fw-bold">${{ s.total_paid|floatformat:2 }}</td>
                        <td class="text-end {% if s.outstanding > 0 %}text-danger{% else %}text-success{% endif %} fw-bold">
                            ${{ s.outstanding|floatformat:2 }}
                        </td>
                        <td class="text-end">{{ s.collection_rate|floatformat:1 }}%</td>
                    </tr>
                    {% endfor %}
                    <!-- Year total row -->
                    <tr class="table-secondary fw-bold">
                        <td>{{ year.name }} TOTAL</td>
                        <td class="text-end">${{ year_totals.year.charged|floatformat:2 }}</td>
                        <td class="text-end text-success">${{ year_totals.year.paid|floatformat:2 }}</td>
                        <td class="text-end text-danger">${{ year_totals.year.outstanding|floatformat:2 }}</td>
                        <td class="text-end">{% if year_totals.year.charged > 0 %}{{ year_totals.year.paid|div:year_totals.year.charged|mul:100|floatformat:1 }}%{% else %}N/A{% endif %}</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
{% empty %}
<p class="text-center text-muted py-5">No semesters found.</p>
{% endfor %}

<!-- Grand totals -->
<div class="card border-0 shadow-sm">
    <div class="card-body">
        <h5 class="mb-3">Grand Totals</h5>
        <div class="row text-center">
            <div class="col-md-3">
                <div class="text-muted small">Total Charged</div>
                <div class="fw-bold fs-4">${{ grand_total_charged|floatformat:2 }}</div>
            </div>
            <div class="col-md-3">
                <div class="text-muted small">Total Paid</div>
                <div class="fw-bold fs-4 text-success">${{ grand_total_paid|floatformat:2 }}</div>
            </div>
            <div class="col-md-3">
                <div class="text-muted small">Total Outstanding</div>
                <div class="fw-bold fs-4 text-danger">${{ grand_total_outstanding|floatformat:2 }}</div>
            </div>
            <div class="col-md-3">
                <div class="text-muted small">Overall Collection</div>
                <div class="fw-bold fs-4">{{ grand_collection_rate|floatformat:1 }}%</div>
            </div>
        </div>
    </div>
</div>

{% block extra_css %}
<style>
@media print {
    .navbar, .sidebar, .btn, .form-select, form[method="get"], .print-hidden { display: none !important; }
    .container-fluid { display: block; }
    main { width: 100%; margin: 0; padding: 0; }
    .card { border: 1px solid #dee2e6 !important; box-shadow: none !important; page-break-inside: avoid; }
    .table { font-size: 0.85rem; }
    .card-header { background: #f8f9fa !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
.print-only { display: none; }
@media print { .print-only { display: block; } }
</style>
{% endblock %}
{% endblock %}
```

---

## 5. Files to Modify

| File | Change |
|------|--------|
| `school/views.py` | Add `financial_records` view |
| `school/urls.py` | Add `/financial-records/` path |
| `templates/base.html` | Add "Reports" section with Financial Records link |
| `templates/school/financial_records.html` | New template (create) |

---

## 6. Validation Steps

1. Navigate to `/financial-records/` → shows current academic year by default
2. Change academic year filter → page reloads with correct data
3. Verify semester totals match dashboard calculations for current semester
4. Verify year totals = sum of semester totals
5. Verify grand totals = sum of year totals
6. Print preview (Ctrl+P) → only tables and header visible, no navbar/sidebar
7. Test with no current academic year set → shows "All Years" by default

---

## 7. Edge Cases Handled

- No current academic year → defaults to "All Years"
- Academic year with no semesters → shows empty state
- Semester with no charges/payments → shows $0.00 across all columns
- Division by zero for collection rate → shows "N/A" or 0%
- Decimal precision maintained throughout (floatformat:2)

---

## 8. Out of Scope

- Per-program or per-student breakdown
- CSV/Excel export
- Date range filters (uses academic year only)
- Role-based access control (uses existing auth)