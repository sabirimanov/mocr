from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np

from app.patterns import METER_READING_RE, extract_meter_reading
from app.regions import CropRegion

# Default LCD crop for Pietro Fiorentini G4 faceplate (normalized coords).
# Excludes the m³ unit on the right of the display.
PF_LCD_CROP = CropRegion(0.34, 0.185, 0.53, 0.268)

# 7-segment patterns: segments a,b,c,d,e,f,g
_DIGIT_SEGMENTS: dict[str, set[str]] = {
    "0": {"a", "b", "c", "d", "e", "f"},
    "1": {"b", "c"},
    "2": {"a", "b", "d", "e", "g"},
    "3": {"a", "b", "c", "d", "g"},
    "4": {"b", "c", "f", "g"},
    "5": {"a", "c", "d", "f", "g"},
    "6": {"a", "c", "d", "e", "f", "g"},
    "7": {"a", "b", "c"},
    "8": {"a", "b", "c", "d", "e", "f", "g"},
    "9": {"a", "b", "c", "d", "f", "g"},
}


@dataclass(frozen=True)
class LcdReadingResult:
    reading: str | None
    source: str | None = None


def extract_lcd_reading(
    image: np.ndarray,
    crop: CropRegion | None = None,
    ocr_fallback_text: str | None = None,
) -> LcdReadingResult:
    """Best-effort LCD reading from display crop."""
    region = crop or PF_LCD_CROP
    lcd = region.apply(image)
    if lcd.size == 0:
        return LcdReadingResult(None, None)

    reading = _reading_from_7segment(lcd)
    if reading:
        return LcdReadingResult(reading, "lcd_7segment")

    reading = _reading_from_tesseract(lcd)
    if reading:
        return LcdReadingResult(reading, "lcd_tesseract")

    if ocr_fallback_text:
        reading = extract_meter_reading(ocr_fallback_text)
        if reading:
            return LcdReadingResult(reading, "ocr")

    return LcdReadingResult(None, None)


def _reading_from_7segment(lcd: np.ndarray) -> str | None:
    gray = cv2.cvtColor(lcd, cv2.COLOR_BGR2GRAY) if len(lcd.shape) == 3 else lcd

    for threshold in (108, 112, 115, 118, 122):
        mask = np.where(gray < threshold, 255, 0).astype(np.uint8)
        upscaled = cv2.resize(mask, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
        reading = _decode_7segment_mask(upscaled)
        if reading:
            return reading
    return None


def _decode_7segment_mask(mask: np.ndarray) -> str | None:
    coords = cv2.findNonZero(mask)
    if coords is None:
        return None

    x, y, width, height = cv2.boundingRect(coords)
    if width < 30 or height < 10:
        return None

    roi = mask[y : y + height, x : x + width]

    # PF LCD layout is fixed: NNNNN.DDD (5 digits, decimal, 3 digits).
    slots = _fixed_digit_slots(roi)
    if not slots:
        columns = _split_columns(roi)
        slots = columns

    chars: list[str] = []
    for index, (col_start, col_end) in enumerate(slots):
        col_width = col_end - col_start
        if col_width < 2:
            continue
        # Sixth slot is the decimal point on PF displays.
        if len(slots) == 9 and index == 5:
            chars.append(".")
            continue
        if col_width < roi.shape[1] * 0.05:
            chars.append(".")
            continue

        digit_img = roi[:, col_start:col_end]
        digit = _classify_digit(digit_img)
        if digit:
            chars.append(digit)
        elif len(slots) == 9:
            # Fixed-slot decode requires every digit position; abort if uncertain.
            return None

    if not chars:
        return None

    raw = "".join(chars)
    return _normalize_lcd_string(raw)


def _fixed_digit_slots(roi: np.ndarray) -> list[tuple[int, int]]:
    """Split LCD ROI into 9 slots: 5 integer digits, decimal, 3 fraction digits."""
    width = roi.shape[1]
    # Relative slot widths for NNNNN.DDD
    ratios = [1.0, 1.0, 1.0, 1.0, 1.0, 0.35, 1.0, 1.0, 1.0]
    total = sum(ratios)
    slots: list[tuple[int, int]] = []
    cursor = 0
    for ratio in ratios:
        slot_width = max(int(width * ratio / total), 1)
        end = min(cursor + slot_width, width)
        if end > cursor:
            slots.append((cursor, end))
        cursor = end
    if cursor < width and slots:
        start, _ = slots[-1]
        slots[-1] = (start, width)
    return slots


def _split_columns(roi: np.ndarray) -> list[tuple[int, int]]:
    col_sum = (roi > 0).sum(axis=0)
    columns: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0

    for index, value in enumerate(col_sum):
        if value > 0:
            if start is None:
                start = index
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= 3:
                end = index - gap
                if end - start >= 2:
                    columns.append((start, end))
                start = None
                gap = 0

    if start is not None:
        columns.append((start, len(col_sum)))
    return columns


def _classify_digit(digit_img: np.ndarray) -> str | None:
    height, width = digit_img.shape
    if height < 8 or width < 4:
        return None

    segments = _active_segments(digit_img)
    if not segments:
        return None

    best_digit: str | None = None
    best_score = 0.0
    for digit, expected in _DIGIT_SEGMENTS.items():
        overlap = len(segments & expected)
        precision = overlap / len(segments) if segments else 0
        recall = overlap / len(expected) if expected else 0
        score = (precision + recall) / 2
        if score > best_score:
            best_score = score
            best_digit = digit

    return best_digit if best_score >= 0.62 else None


def _active_segments(digit_img: np.ndarray) -> set[str]:
    height, width = digit_img.shape
    total = max((digit_img > 0).sum(), 1)

    def density(y1: float, y2: float, x1: float, x2: float) -> float:
        top = int(y1 * height)
        bottom = max(int(y2 * height), top + 1)
        left = int(x1 * width)
        right = max(int(x2 * width), left + 1)
        patch = digit_img[top:bottom, left:right]
        if patch.size == 0:
            return 0.0
        return (patch > 0).sum() / patch.size

    segments: set[str] = set()
    checks = {
        "a": (0.02, 0.22, 0.12, 0.88),
        "b": (0.08, 0.52, 0.62, 0.98),
        "c": (0.50, 0.92, 0.62, 0.98),
        "d": (0.78, 0.98, 0.12, 0.88),
        "e": (0.50, 0.92, 0.02, 0.38),
        "f": (0.08, 0.52, 0.02, 0.38),
        "g": (0.42, 0.58, 0.12, 0.88),
    }
    for name, box in checks.items():
        if density(*box) >= 0.18:
            segments.add(name)
    return segments


def _normalize_lcd_string(raw: str) -> str | None:
    cleaned = raw.replace(" ", "")
    if cleaned.count(".") > 1:
        return None

    if "." in cleaned:
        left, _, right = cleaned.partition(".")
    else:
        # Some displays OCR without dot: last 3 digits are decimals.
        if len(cleaned) < 4:
            return None
        left, right = cleaned[:-3], cleaned[-3:]

    if not left.isdigit() or not right.isdigit():
        return None

    return f"{left.zfill(5)[-5:]}.{right.ljust(3, '0')[:3]}"


def _reading_from_tesseract(lcd: np.ndarray) -> str | None:
    if shutil.which("tesseract") is None:
        return None

    import tempfile
    from pathlib import Path

    gray = cv2.cvtColor(lcd, cv2.COLOR_BGR2GRAY) if len(lcd.shape) == 3 else lcd
    mask = np.where(gray < 115, 255, 0).astype(np.uint8)
    upscaled = cv2.resize(mask, None, fx=8, fy=8, interpolation=cv2.INTER_LINEAR)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        cv2.imwrite(str(path), upscaled)
        for psm in (7, 6, 13):
            result = subprocess.run(
                [
                    "tesseract",
                    str(path),
                    "stdout",
                    "--psm",
                    str(psm),
                    "-c",
                    "tessedit_char_whitelist=0123456789.",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            reading = _normalize_tesseract(result.stdout)
            if reading:
                return reading
    finally:
        path.unlink(missing_ok=True)
    return None


def _normalize_tesseract(raw: str) -> str | None:
    cleaned = re.sub(r"[^0-9.]", "", raw)
    match = METER_READING_RE.search(cleaned.replace(",", "."))
    if match:
        return match.group(1).replace(",", ".")
    return _normalize_lcd_string(cleaned)
