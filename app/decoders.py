from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class CodeType(str, Enum):
    QRCODE = "QRCODE"
    BARCODE = "BARCODE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DecodedCode:
    data: str
    code_type: CodeType
    symbology: str


def decode_codes(image: np.ndarray) -> list[DecodedCode]:
    """Decode all QR codes and barcodes in an image."""
    from pyzbar.pyzbar import decode as pyzbar_decode

    gray = _to_grayscale(image)
    results: list[DecodedCode] = []

    for symbol in pyzbar_decode(gray):
        raw = symbol.data.decode("utf-8", errors="replace").strip()
        if not raw:
            continue
        symbology = symbol.type or "UNKNOWN"
        code_type = CodeType.QRCODE if symbology == "QRCODE" else CodeType.BARCODE
        results.append(DecodedCode(data=raw, code_type=code_type, symbology=symbology))

    return results


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    import cv2

    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
