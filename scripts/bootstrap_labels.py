#!/usr/bin/env python3
"""Scan image folders and create a draft labels.csv from current OCR rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dataset import LabelRecord, save_labels
from app.extractors import extract_meter_data, supported_meter_types
from app.image_utils import load_image_from_path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def discover_images(root: Path) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    supported = set(supported_meter_types())

    for meter_type in supported:
        type_dir = root / meter_type
        if not type_dir.is_dir():
            continue
        for path in sorted(type_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                found.append((path.resolve(), meter_type))

    if found:
        return found

    # Flat folder: infer meter type from parent directory name when possible.
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        meter_type = path.parent.name.lower()
        if meter_type not in supported:
            continue
        found.append((path.resolve(), meter_type))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("data/images"),
        help="Root folder containing pf/, itron/, etc.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/labels.csv"),
        help="CSV file to write",
    )
    parser.add_argument(
        "--split",
        default="",
        help="Optional split tag written to every row (train/val/test)",
    )
    args = parser.parse_args()

    images = discover_images(args.images_dir)
    if not images:
        supported = ", ".join(supported_meter_types())
        raise SystemExit(
            f"No images found under {args.images_dir}. "
            f"Expected subfolders like data/images/pf/ and data/images/itron/ "
            f"(supported types: {supported})."
        )

    records: list[LabelRecord] = []
    for index, (path, meter_type) in enumerate(images, start=1):
        image = load_image_from_path(path)
        result = extract_meter_data(image, meter_type)
        records.append(
            LabelRecord(
                image_path=str(path),
                meter_type=meter_type,
                serial=result.serial or "",
                reading=result.reading or "",
                split=args.split,
                notes="auto_bootstrap",
            )
        )
        print(f"[{index}/{len(images)}] {path.name}: serial={result.serial!r}")

    save_labels(args.output, records)
    print(f"\nWrote {len(records)} rows to {args.output}")
    print("Review and correct serial/reading values, then run scripts/evaluate.py")


if __name__ == "__main__":
    main()
