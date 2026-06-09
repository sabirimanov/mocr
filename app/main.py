from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.config import settings
from app.extractors import extract_meter_data, supported_meter_types
from app.image_utils import fetch_image
from app.models import OcrRequest, OcrResponse
from app.ocr_engine import OcrEngine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm up OCR model at startup so first request is fast.
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
    return await _process(str(request.image_url), request.meter_type)


@app.get("/ocr", response_model=OcrResponse)
async def ocr_from_query(
    image_url: str = Query(..., description="Public URL of the meter image"),
    meter_type: str = Query(..., description="pf or itron"),
) -> OcrResponse:
    return await _process(image_url, meter_type)


async def _process(image_url: str, meter_type: str) -> OcrResponse:
    image = await fetch_image(image_url)

    try:
        result = extract_meter_data(image, meter_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OcrResponse(
        success=result.serial is not None,
        meter_type=result.meter_type,
        serial=result.serial,
        serial_source=result.serial_source,
        reading=result.reading,
        qr_data=result.qr_data,
        skipped_barcodes=result.skipped_barcodes,
        ocr_text=result.ocr_text,
        confidence=result.confidence,
        error=None if result.serial else "Serial number not found",
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
