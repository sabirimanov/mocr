#!/usr/bin/env python3
"""Evaluate OCR extraction accuracy against labels.csv."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dataset import LabelRecord, load_labels, normalize_reading, normalize_serial
from app.extractors import extract_meter_data
from app.image_utils import load_image_from_path


@dataclass
class RowResult:
    image_path: str
    meter_type: str
    expected_serial: str
    predicted_serial: str | None
    serial_ok: bool
    expected_reading: str
    predicted_reading: str | None
    reading_ok: bool
    serial_source: str | None
    error: str | None = None


def evaluate_records(records: list[LabelRecord]) -> tuple[list[RowResult], dict]:
    results: list[RowResult] = []
    totals = defaultdict(int)

    for record in records:
        totals["rows"] += 1
        totals[f"type:{record.meter_type}"] += 1

        expected_serial = normalize_serial(record.serial)
        expected_reading = normalize_reading(record.reading)
        if expected_serial:
            totals["serial_labeled"] += 1
        if expected_reading:
            totals["reading_labeled"] += 1

        try:
            image = load_image_from_path(record.path)
            prediction = extract_meter_data(image, record.meter_type)
            predicted_serial = normalize_serial(prediction.serial)
            predicted_reading = normalize_reading(prediction.reading)
            serial_ok = not expected_serial or predicted_serial == expected_serial
            reading_ok = not expected_reading or predicted_reading == expected_reading
            error = None
        except Exception as exc:  # noqa: BLE001 - report per-image failures in batch eval
            predicted_serial = None
            predicted_reading = None
            serial_ok = not expected_serial
            reading_ok = not expected_reading
            prediction = None
            error = str(exc)

        if expected_serial:
            totals["serial_checked"] += 1
            totals["serial_correct"] += int(serial_ok)
        if expected_reading:
            totals["reading_checked"] += 1
            totals["reading_correct"] += int(reading_ok)

        results.append(
            RowResult(
                image_path=record.image_path,
                meter_type=record.meter_type,
                expected_serial=expected_serial,
                predicted_serial=predicted_serial or None,
                serial_ok=serial_ok,
                expected_reading=expected_reading,
                predicted_reading=predicted_reading or None,
                reading_ok=reading_ok,
                serial_source=getattr(prediction, "serial_source", None),
                error=error,
            )
        )

    summary = {
        "rows": totals["rows"],
        "serial_accuracy": _ratio(totals["serial_correct"], totals["serial_checked"]),
        "reading_accuracy": _ratio(totals["reading_correct"], totals["reading_checked"]),
        "serial_labeled": totals["serial_labeled"],
        "reading_labeled": totals["reading_labeled"],
        "failures": sum(1 for row in results if not row.serial_ok or not row.reading_ok),
        "by_meter_type": _by_meter_type(results),
    }
    return results, summary


def _ratio(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(correct / total, 4)


def _by_meter_type(results: list[RowResult]) -> dict[str, dict]:
    grouped: dict[str, list[RowResult]] = defaultdict(list)
    for row in results:
        grouped[row.meter_type].append(row)

    stats: dict[str, dict] = {}
    for meter_type, rows in grouped.items():
        serial_rows = [row for row in rows if row.expected_serial]
        reading_rows = [row for row in rows if row.expected_reading]
        stats[meter_type] = {
            "count": len(rows),
            "serial_accuracy": _ratio(
                sum(1 for row in serial_rows if row.serial_ok),
                len(serial_rows),
            ),
            "reading_accuracy": _ratio(
                sum(1 for row in reading_rows if row.reading_ok),
                len(reading_rows),
            ),
            "failures": sum(1 for row in rows if not row.serial_ok or not row.reading_ok),
        }
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("data/labels.csv"),
        help="Ground-truth CSV",
    )
    parser.add_argument(
        "--split",
        default="",
        help="Optional split filter: train, val, or test",
    )
    parser.add_argument(
        "--failures",
        type=Path,
        default=Path("data/eval_failures.json"),
        help="Write failed rows as JSON for review",
    )
    args = parser.parse_args()

    records = load_labels(args.labels)
    if args.split:
        records = [record for record in records if record.split == args.split]

    if not records:
        raise SystemExit(f"No records found in {args.labels}")

    results, summary = evaluate_records(records)
    print(json.dumps(summary, indent=2))

    failures = [
        asdict(row)
        for row in results
        if (row.expected_serial and not row.serial_ok)
        or (row.expected_reading and not row.reading_ok)
        or row.error
    ]
    args.failures.parent.mkdir(parents=True, exist_ok=True)
    args.failures.write_text(json.dumps(failures, indent=2), encoding="utf-8")
    print(f"\nFailures written to {args.failures} ({len(failures)} rows)")


if __name__ == "__main__":
    main()
