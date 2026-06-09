from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml


@dataclass(frozen=True)
class CropRegion:
    x1: float
    y1: float
    x2: float
    y2: float

    def apply(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        left = max(0, int(self.x1 * width))
        top = max(0, int(self.y1 * height))
        right = min(width, int(self.x2 * width))
        bottom = min(height, int(self.y2 * height))
        if right <= left or bottom <= top:
            return image
        return image[top:bottom, left:right]


@dataclass(frozen=True)
class MeterRegions:
    serial: CropRegion | None = None
    reading: CropRegion | None = None


def _parse_region(raw: list[float] | None) -> CropRegion | None:
    if not raw or len(raw) != 4:
        return None
    x1, y1, x2, y2 = (float(v) for v in raw)
    return CropRegion(x1=x1, y1=y1, x2=x2, y2=y2)


def load_regions(config_path: Path) -> dict[str, MeterRegions]:
    if not config_path.exists():
        return {}

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    regions: dict[str, MeterRegions] = {}
    for meter_type, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        regions[str(meter_type).lower()] = MeterRegions(
            serial=_parse_region(cfg.get("serial_crop")),
            reading=_parse_region(cfg.get("reading_crop")),
        )
    return regions
