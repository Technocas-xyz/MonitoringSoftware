"""Report exporters (spec 38): CSV / Excel / PDF.

CSV is built-in (stdlib). XLSX uses openpyxl and PDF uses reportlab when available; both are
imported lazily so the dependencies are optional. If an optional library is missing, we fall
back to CSV bytes with a note so report generation never hard-fails.
"""
from __future__ import annotations

import csv
import io

from app.reports.builders import ReportData


def to_csv(data: ReportData) -> tuple[bytes, str, str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(data.columns)
    writer.writerows(data.rows)
    return buf.getvalue().encode("utf-8"), "text/csv", "csv"


def to_xlsx(data: ReportData) -> tuple[bytes, str, str]:
    try:
        from openpyxl import Workbook  # type: ignore
    except Exception:
        return to_csv(data)  # graceful fallback

    wb = Workbook()
    ws = wb.active
    ws.title = data.title[:31]
    ws.append(data.columns)
    for row in data.rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return (
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    )


def to_pdf(data: ReportData) -> tuple[bytes, str, str]:
    try:
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.pagesizes import landscape, letter  # type: ignore
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle  # type: ignore
    except Exception:
        return to_csv(data)  # graceful fallback

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), title=data.title)
    table = Table([data.columns] + data.rows)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    doc.build([table])
    return buf.getvalue(), "application/pdf", "pdf"


def export(data: ReportData, fmt: str) -> tuple[bytes, str, str]:
    """Return (bytes, content_type, extension)."""
    if fmt == "xlsx":
        return to_xlsx(data)
    if fmt == "pdf":
        return to_pdf(data)
    return to_csv(data)
