"""The multi-insurer comparison an agent hands a customer.

Deliberately not `document_pdf`. That renderer prints line items down the page and
sums them; this one puts *insurers across the page* and sums nothing. Bending one
renderer to do both would mean a totals block that has to be suppressed and a
column layout that has to be transposed — two documents wearing one function.

The selected option is marked, because a comparison with no recommendation leaves
the customer exactly where they started.
"""

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.quotations.insurance import MONEY_FIELDS, COMPARISON_ROWS, comparison_rows, selected_option

ACCENT = colors.HexColor("#4F46E5")
SLATE = colors.HexColor("#1E293B")
GRAY = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#CBD5E1")
HIGHLIGHT = colors.HexColor("#ECFDF5")

_MONEY_LABELS = {label for key, label in COMPARISON_ROWS if key in MONEY_FIELDS}
_PERCENT_LABELS = {label for key, label in COMPARISON_ROWS if key.endswith("_percent")}


def _cell(value, label: str, currency: str) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if label in _MONEY_LABELS:
        return f"{currency} {Decimal(str(value)):,.0f}"
    if label in _PERCENT_LABELS:
        # A bare "25" under "No-claim bonus" reads as ₹25 to a customer skimming a
        # sheet of money columns.
        return f"{Decimal(str(value)):g}%"
    return str(value)


def comparison_pdf(quotation, profile: dict, logo: bytes | None = None) -> bytes:
    options = (quotation.insurance or {}).get("options", [])
    if not options:
        raise ValueError("Nothing to compare — this quotation has no options")

    currency = quotation.currency or "INR"
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"{quotation.number} comparison",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, textColor=SLATE, leading=11)
    small_gray = ParagraphStyle("smallgray", parent=small, textColor=GRAY)
    story = []

    # --- header
    org = profile.get("name") or "WeTa CRM"
    left = [Paragraph(f"<b>{org}</b>", styles["Heading3"])]
    for line in (profile.get("address"), profile.get("phone"), profile.get("email")):
        if line:
            left.append(Paragraph(str(line), small_gray))
    if logo:
        try:
            left.insert(0, Image(ImageReader(io.BytesIO(logo)), width=32 * mm, height=14 * mm, kind="proportional"))
        except Exception:
            pass

    customer = ""
    if quotation.contact:
        customer = f"{quotation.contact.first_name} {quotation.contact.last_name}".strip()
    risk = quotation.insurance or {}
    right = [
        Paragraph("<b>Insurance comparison</b>", ParagraphStyle("t", parent=styles["Heading2"], alignment=2, textColor=ACCENT)),
        Paragraph(quotation.number, ParagraphStyle("n", parent=small, alignment=2)),
    ]
    for label, value in (
        ("Prepared for", customer),
        ("Cover", str(risk.get("product_line") or "").title()),
        ("Vehicle / policy", risk.get("registration_no") or risk.get("existing_policy_no")),
        ("Valid until", quotation.valid_until),
    ):
        if value:
            right.append(Paragraph(f"{label}: <b>{value}</b>", ParagraphStyle("r", parent=small_gray, alignment=2)))

    header = Table([[left, right]], colWidths=[150 * mm, 119 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([header, Spacer(1, 6 * mm)])

    # --- comparison grid: one column per insurer
    def head(option: dict) -> Paragraph:
        name = option.get("insurer_name") or "Insurer"
        tag = " ★" if option.get("selected") else ""
        return Paragraph(
            f"<b>{name}{tag}</b>",
            ParagraphStyle("h", parent=small, textColor=colors.white, alignment=1),
        )

    rows = [[Paragraph("<b></b>", small)] + [head(o) for o in options]]
    for label, values in comparison_rows(quotation.insurance):
        rows.append(
            [Paragraph(f"<b>{label}</b>", small)]
            + [Paragraph(_cell(v, label, currency), ParagraphStyle("c", parent=small, alignment=1)) for v in values]
        )

    # Fill the page rather than leaving a dead gutter beside a three-insurer sheet;
    # capped so a two-option comparison does not become two enormous columns.
    label_width = 42 * mm
    column_width = min(78 * mm, (269 * mm - label_width) / len(options))
    table = Table(rows, colWidths=[label_width] + [column_width] * len(options), repeatRows=1)
    table.hAlign = "CENTER"

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]
    chosen = next((i for i, o in enumerate(options) if o.get("selected")), None)
    if chosen is not None:
        column = chosen + 1
        style += [
            ("BACKGROUND", (column, 1), (column, -1), HIGHLIGHT),
            ("BOX", (column, 0), (column, -1), 1.1, colors.HexColor("#10B981")),
        ]
    table.setStyle(TableStyle(style))
    story.append(table)

    picked = selected_option(quotation.insurance)
    if picked:
        story.extend([
            Spacer(1, 5 * mm),
            Paragraph(
                f"★ Recommended: <b>{picked.get('insurer_name') or 'selected plan'}</b> at "
                f"<b>{currency} {Decimal(str(picked.get('premium_gross') or 0)):,.2f}</b> payable.",
                ParagraphStyle("rec", parent=small, textColor=colors.HexColor("#047857"), fontSize=10),
            ),
        ])

    for label, text in (("Notes", quotation.notes), ("Terms", quotation.terms)):
        if text:
            story.extend([Spacer(1, 4 * mm), Paragraph(f"<b>{label}</b><br/>{text}", small)])

    story.extend([
        Spacer(1, 6 * mm),
        Paragraph(
            "Premiums are indicative and subject to the insurer's underwriting. Cover, "
            "exclusions and waiting periods are as per the policy wording.",
            ParagraphStyle("disc", parent=small_gray, fontSize=7.5),
        ),
    ])

    pdf.build(story)
    return buf.getvalue()
