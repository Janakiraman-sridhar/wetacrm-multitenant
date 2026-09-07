"""Validation for Indian identity and contact fields.

Kept separate from the models because these rules are worth testing on their own —
a wrong Aadhaar checksum or a mangled phone number is the kind of thing that only
surfaces months later, in someone's WhatsApp message going nowhere.
"""

import re

from app.core.exceptions import AppError

PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

# Verhoeff tables. Aadhaar's last digit is a Verhoeff check digit, so a
# transposition or single-digit typo is caught here rather than at the insurer.
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(number: str) -> bool:
    checksum = 0
    for position, digit in enumerate(reversed(number)):
        if not digit.isdigit():
            return False
        checksum = _D[checksum][_P[position % 8][int(digit)]]
    return checksum == 0


def normalise_pan(value: str | None) -> str | None:
    """Uppercase and validate a PAN, or raise."""
    if value in (None, ""):
        return None
    pan = str(value).strip().upper().replace(" ", "")
    if not PAN_PATTERN.match(pan):
        raise AppError("PAN must look like ABCDE1234F")
    return pan


def normalise_aadhaar(value: str | None) -> str | None:
    """Strip formatting and check the Verhoeff digit, or raise."""
    if value in (None, ""):
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 12:
        raise AppError("Aadhaar must be 12 digits")
    if digits[0] in "01":
        raise AppError("Aadhaar cannot start with 0 or 1")
    if not verhoeff_valid(digits):
        raise AppError("Aadhaar number is not valid — check for a typo")
    return digits


def mask_pan(pan: str | None) -> str | None:
    """`ABCDE1234F` → `ABCDE****F`. Keeps enough to recognise, not enough to use."""
    if not pan or len(pan) != 10:
        return None
    return f"{pan[:5]}****{pan[-1]}"


def mask_aadhaar(aadhaar: str | None) -> str | None:
    """`123412341234` → `XXXX XXXX 1234`, the format UIDAI itself uses."""
    if not aadhaar or len(aadhaar) < 4:
        return None
    return f"XXXX XXXX {aadhaar[-4:]}"


def normalise_phone(value: str | None, country_code: str = "+91") -> str | None:
    """Best-effort E.164, so `wa.me` links and future API sends actually work.

    Deliberately forgiving: a number that cannot be parsed is kept as typed rather
    than rejected, because refusing to save a customer over a phone format would be
    worse than storing it imperfectly.
    """
    if value in (None, ""):
        return None
    raw = str(value).strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        return digits
    digits = re.sub(r"\D", "", digits)
    if not digits:
        return raw
    if len(digits) == 10:
        return f"{country_code}{digits}"
    if len(digits) > 10 and digits.startswith(country_code.lstrip("+")):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"{country_code}{digits[1:]}"
    return f"+{digits}"


def normalise_pincode(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 6:
        raise AppError("Pincode must be 6 digits")
    if digits[0] == "0":
        raise AppError("Pincode cannot start with 0")
    return digits
