from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


LABEL_FIELDS = ("image_path", "meter_type", "serial", "reading", "split", "notes")


@dataclass
class LabelRecord:
    image_path: str
    meter_type: str
    serial: str = ""
    reading: str = ""
    split: str = ""
    notes: str = ""

    @property
    def path(self) -> Path:
        return Path(self.image_path)


def load_labels(csv_path: Path, base_dir: Path | None = None) -> list[LabelRecord]:
    base = base_dir or csv_path.parent
    records: list[LabelRecord] = []

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            image_path = row.get("image_path", "").strip()
            meter_type = row.get("meter_type", "").strip().lower()
            if not image_path or not meter_type:
                continue

            path = Path(image_path)
            if not path.is_absolute():
                path = (base / path).resolve()

            records.append(
                LabelRecord(
                    image_path=str(path),
                    meter_type=meter_type,
                    serial=(row.get("serial") or "").strip(),
                    reading=(row.get("reading") or "").strip(),
                    split=(row.get("split") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return records


def save_labels(csv_path: Path, records: list[LabelRecord]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "image_path": record.image_path,
                    "meter_type": record.meter_type,
                    "serial": record.serial,
                    "reading": record.reading,
                    "split": record.split,
                    "notes": record.notes,
                }
            )


def normalize_serial(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def normalize_reading(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip().replace(",", ".")
    digits = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
    if digits.count(".") > 1:
        head, *tail = digits.split(".")
        digits = head + "." + "".join(tail)
    return digits
