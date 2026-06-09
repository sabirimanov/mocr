from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from app.patterns import METER_READING_RE, extract_meter_reading
from app.regions import CropRegion

PF_LCD_CROP = CropRegion(0.34, 0.185, 0.53, 0.268)
PF_LCD_DIGITS_CROP = CropRegion(0.355, 0.190, 0.515, 0.234)


@dataclass(frozen=True)
class LcdReadingResult:
    reading: str | None
    source: str | None = None


@dataclass(frozen=True)
class _DecodeCandidate:
    reading: str
    score: float


def extract_lcd_reading(
    image: np.ndarray,
    crop: CropRegion | None = None,
    ocr_fallback_text: str | None = None,
) -> LcdReadingResult:
    region = crop or PF_LCD_CROP
    lcd = region.apply(image)
    if lcd.size == 0:
        return LcdReadingResult(None, None)

    digits_crop = PF_LCD_DIGITS_CROP.apply(image)
    gray = _to_gray(digits_crop if digits_crop.size else lcd)
    gray = gray[: max(int(gray.shape[0] * 0.62), 1), :]

    if not _lcd_is_active(gray):
        return LcdReadingResult(None, None)

    candidate = _best_template_decode(gray)
    if candidate and _is_plausible_reading(candidate.reading, candidate.score):
        return LcdReadingResult(candidate.reading, "lcd_template")

    reading = _reading_from_tesseract(_to_bgr(gray))
    if reading and _is_plausible_reading(reading):
        return LcdReadingResult(reading, "lcd_tesseract")

    if ocr_fallback_text:
        reading = extract_meter_reading(ocr_fallback_text)
        if reading and _is_plausible_reading(reading):
            return LcdReadingResult(reading, "ocr")

    return LcdReadingResult(None, None)


def _to_gray(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _to_bgr(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        return image
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def _lcd_is_active(gray: np.ndarray) -> bool:
    if gray.size == 0 or float(gray.std()) < 12.0:
        return False

    binary = _binarize_digits(gray)
    dark_ratio = (binary > 0).sum() / binary.size
    if dark_ratio < 0.06:
        return False

    coords = cv2.findNonZero(binary)
    if coords is None:
        return False

    _, _, width, height = cv2.boundingRect(coords)
    if height < 6 or width < 20:
        return False

    # Off/ghost LCD: faint all-segment pattern, very uniform fill across slots.
    if dark_ratio > 0.40:
        return False

    candidate = _best_template_decode(gray)
    if candidate and _is_ghost_reading(candidate.reading):
        return False

    return True


def _binarize_digits(gray: np.ndarray) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    _, binary = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _best_template_decode(gray: np.ndarray) -> _DecodeCandidate | None:
    binary = _binarize_digits(gray)
    best: _DecodeCandidate | None = None

    for scale in (8, 10, 12):
        upscaled = cv2.resize(binary, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        coords = cv2.findNonZero(upscaled)
        if coords is None:
            continue
        x, y, width, height = cv2.boundingRect(coords)
        roi = upscaled[y : y + height, x : x + width]

        for dot_ratio in (0.58, 0.60, 0.62, 0.64):
            reading, score = _decode_roi(roi, dot_ratio)
            if not reading:
                continue
            candidate = _DecodeCandidate(reading, score)
            if best is None or candidate.score > best.score:
                best = candidate

    return best


def _decode_roi(roi: np.ndarray, dot_ratio: float) -> tuple[str | None, float]:
    templates = _digit_templates()
    slots = _decimal_slots(roi.shape[1], dot_ratio)
    chars: list[str] = []
    scores: list[float] = []

    for index, (col_start, col_end) in enumerate(slots):
        if index == 5:
            chars.append(".")
            continue

        patch = roi[:, col_start:col_end]
        if patch.size == 0:
            return None, 0.0

        fill = (patch > 0).sum() / patch.size
        if fill < 0.03:
            return None, 0.0

        char, score = _match_digit(patch, templates, prefer_zero=index < 5)
        if char is None:
            return None, 0.0
        chars.append(char)
        scores.append(score)

    reading = _normalize_lcd_string("".join(chars))
    if not reading:
        return None, 0.0
    return reading, sum(scores) / len(scores)


def _decimal_slots(width: int, dot_ratio: float) -> list[tuple[int, int]]:
    dot_x = int(width * dot_ratio)
    gap = max(int(width * 0.03), 2)
    frac_base = min(dot_x + gap, width)
    slots: list[tuple[int, int]] = []

    for index in range(5):
        start = int(index * dot_x / 5)
        end = int((index + 1) * dot_x / 5)
        slots.append((start, max(end, start + 1)))

    slots.append((dot_x, min(dot_x + gap, width)))

    frac_width = max(width - frac_base, 1)
    for index in range(3):
        start = frac_base + int(index * frac_width / 3)
        end = frac_base + int((index + 1) * frac_width / 3)
        slots.append((start, min(end, width)))

    return slots


def _match_digit(
    patch: np.ndarray,
    templates: dict[str, np.ndarray],
    prefer_zero: bool,
) -> tuple[str | None, float]:
    if patch.size == 0:
        return None, 0.0

    height, width = patch.shape
    center = width // 2
    half = max(width // 2, 4)

    ranked_best: list[tuple[str, float]] = []
    for shift in range(-8, 9, 2):
        left = max(0, center - half + shift)
        right = min(width, center + half + shift)
        if right - left < 4:
            continue
        ranked_best.extend(_score_patch(patch[:, left:right], templates))

    if not ranked_best:
        ranked_best = _score_patch(patch, templates)

    ranked: list[tuple[str, float]] = []
    for char, score in ranked_best:
        existing = next((index for index, item in enumerate(ranked) if item[0] == char), None)
        if existing is None:
            ranked.append((char, score))
        elif score > ranked[existing][1]:
            ranked[existing] = (char, score)

    ranked.sort(key=lambda item: item[1], reverse=True)
    best_char, best_score = ranked[0]

    if prefer_zero:
        zero_score = next(score for char, score in ranked if char == "0")
        if zero_score >= 0.14:
            return "0", zero_score
        if best_char in {"6", "8"} and best_score - zero_score < 0.06:
            return "0", zero_score

    if best_score < 0.08:
        return None, 0.0
    return best_char, best_score


def _score_patch(patch: np.ndarray, templates: dict[str, np.ndarray]) -> list[tuple[str, float]]:
    normalized = cv2.resize(patch, (32, 56), interpolation=cv2.INTER_NEAREST)
    pixels = (normalized > 127).astype(np.uint8)
    scores: list[tuple[str, float]] = []
    for char, template in templates.items():
        template_pixels = (template > 0).astype(np.uint8)
        intersection = np.logical_and(pixels, template_pixels).sum()
        union = np.logical_or(pixels, template_pixels).sum()
        score = intersection / union if union else 0.0
        scores.append((char, score))
    return scores


@lru_cache(maxsize=1)
def _digit_templates() -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    for char in "0123456789":
        templates[char] = _render_7segment(char)
    return templates


def _render_7segment(char: str) -> np.ndarray:
    segments = {
        "0": "abcdef",
        "1": "bc",
        "2": "abdeg",
        "3": "abcdg",
        "4": "bcfg",
        "5": "acdfg",
        "6": "acdefg",
        "7": "abc",
        "8": "abcdefg",
        "9": "abcdfg",
    }.get(char, "")

    canvas = np.zeros((56, 32), dtype=np.uint8)
    thickness = 4

    def draw(segment: str) -> None:
        if segment == "a":
            cv2.line(canvas, (5, 4), (27, 4), 255, thickness)
        elif segment == "b":
            cv2.line(canvas, (28, 5), (28, 25), 255, thickness)
        elif segment == "c":
            cv2.line(canvas, (28, 29), (28, 49), 255, thickness)
        elif segment == "d":
            cv2.line(canvas, (5, 51), (27, 51), 255, thickness)
        elif segment == "e":
            cv2.line(canvas, (4, 29), (4, 49), 255, thickness)
        elif segment == "f":
            cv2.line(canvas, (4, 5), (4, 25), 255, thickness)
        elif segment == "g":
            cv2.line(canvas, (5, 27), (27, 27), 255, thickness)

    for segment in segments:
        draw(segment)
    return canvas


def _normalize_lcd_string(raw: str) -> str | None:
    cleaned = raw.replace(" ", "")
    if cleaned.count(".") > 1:
        return None

    if "." in cleaned:
        left, _, right = cleaned.partition(".")
    else:
        if len(cleaned) < 4:
            return None
        left, right = cleaned[:-3], cleaned[-3:]

    if not left.isdigit() or not right.isdigit():
        return None

    return f"{left.zfill(5)[-5:]}.{right.ljust(3, '0')[:3]}"


def _is_ghost_reading(reading: str) -> bool:
    integer, _, fraction = reading.partition(".")
    if integer == "88888" or fraction == "888":
        return True
    if len(integer) == 5 and integer.count("8") >= 4 and fraction.count("8") >= 2:
        return True
    return False


def _is_plausible_reading(reading: str, decode_score: float = 1.0) -> bool:
    if not reading or _is_ghost_reading(reading):
        return False
    if decode_score < 0.16:
        return False
    return True


def _reading_from_tesseract(lcd: np.ndarray) -> str | None:
    if shutil.which("tesseract") is None:
        return None

    import tempfile
    from pathlib import Path

    binary = _binarize_digits(_to_gray(lcd))
    upscaled = cv2.resize(binary, None, fx=8, fy=8, interpolation=cv2.INTER_LINEAR)

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
