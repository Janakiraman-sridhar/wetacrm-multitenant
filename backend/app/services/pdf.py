"""Quotation / invoice PDF generation with ReportLab.

The rendering is driven by the customizable <kind>_template setting, Zoho-Books
style: layout preset, font, accent color, logo, column labels, optional tax
column, bank details and an authorized-signatory block.
"""

import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEFAULT_ACCENT = "#4F46E5"
SLATE = colors.HexColor("#1E293B")
GRAY = colors.HexColor("#64748B")
LIGHT_LINE = colors.HexColor("#CBD5E1")

FONT_MAP = {
    "helvetica": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"),
    "times": ("Times-Roman", "Times-Bold", "Times-Italic"),
}

LAYOUTS = ["modern", "classic", "minimal"]


def _fmt(amount, currency: str) -> str:
    return f"{currency} {Decimal(str(amount or 0)):,.2f}"


def _accent_color(template: dict):
    raw = str(template.get("accent_color") or DEFAULT_ACCENT)
    try:
        return colors.HexColor(raw)
    except Exception:
        return colors.HexColor(DEFAULT_ACCENT)


def sample_document(kind: str):
    """Fake document used by the Settings live preview."""
    items = [
        SimpleNamespace(name="Consulting services", quantity=10, unit_price=5000, tax_rate=18, line_total=59000),
        SimpleNamespace(name="Software licence (annual)", quantity=2, unit_price=25000, tax_rate=18, line_total=59000),
        SimpleNamespace(name="Onboarding & training", quantity=1, unit_price=20000, tax_rate=18, line_total=23600),
    ]
    return SimpleNamespace(
        number=("QT" if kind == "quotation" else "INV") + "-2026-0042",
        company=SimpleNamespace(name="Acme Industries Pvt Ltd"),
        contact=SimpleNamespace(first_name="Priya", last_name="Sharma"),
        status="sent",
        issue_date=date.today(),
        currency="INR",
        subtotal=140000,
        tax_total=25200,
        discount=23600,
        total=141600,
        notes="Sample notes shown on the document.",
        terms="Payment due within 30 days of the issue date.",
        items=items,
    )


def document_pdf(
    kind: str,
    doc,
    company_profile: dict,
    template: dict | None = None,
    logo_bytes: bytes | None = None,
) -> bytes:
    template = template or {}
    accent = _accent_color(template)
    layout = template.get("layout") if template.get("layout") in LAYOUTS else "modern"
    base_font, bold_font, italic_font = FONT_MAP.get(str(template.get("font") or "helvetica").lower(), FONT_MAP["helvetica"])
    show_tax = template.get("show_tax_column", True)
    show_signature = template.get("show_signature", True)
    show_logo = template.get("show_logo", True)
    title_color = SLATE if layout == "classic" else accent

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=title_color, alignment=2, fontSize=19, fontName=bold_font)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=SLATE, fontName=base_font)
    small_gray = ParagraphStyle("small_gray", parent=small, textColor=GRAY)
    org_style = ParagraphStyle("org", parent=small, fontSize=11, fontName=bold_font)

    title = str(template.get("title") or ("QUOTATION" if kind == "quotation" else "INVOICE")).upper()
    org_name = company_profile.get("name") or "WeTa CRM"

    # --- header: logo + company block on the left, title/number/date on the right
    left_parts = []
    if show_logo and logo_bytes:
        try:
            reader = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = reader.getSize()
            height = 16 * mm
            left_parts.append(Image(io.BytesIO(logo_bytes), width=iw / ih * height, height=height, hAlign="LEFT"))
            left_parts.append(Spacer(1, 2 * mm))
        except Exception:
            pass
    left_parts.append(Paragraph(org_name, org_style))
    org_lines = [company_profile.get("address", ""), company_profile.get("email", ""), company_profile.get("phone", ""), company_profile.get("website", "")]
    org_text = "<br/>".join(l for l in org_lines if l)
    if org_text:
        left_parts.append(Paragraph(org_text, small_gray))

    right_parts = [
        Paragraph(title, h1),
        Paragraph(
            f"<b>{doc.number}</b><br/>Date: {getattr(doc, 'issue_date', '') or '—'}<br/>Status: {(doc.status or '').title()}",
            ParagraphStyle("meta", parent=small, alignment=2),
        ),
    ]
    header = Table([[left_parts, right_parts]], colWidths=[100 * mm, 80 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story = [header, Spacer(1, 6 * mm)]

    # --- bill to
    bill_to = []
    if doc.company:
        bill_to.append(doc.company.name)
    if doc.contact:
        bill_to.append(f"{doc.contact.first_name} {doc.contact.last_name}".strip())
    bill_style = ParagraphStyle("bill", parent=small, fontSize=10)
    story.append(Paragraph(f"<font color='{template.get('accent_color') or DEFAULT_ACCENT}'><b>Bill To</b></font>", small))
    story.append(Paragraph("<br/>".join(bill_to) or "—", bill_style))
    story.append(Spacer(1, 5 * mm))

    # --- items table
    labels = {
        "item": template.get("label_item") or "Item & Description",
        "quantity": template.get("label_quantity") or "Qty",
        "rate": template.get("label_rate") or "Rate",
        "tax": template.get("label_tax") or "Tax %",
        "amount": template.get("label_amount") or "Amount",
    }
    if show_tax:
        head = ["#", labels["item"], labels["quantity"], labels["rate"], labels["tax"], labels["amount"]]
        widths = [9 * mm, 76 * mm, 16 * mm, 29 * mm, 16 * mm, 34 * mm]
    else:
        head = ["#", labels["item"], labels["quantity"], labels["rate"], labels["amount"]]
        widths = [9 * mm, 92 * mm, 16 * mm, 29 * mm, 34 * mm]
    rows = [head]
    for i, item in enumerate(doc.items, start=1):
        row = [str(i), item.name, f"{Decimal(str(item.quantity)):g}", _fmt(item.unit_price, doc.currency)]
        if show_tax:
            row.append(f"{Decimal(str(item.tax_rate)):g}")
        row.append(_fmt(item.line_total, doc.currency))
        rows.append(row)

    items_table = Table(rows, colWidths=widths, repeatRows=1)
    base_style = [
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, 1), (-1, -1), base_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]
    if layout == "modern":
        base_style += [
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_LINE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]
    elif layout == "classic":
        base_style += [
            ("TEXTCOLOR", (0, 0), (-1, 0), SLATE),
            ("LINEABOVE", (0, 0), (-1, 0), 1, SLATE),
            ("LINEBELOW", (0, 0), (-1, 0), 1, SLATE),
            ("LINEBELOW", (0, -1), (-1, -1), 1, SLATE),
            ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_LINE),
        ]
    else:  # minimal
        base_style += [
            ("TEXTCOLOR", (0, 0), (-1, 0), accent),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ]
    items_table.setStyle(TableStyle(base_style))
    story.extend([items_table, Spacer(1, 5 * mm)])

    # --- totals
    totals = [["Subtotal", _fmt(doc.subtotal, doc.currency)]]
    if float(doc.discount or 0) > 0:
        totals.append(["Discount", f"- {_fmt(doc.discount, doc.currency)}"])
    totals.append(["Tax", _fmt(doc.tax_total, doc.currency)])
    totals.append(["Total", _fmt(doc.total, doc.currency)])
    if kind == "invoice" and float(getattr(doc, "amount_paid", 0) or 0) > 0:
        totals.append(["Amount Paid", f"- {_fmt(doc.amount_paid, doc.currency)}"])
        totals.append(["Balance Due", _fmt(float(doc.total or 0) - float(doc.amount_paid or 0), doc.currency)])
    totals_table = Table(totals, colWidths=[140 * mm, 40 * mm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -2), base_font),
        ("FONTNAME", (0, -1), (-1, -1), bold_font),
        ("TEXTCOLOR", (0, -1), (-1, -1), title_color),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, title_color),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(totals_table)

    # --- notes & terms
    for label, text in (("Notes", getattr(doc, "notes", None)), ("Terms", getattr(doc, "terms", None))):
        if text:
            story.extend([Spacer(1, 4 * mm), Paragraph(f"<b>{label}</b><br/>{text}", small)])

    # --- bank details + signature
    bank_details = template.get("bank_details") or ""
    if bank_details or show_signature:
        left = []
        if bank_details:
            left.append(Paragraph("<b>Payment details</b><br/>" + str(bank_details).replace("\n", "<br/>"), small))
        right = []
        if show_signature:
            right.append(Paragraph(f"For <b>{org_name}</b>", ParagraphStyle("sig", parent=small, alignment=2)))
            right.append(Spacer(1, 14 * mm))
            right.append(Paragraph(
                str(template.get("signature_label") or "Authorized Signatory"),
                ParagraphStyle("sig2", parent=small_gray, alignment=2),
            ))
        block = Table([[left, right]], colWidths=[110 * mm, 70 * mm])
        block.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.extend([Spacer(1, 10 * mm), block])

    # --- footer note
    footer_note = template.get("footer_note")
    if footer_note:
        footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontSize=9, textColor=GRAY, alignment=1, fontName=italic_font)
        story.extend([Spacer(1, 8 * mm), Paragraph(str(footer_note), footer_style)])

    pdf.build(story)
    return buf.getvalue()
