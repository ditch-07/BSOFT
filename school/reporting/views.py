from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from school.models import AcademicYear, Program, Semester, Student
from school.reporting.builders import BUILDERS
from school.reporting.registry import REPORT_BY_VIEW, permitted_reports
from school.reporting.renderers import csv_response, pdf_response, safe_filename
from school.utils.audit import log_action
from school.utils.time_utils import get_current_date, get_working_semester


def _filename(spec, result, export_format):
    period = "all"
    filters = dict(result.applied_filters)
    if "Semester" in filters:
        period = filters["Semester"].replace(" · ", "-").replace(" ", "-")
    elif "Date" in filters:
        period = filters["Date"].replace(" ", "-").replace("–", "to")
    elif "Academic year" in filters:
        period = filters["Academic year"].replace(" ", "-")
    today = get_current_date().isoformat()
    return f"{safe_filename(spec.filename_stem)}_{safe_filename(period)}_{today}.{export_format}"


def _audit(request, spec, fmt, result):
    category = "FINANCIAL" if spec.group == "Money" else "STUDENT"
    log_action(request.user, "OTHER", summary=f"Exported {spec.title} ({fmt.upper()})",
               details={"report": spec.slug, "format": fmt,
                        "filters": dict(result.applied_filters), "rows": result.row_count},
               category=category)


def render_report(request, view_name, filter_type=None):
    spec = REPORT_BY_VIEW[view_name]
    result = BUILDERS[view_name](request)
    export_format = request.GET.get("format", "html").lower()
    if export_format not in ("html", "csv", "pdf"):
        export_format = "html"
    if export_format == "csv":
        _audit(request, spec, "csv", result)
        return csv_response(result, _filename(spec, result, "csv"))
    if export_format == "pdf":
        response = pdf_response(result, _filename(spec, result, "pdf"),
                                getattr(settings, "SCHOOL_NAME", "BSOFT Student Management"))
        if response is None:
            raise Http404("PDF export is unavailable because ReportLab is not installed.")
        _audit(request, spec, "pdf", result)
        return response

    rows = result.rows
    per_page = 50 if view_name == "status_history_report" else 25
    page_obj = Paginator(rows, per_page).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    common_query = urlencode(query, doseq=True)
    def page_url(page):
        params = query.copy()
        params["page"] = page
        return request.path + "?" + urlencode(params, doseq=True)
    pdf_available = _pdf_available()
    context = {
        "result": result,
        "page_obj": page_obj,
        "page_rows": page_obj.object_list,
        "page_number": page_obj.number,
        "page_count": page_obj.paginator.num_pages,
        "prev_url": page_url(page_obj.previous_page_number()) if page_obj.has_previous() else "",
        "next_url": page_url(page_obj.next_page_number()) if page_obj.has_next() else "",
        "permitted_reports": permitted_reports(request.user),
        "pdf_available": pdf_available,
        "csv_url": request.path + ("?" + common_query + "&" if common_query else "?") + "format=csv",
        "pdf_url": request.path + ("?" + common_query + "&" if common_query else "?") + "format=pdf",
        "print_url": request.path + ("?" + common_query + "&" if common_query else "?") + "format=pdf",
        "filter_type": filter_type or view_name,
        "selected_semester": _selected_semester(request),
        "all_semesters": Semester.objects.select_related("academic_year").order_by("-academic_year__name", "number"),
        "all_programs": Program.objects.filter(active=True).order_by("name"),
        "all_years": AcademicYear.objects.order_by("-name"),
        "all_intake_years": AcademicYear.objects.order_by("-name"),
        "status_choices": Student.STATUS_CHOICES,
        "program_id": request.GET.get("program", ""),
        "course_year": request.GET.get("course_year", ""),
        "show_contact": request.GET.get("show_contact") == "1" and request.user.has_perm("school.view_student"),
        "intake_year_filter": request.GET.get("intake_year", ""),
        "status_filter": request.GET.get("status", ""),
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "date_value": request.GET.get("date", "") or (get_current_date().isoformat() if view_name == "daily_collections_report" else ""),
        "start_date": request.GET.get("start_date", ""),
        "end_date": request.GET.get("end_date", ""),
        "student_id": request.GET.get("student", ""),
        "student_query": request.GET.get("student_query", ""),
        "selected_year_id": request.GET.get("academic_year", ""),
    }
    if view_name == "outstanding_report":
        context["course_years"] = range(1, max((program.duration_years for program in context["all_programs"]), default=1) + 1)
    if view_name == "daily_collections_report":
        context["date_value"] = request.GET.get("date", "") or get_current_date().isoformat()
    return render(request, "school/reports/report.html", context)


def _selected_semester(request):
    semester_id = request.GET.get("semester")
    if semester_id:
        try:
            return Semester.objects.select_related("academic_year").get(pk=semester_id)
        except (Semester.DoesNotExist, ValueError):
            pass
    return get_working_semester()


def _pdf_available():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return True


def _report_decorator(view_name):
    spec = REPORT_BY_VIEW[view_name]
    return permission_required(spec.permission, raise_exception=True)(
        lambda request: render_report(request, view_name)
    )
