from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.decoders import CodeType, DecodedCode, decode_codes
from app.image_utils import extract_pattern_matches, normalize_text
from app.ocr_engine import OcrEngine, OcrLine
from app.regions import MeterRegions, load_regions
from app.config import settings

_REGIONS_CACHE: dict[str, MeterRegions] | None = None


def _get_regions() -> dict[str, MeterRegions]:
    global _REGIONS_CACHE
    if _REGIONS_CACHE is None:
        _REGIONS_CACHE = load_regions(settings.regions_path)
    return _REGIONS_CACHE


@dataclass
class ExtractionResult:
    meter_type: str
    serial: str | None = None
    meter_serial_number: str | None = None
    metrological_seal_number: str | None = None
    serial_source: str | None = None
    reading: str | None = None
    reading_source: str | None = None
    qr_data: list[str] = field(default_factory=list)
    skipped_barcodes: list[str] = field(default_factory=list)
    ocr_text: str | None = None
    raw_codes: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "meter_type": self.meter_type,
            "serial": self.serial or self.meter_serial_number,
            "meter_serial_number": self.meter_serial_number or self.serial,
            "metrological_seal_number": self.metrological_seal_number,
            "serial_source": self.serial_source,
            "reading": self.reading,
            "reading_source": self.reading_source,
            "qr_data": self.qr_data,
            "skipped_barcodes": self.skipped_barcodes,
            "ocr_text": self.ocr_text,
            "raw_codes": self.raw_codes,
            "confidence": self.confidence,
        }


class MeterExtractor(ABC):
    meter_type: str

    @abstractmethod
    def extract(self, image: np.ndarray) -> ExtractionResult:
        raise NotImplementedError


class BaseMeterExtractor(MeterExtractor):
    """Shared OCR + barcode pipeline with meter-specific filtering hooks."""

    serial_prefix: str
    skip_barcode_prefixes: tuple[str, ...] = ()
    skip_all_barcodes: bool = False
    reading_pattern: str | None = None

    def extract(self, image: np.ndarray) -> ExtractionResult:
        regions = _get_regions().get(self.meter_type, MeterRegions())
        serial_image = regions.serial.apply(image) if regions.serial else image
        reading_image = regions.reading.apply(image) if regions.reading else image

        codes = decode_codes(image)
        serial_lines = OcrEngine.get().read_text(serial_image)
        reading_lines = (
            OcrEngine.get().read_text(reading_image)
            if regions.reading and reading_image is not serial_image
            else serial_lines
        )
        ocr_text = " ".join(line.text for line in serial_lines)
        reading_text = " ".join(line.text for line in reading_lines)

        result = ExtractionResult(
            meter_type=self.meter_type,
            ocr_text=ocr_text,
            raw_codes=[
                {"data": code.data, "type": code.code_type.value, "symbology": code.symbology}
                for code in codes
            ],
        )

        for code in codes:
            if code.code_type == CodeType.BARCODE and self._should_skip_barcode(code.data):
                result.skipped_barcodes.append(code.data)
                continue
            if code.code_type == CodeType.QRCODE:
                result.qr_data.append(code.data)

        serial, source, confidence = self._resolve_serial(codes, serial_lines, ocr_text)
        result.serial = serial
        result.serial_source = source
        result.confidence = confidence
        result.reading = self._extract_reading(reading_text if regions.reading else ocr_text)
        return result

    def _should_skip_barcode(self, data: str) -> bool:
        if self.skip_all_barcodes:
            return True
        normalized = normalize_text(data)
        return any(normalized.startswith(prefix) for prefix in self.skip_barcode_prefixes)

    def _resolve_serial(
        self,
        codes: list[DecodedCode],
        ocr_lines: list[OcrLine],
        ocr_text: str,
    ) -> tuple[str | None, str | None, float | None]:
        # 1. QR codes often carry the authoritative serial on PF meters.
        for code in codes:
            if code.code_type != CodeType.QRCODE:
                continue
            serial = self._serial_from_text(code.data)
            if serial:
                return serial, "qr", None

        # 2. Printed serial via OCR.
        for line in ocr_lines:
            matches = extract_pattern_matches(line.text, self.serial_prefix)
            if matches:
                return matches[0], "ocr", line.confidence

        matches = extract_pattern_matches(ocr_text, self.serial_prefix)
        if matches:
            return matches[0], "ocr", None

        return None, None, None

    def _serial_from_text(self, text: str) -> str | None:
        matches = extract_pattern_matches(text, self.serial_prefix)
        return matches[0] if matches else None

    def _extract_reading(self, ocr_text: str) -> str | None:
        if not self.reading_pattern:
            return None
        import re

        match = re.search(self.reading_pattern, ocr_text, re.IGNORECASE)
        return match.group(0) if match else None
