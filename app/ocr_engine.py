from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import settings


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float


class OcrEngine:
    """Singleton wrapper around RapidOCR (ONNX) for fast CPU inference."""

    _instance: OcrEngine | None = None

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    @classmethod
    def get(cls) -> OcrEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def read_text(self, image: np.ndarray) -> list[OcrLine]:
        result, _ = self._engine(image, use_angle_cls=settings.ocr_use_angle_cls)
        if not result:
            return []

        lines: list[OcrLine] = []
        for item in result:
            text = str(item[1]).strip()
            if not text:
                continue
            confidence = float(item[2]) if len(item) > 2 else 0.0
            lines.append(OcrLine(text=text, confidence=confidence))
        return lines

    def read_full_text(self, image: np.ndarray) -> str:
        return " ".join(line.text for line in self.read_text(image))
