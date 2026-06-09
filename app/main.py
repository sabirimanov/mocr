from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile

from app.config import settings
from app.extractors import extract_meter_data, supported_meter_types
from app.image_utils import _decode_image_bytes, load_image_source
from app.models import OcrRequest, OcrResponse
from app.ocr_engine import OcrEngine


@asynccontextmanager
async def lifespan(_: FastAPI):
    OcrEngine.get()
    yield


app = FastAPI(
    title="Meter OCR Service",
    description="Extract serial numbers and readings from utility meter photos",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meter-types")
async def meter_types() -> dict[str, list[str]]:
    return {"meter_types": supported_meter_types()}


@app.post("/ocr", response_model=OcrResponse)
async def ocr_from_body(request: OcrRequest) -> OcrResponse:
    source = str(request.image_url) if request.image_url else request.image_path
    assert source is not None
    return await _process(source, request.meter_type)


@app.post("/ocr/upload", response_model=OcrResponse)
async def ocr_from_upload(
    meter_type: str = Form(..., description="pf or itron"),
    file: UploadFile = File(..., description="Meter photo"),
) -> OcrResponse:
    content_type = file.content_type or ""
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Expected an image file, got {content_type}")

    data = await file.read()
    if len(data) > settings.max_image_bytes:
        raise HTTPException(status_code=400, detail="Image exceeds maximum allowed size")

    image = _decode_image_bytes(data)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    return _build_response(extract_meter_data(image, meter_type))


@app.get("/ocr", response_model=OcrResponse)
async def ocr_from_query(
    meter_type: str = Query(..., description="pf or itron"),
    image_url: str | None = Query(default=None, description="Public URL of the meter image"),
    image_path: str | None = Query(default=None, description="Server-local image path"),
) -> OcrResponse:
    if bool(image_url) == bool(image_path):
        raise HTTPException(status_code=400, detail="Provide exactly one of image_url or image_path")
    source = image_url or image_path
    assert source is not None
    return await _process(source, meter_type)


async def _process(source: str, meter_type: str) -> OcrResponse:
    image = await load_image_source(source)

    try:
        result = extract_meter_data(image, meter_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _build_response(result)


def _build_response(result) -> OcrResponse:
    serial = result.meter_serial_number or result.serial
    return OcrResponse(
        success=serial is not None,
        meter_type=result.meter_type,
        serial=serial,
        meter_serial_number=serial,
        metrological_seal_number=result.metrological_seal_number,
        serial_source=result.serial_source,
        reading=result.reading,
        reading_source=result.reading_source,
        qr_data=result.qr_data,
        skipped_barcodes=result.skipped_barcodes,
        ocr_text=result.ocr_text,
        confidence=result.confidence,
        error=None if serial else "Serial number not found",
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
