"""Quotation / invoice PDF generation with ReportLab."""

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PRIMARY = colors.HexColor("#4F46E5")
SLATE = colors.HexColor("#1E293B")


def _fmt(amount, currency: str) -> str:
    return f"{currency} {Decimal(str(amount or 0)):,.2f}"


def document_pdf(kind: str, doc, company_profile: dict) -> bytes:
    """Render a quotation or invoice to PDF. `doc` is a Quotation or Invoice ORM object."""
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=PRIMARY, alignment=0, fontSize=20)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=SLATE)

    title = "QUOTATION" if kind == "quotation" else "INVOICE"
    story = [Paragraph(f"{title} {doc.number}", h1), Spacer(1, 4 * mm)]

    org_name = company_profile.get("name") or "WeTa CRM"
    org_lines = [org_name, company_profile.get("address", ""), company_profile.get("email", ""), company_profile.get("phone", "")]
    story.append(Paragraph("<br/>".join(l for l in org_lines if l), small))
    story.append(Spacer(1, 6 * mm))

    bill_to = []
    if doc.company:
        bill_to.append(doc.company.name)
    if doc.contact:
        bill_to.append(f"{doc.contact.first_name} {doc.contact.last_name}".strip())
    meta_rows = [
        ["Bill To", "Date", "Status"],
        [
            "\n".join(bill_to) or "—",
            str(getattr(doc, "issue_date", "") or "—"),
            (doc.status or "").title(),
        ],
    ]
    meta = Table(meta_rows, colWidths=[80 * mm, 45 * mm, 45 * mm])
    meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), PRIMARY),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([meta, Spacer(1, 6 * mm)])

    rows = [["#", "Item", "Qty", "Unit Price", "Tax %", "Line Total"]]
    for i, item in enumerate(doc.items, start=1):
        rows.append([
            str(i), item.name, f"{Decimal(str(item.quantity)):g}",
            _fmt(item.unit_price, doc.currency), f"{Decimal(str(item.tax_rate)):g}", _fmt(item.line_total, doc.currency),
        ])
    items_table = Table(rows, colWidths=[10 * mm, 75 * mm, 18 * mm, 30 * mm, 16 * mm, 31 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.extend([items_table, Spacer(1, 5 * mm)])

    totals = [
        ["Subtotal", _fmt(doc.subtotal, doc.currency)],
        ["Discount", _fmt(doc.discount, doc.currency)],
        ["Tax", _fmt(doc.tax_total, doc.currency)],
        ["Total", _fmt(doc.total, doc.currency)],
    ]
    totals_table = Table(totals, colWidths=[140 * mm, 40 * mm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), PRIMARY),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, PRIMARY),
    ]))
    story.append(totals_table)

    for label, text in (("Notes", getattr(doc, "notes", None)), ("Terms", getattr(doc, "terms", None))):
        if text:
            story.extend([Spacer(1, 5 * mm), Paragraph(f"<b>{label}</b><br/>{text}", small)])

    pdf.build(story)
    return buf.getvalue()
