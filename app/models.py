from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class OcrRequest(BaseModel):
    meter_type: Literal["pf", "itron"] = Field(
        description="Meter manufacturer/type; selects extraction rules"
    )
    image_url: HttpUrl | None = Field(
        default=None,
        description="Public http(s) URL of the meter image",
    )
    image_path: str | None = Field(
        default=None,
        description="Server-local file path (must be under METER_OCR_ALLOWED_IMAGE_DIRS)",
    )

    @model_validator(mode="after")
    def require_one_image_source(self) -> OcrRequest:
        if bool(self.image_url) == bool(self.image_path):
            raise ValueError("Provide exactly one of image_url or image_path")
        return self


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
