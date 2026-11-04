import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO, StringIO
from urllib.parse import urlencode

from django.http import HttpResponse
from django.utils import timezone


@dataclass(frozen=True)
class ReportColumn:
    label: str
    key: str
    numeric: bool = False


@dataclass
class ReportResult:
    title: str
    subtitle: str
    generated_at: datetime
    generated_by: str
    applied_filters: list = field(default_factory=list)
    kpis: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    empty_text: str = "No records match these filters."
    notes: list = field(default_factory=list)
    orientation: str = "portrait"
    filename_stem: str = "report"
    row_count: int = 0
    csv_columns: list = None
    csv_rows: list = None


def neutralize_cell(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_response(result, filename):
    output = StringIO(newline="")
    writer = csv.writer(output)
    columns = result.csv_columns or result.columns
    rows = result.csv_rows if result.csv_rows is not None else result.rows
    writer.writerow([column.label for column in columns])
    for row in rows:
        writer.writerow([
            row.get(column.key) if column.numeric else neutralize_cell(row.get(column.key, ""))
            for column in columns
        ])
    response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def safe_filename(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-._") or "report"


def query_url(path, params, **overrides):
    values = {key: value for key, value in params.items() if value not in (None, "")}
    values.update(overrides)
    return path + ("?" + urlencode(values, doseq=True) if values else "")


def pdf_response(result, filename, school_name="BSOFT Student Management", mark=None):
    """Return a ReportLab PDF attachment; None means the optional library is absent."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.platypus import LongTable, Paragraph, Spacer, Table, TableStyle, SimpleDocTemplate
    except ImportError:
        return None

    page_size = landscape(A4) if result.orientation == "landscape" else A4
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=16*mm,
                            title=result.title, author=result.generated_by)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=17, leading=21, textColor=colors.HexColor("#1F4F7A"), spaceAfter=4))
    styles.add(ParagraphStyle(name="ReportSmall", parent=styles["Normal"], fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="ReportCell", parent=styles["Normal"], fontSize=7.5, leading=9))
    styles.add(ParagraphStyle(name="ReportCellRight", parent=styles["ReportCell"], alignment=TA_RIGHT))

    def para(value, style):
        value = str(value if value is not None else "")
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(value, style)

    story = []
    if mark:
        story.append(para("BSOFT", styles["ReportSmall"]))
    story.extend([para(school_name, styles["Heading2"]), para(result.title, styles["ReportTitle"]),
                  para(result.subtitle, styles["ReportSmall"])])
    if result.applied_filters:
        story.append(para("Filters: " + " · ".join(f"{label}: {value}" for label, value in result.applied_filters), styles["ReportSmall"]))
    story.append(para(f"Generated {timezone.localtime(result.generated_at):%d %b %Y %H:%M} by {result.generated_by}", styles["ReportSmall"]))
    story.append(Spacer(1, 8))
    if result.title == "Daily collections":
        story.append(para("Prepared by: ______________________________    Checked by: ______________________________", styles["ReportSmall"]))
        story.append(para(f"Date: {dict(result.applied_filters).get('Date', '')}", styles["ReportSmall"]))
        story.append(Spacer(1, 6))
    if result.kpis:
        kpi_data = [[para(f"<b>{label}</b><br/>{value}", styles["ReportSmall"]) for label, value in result.kpis]]
        kpi = Table(kpi_data, hAlign="LEFT")
        kpi.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,colors.HexColor("#D6DAD5")),
                                 ("INNERGRID",(0,0),(-1,-1),.5,colors.HexColor("#D6DAD5")),
                                 ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
                                 ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.extend([kpi, Spacer(1, 8)])
    width = page_size[0] - 30*mm
    col_widths = [width / max(1, len(result.columns))] * len(result.columns)
    table_columns = result.columns
    table_rows = result.rows[:10000]
    if len(result.rows) > 10000:
        story.append(para(f"Export capped at 10,000 of {len(result.rows)} records.", styles["ReportSmall"]))
    data = [[para(f"<b>{column.label}</b>", styles["ReportCell"]) for column in table_columns]]
    for row in table_rows:
        data.append([para(row.get(column.key, ""), styles["ReportCellRight"] if column.numeric else styles["ReportCell"])
                     for column in table_columns])
    if result.totals and len(result.rows) <= 10000:
        data.append([para(f"<b>{result.totals.get(column.key, '')}</b>",
                          styles["ReportCellRight"] if column.numeric else styles["ReportCell"])
                     for column in table_columns])
    table = LongTable(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                               ("LINEBELOW",(0,0),(-1,0),.8,colors.HexColor("#1F4F7A")),
                               ("LINEBELOW",(0,1),(-1,-2),.35,colors.HexColor("#AEB6B5")),
                               ("LINEABOVE",(0,-1),(-1,-1),.9,colors.HexColor("#1E2B33")),
                               ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
                               ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.append(table)
    if result.title == "Daily collections":
        methods = []
        for note in result.notes:
            methods.append([para(note.split(":", 1)[0], styles["ReportCell"]),
                            para(note.split(":", 1)[1].strip() if ":" in note else "", styles["ReportCellRight"])])
        if methods:
            method_table = Table([[para("<b>Payment method</b>", styles["ReportCell"]), para("<b>Count · amount</b>", styles["ReportCellRight"])]] + methods,
                                 colWidths=[width * .55, width * .45], repeatRows=1)
            method_table.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,0),.7,colors.HexColor("#1F4F7A")),
                ("LINEBELOW",(0,1),(-1,-1),.35,colors.HexColor("#AEB6B5")), ("ALIGN",(1,0),(1,-1),"RIGHT")] ))
            story.extend([Spacer(1, 8), method_table])
    if not result.rows:
        story.append(para(result.empty_text, styles["ReportSmall"]))
    if len(result.rows) > 10000:
        story.append(para(f"Row cap: 10,000 of {len(result.rows)} records.", styles["ReportSmall"]))
    if result.notes:
        story.append(Spacer(1, 6))
        story.extend(para(note, styles["ReportSmall"]) for note in result.notes)

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._states = []
        def showPage(self):
            self._states.append(dict(self.__dict__))
            self._startPage()
        def save(self):
            total = len(self._states)
            for state in self._states:
                self.__dict__.update(state)
                self.setFont("Helvetica", 7)
                self.setFillColor(colors.HexColor("#4E5C66"))
                self.drawString(15*mm, 8*mm, f"BSOFT Student Management · {result.title}")
                self.drawRightString(page_size[0]-15*mm, 8*mm, f"Page {self._pageNumber} of {total}")
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    doc.build(story, canvasmaker=NumberedCanvas)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
