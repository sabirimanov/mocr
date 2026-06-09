from __future__ import annotations

from pathlib import Path

import httpx
import numpy as np
from fastapi import HTTPException

from app.config import settings


async def load_image_source(source: str) -> np.ndarray:
    """Load image from http(s) URL or a server-local file path."""
    source = source.strip()
    if source.startswith(("http://", "https://")):
        return await fetch_image(source)
    return load_image_from_path(source, check_allowed=True)


async def fetch_image(url: str) -> np.ndarray:
    """Download an image URL and return it as a BGR numpy array."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.download_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to download image: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"URL did not return an image (content-type: {content_type})",
        )

    if len(response.content) > settings.max_image_bytes:
        raise HTTPException(status_code=400, detail="Image exceeds maximum allowed size")

    image = _decode_image_bytes(response.content)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode image data")
    return image


def _decode_image_bytes(data: bytes) -> np.ndarray | None:
    import cv2

    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    return image


def load_image_from_path(path: Path | str, *, check_allowed: bool = False) -> np.ndarray:
    import cv2

    file_path = Path(path).expanduser()
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()
    else:
        file_path = file_path.resolve()

    if check_allowed and not _is_path_allowed(file_path):
        raise HTTPException(
            status_code=403,
            detail=f"Image path not allowed: {file_path}. "
            f"Configure METER_OCR_ALLOWED_IMAGE_DIRS.",
        )

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {file_path}")

    if file_path.stat().st_size > settings.max_image_bytes:
        raise HTTPException(status_code=400, detail="Image exceeds maximum allowed size")

    image = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {file_path}")
    return image


def _allowed_roots() -> list[Path]:
    roots: list[Path] = []
    for entry in settings.allowed_image_dirs.split(","):
        entry = entry.strip()
        if not entry:
            continue
        root = Path(entry).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        else:
            root = root.resolve()
        roots.append(root)
    return roots


def _is_path_allowed(file_path: Path) -> bool:
    roots = _allowed_roots()
    if not roots:
        return False
    return any(file_path == root or root in file_path.parents for root in roots)


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip().upper()


def extract_pattern_matches(text: str, prefix: str) -> list[str]:
    """Find tokens in OCR text that start with the given prefix."""
    normalized = normalize_text(text)
    matches: list[str] = []
    for token in normalized.replace(",", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if cleaned.startswith(prefix):
            matches.append(cleaned)
    return matches
