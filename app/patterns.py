from __future__ import annotations

import re

# PF meter serial: FIOR + exactly 12 digits (e.g. FIOR034426017368)
FIOR_SERIAL_RE = re.compile(r"FIOR(\d{12})\b", re.IGNORECASE)

# Itron meter serial: STS + digits
ITRON_SERIAL_RE = re.compile(r"STS(\d+)\b", re.IGNORECASE)

# Metrological seal on PF stickers: *1139778*, 1139778*, or AzMi 1138438
PF_SEAL_RE = re.compile(
    r"(?:"
    r"\*(\d{7})\*?"
    r"|"
    r"(\d{7})\*"
    r"|"
    r"(?:AzMi|AZMI|AzMİ)\s*[\"'*]*(\d{7})"
    r")",
    re.IGNORECASE,
)

# LCD / label reading: 00000.328 or 00000,328
METER_READING_RE = re.compile(r"\b(\d{5}[.,]\d{3})\b")

# Bottom PF barcode label (ignored for serial extraction)
APF_BARCODE_RE = re.compile(r"APF\d+", re.IGNORECASE)


def extract_fior_serial(text: str) -> str | None:
    match = FIOR_SERIAL_RE.search(text)
    if match:
        return f"FIOR{match.group(1)}".upper()
    return None


def extract_itron_serial(text: str) -> str | None:
    match = ITRON_SERIAL_RE.search(text)
    if match:
        return f"STS{match.group(1)}".upper()
    return None


def extract_pf_seal(text: str) -> str | None:
    match = PF_SEAL_RE.search(text)
    if not match:
        return None
    return next((group for group in match.groups() if group), None)


def extract_meter_reading(text: str) -> str | None:
    match = METER_READING_RE.search(text)
    if not match:
        return None
    return match.group(1).replace(",", ".")


def extract_apf_barcodes(text: str) -> list[str]:
    return [m.group(0).upper() for m in APF_BARCODE_RE.finditer(text)]
