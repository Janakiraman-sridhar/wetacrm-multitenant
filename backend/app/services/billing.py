"""Shared line-item math for quotations and invoices."""

from decimal import ROUND_HALF_UP, Decimal


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_items(items: list[dict]) -> tuple[list[dict], Decimal, Decimal]:
    """Returns (items with line_total/position filled, subtotal, tax_total)."""
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    out = []
    for pos, item in enumerate(items):
        qty, price, tax_rate = _d(item.get("quantity", 1)), _d(item.get("unit_price")), _d(item.get("tax_rate"))
        line_net = qty * price
        line_tax = line_net * tax_rate / Decimal("100")
        subtotal += line_net
        tax_total += line_tax
        out.append({**item, "line_total": _money(line_net + line_tax), "position": pos})
    return out, _money(subtotal), _money(tax_total)


def compute_total(subtotal: Decimal, tax_total: Decimal, discount) -> Decimal:
    total = subtotal + tax_total - _d(discount)
    return _money(total if total > 0 else Decimal("0"))
