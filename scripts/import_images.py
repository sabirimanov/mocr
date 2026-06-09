#!/usr/bin/env python3
"""Import a flat folder of images into data/images/<meter_type>/ layout."""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Folder containing raw images")
    parser.add_argument(
        "--meter-type",
        required=True,
        help="Target meter type folder name, e.g. pf or itron",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("data/images"),
        help="Dataset root (creates data/images/<meter_type>/)",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("data/labels.csv"),
        help="Optional CSV to append rows without serial/reading yet",
    )
    parser.add_argument("--copy", action="store_true", help="Copy instead of move")
    args = parser.parse_args()

    target_dir = args.dest / args.meter_type.lower()
    target_dir.mkdir(parents=True, exist_ok=True)

    imported: list[tuple[str, str]] = []
    for path in sorted(args.source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        destination = target_dir / path.name
        stem, suffix = destination.stem, destination.suffix
        counter = 1
        while destination.exists():
            destination = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        if args.copy:
            shutil.copy2(path, destination)
        else:
            shutil.move(path, destination)
        imported.append((str(destination.resolve()), args.meter_type.lower()))
        print(f"Imported {path.name} -> {destination}")

    if not imported:
        raise SystemExit(f"No images found in {args.source}")

    if args.labels:
        write_header = not args.labels.exists()
        args.labels.parent.mkdir(parents=True, exist_ok=True)
        with args.labels.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if write_header:
                writer.writerow(["image_path", "meter_type", "serial", "reading", "split", "notes"])
            for image_path, meter_type in imported:
                writer.writerow([image_path, meter_type, "", "", "", "imported"])

    print(f"\nImported {len(imported)} images into {target_dir}")


if __name__ == "__main__":
    main()
