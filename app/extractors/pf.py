from __future__ import annotations

import numpy as np

from app.decoders import CodeType, decode_codes
from app.extractors.base import BaseMeterExtractor, ExtractionResult
from app.lcd_reading import PF_LCD_CROP, extract_lcd_reading
from app.ocr_engine import OcrEngine
from app.patterns import extract_apf_barcodes, extract_fior_serial, extract_pf_seal
from app.regions import MeterRegions, load_regions
from app.config import settings

_REGIONS_CACHE: dict[str, MeterRegions] | None = None


def _get_regions() -> dict[str, MeterRegions]:
    global _REGIONS_CACHE
    if _REGIONS_CACHE is None:
        _REGIONS_CACHE = load_regions(settings.regions_path)
    return _REGIONS_CACHE


class PFExtractor(BaseMeterExtractor):
    """
    PF (Pietro Fiorentini) meters:
    - Skip all barcodes (including APF… bottom label)
    - meter_serial_number: FIOR + 12 digits
    - metrological_seal_number: 7-digit seal near AzMi / *…*
    - reading: LCD display (optional tesseract on crop)
    """

    meter_type = "pf"
    serial_prefix = "FIOR"
    skip_all_barcodes = True

    def extract(self, image: np.ndarray) -> ExtractionResult:
        regions = _get_regions().get(self.meter_type, MeterRegions())
        codes = decode_codes(image)
        ocr_lines = OcrEngine.get().read_text(image)
        ocr_text = " ".join(line.text for line in ocr_lines)

        result = ExtractionResult(
            meter_type=self.meter_type,
            ocr_text=ocr_text,
            raw_codes=[
                {"data": code.data, "type": code.code_type.value, "symbology": code.symbology}
                for code in codes
            ],
        )

        for code in codes:
            if code.code_type == CodeType.BARCODE:
                result.skipped_barcodes.append(code.data)
            elif code.code_type == CodeType.QRCODE:
                result.qr_data.append(code.data)

        # Serial: QR first, then regex (avoid matching "Fiorentini").
        serial, source, confidence = self._resolve_pf_serial(codes, ocr_text, ocr_lines)
        result.meter_serial_number = serial
        result.serial = serial
        result.serial_source = source
        result.confidence = confidence

        result.metrological_seal_number = extract_pf_seal(ocr_text)

        lcd_crop = regions.reading or PF_LCD_CROP
        lcd = extract_lcd_reading(image, lcd_crop, ocr_fallback_text=ocr_text)
        result.reading = lcd.reading
        result.reading_source = lcd.source

        for apf in extract_apf_barcodes(ocr_text):
            if apf not in result.skipped_barcodes:
                result.skipped_barcodes.append(apf)

        return result

    def _resolve_pf_serial(
        self,
        codes,
        ocr_text: str,
        ocr_lines,
    ) -> tuple[str | None, str | None, float | None]:
        for code in codes:
            if code.code_type != CodeType.QRCODE:
                continue
            serial = extract_fior_serial(code.data)
            if serial:
                return serial, "qr", None

        for line in ocr_lines:
            serial = extract_fior_serial(line.text)
            if serial:
                return serial, "ocr", line.confidence

        serial = extract_fior_serial(ocr_text)
        if serial:
            return serial, "ocr", None

        return None, None, None


class ItronExtractor(BaseMeterExtractor):
    meter_type = "itron"
    serial_prefix = "STS"
    skip_barcode_prefixes = ("ITGL",)
