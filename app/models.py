from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class OcrRequest(BaseModel):
    image_url: HttpUrl
    meter_type: Literal["pf", "itron"] = Field(
        description="Meter manufacturer/type; selects extraction rules"
    )


class OcrResponse(BaseModel):
    success: bool
    meter_type: str
    serial: str | None = Field(
        default=None,
        description="Deprecated alias for meter_serial_number",
    )
    meter_serial_number: str | None = None
    metrological_seal_number: str | None = None
    serial_source: str | None = Field(
        default=None,
        description="Where serial was found: qr, ocr",
    )
    reading: str | None = None
    reading_source: str | None = Field(
        default=None,
        description="Where reading was found: lcd, ocr",
    )
    qr_data: list[str] = Field(default_factory=list)
    skipped_barcodes: list[str] = Field(default_factory=list)
    ocr_text: str | None = None
    confidence: float | None = None
    error: str | None = None
