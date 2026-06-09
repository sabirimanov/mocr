from __future__ import annotations

from typing import Type

import numpy as np

from app.extractors.base import ExtractionResult, MeterExtractor
from app.extractors.pf import ItronExtractor, PFExtractor

_EXTRACTORS: dict[str, Type[MeterExtractor]] = {
    "pf": PFExtractor,
    "itron": ItronExtractor,
}


def supported_meter_types() -> list[str]:
    return sorted(_EXTRACTORS.keys())


def extract_meter_data(image: np.ndarray, meter_type: str) -> ExtractionResult:
    key = meter_type.strip().lower()
    extractor_cls = _EXTRACTORS.get(key)
    if extractor_cls is None:
        supported = ", ".join(supported_meter_types())
        raise ValueError(f"Unknown meter type '{meter_type}'. Supported: {supported}")
    return extractor_cls().extract(image)
