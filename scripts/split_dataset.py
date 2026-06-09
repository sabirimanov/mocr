#!/usr/bin/env python3
"""Split labels.csv into train/val/test subsets."""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dataset import load_labels, save_labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if abs(args.train + args.val + (1.0 - args.train - args.val) - 1.0) > 1e-6:
        raise SystemExit("train + val + test must equal 1.0")

    test_ratio = 1.0 - args.train - args.val
    records = load_labels(args.labels)
    grouped: dict[str, list] = defaultdict(list)
    for record in records:
        grouped[record.meter_type].append(record)

    rng = random.Random(args.seed)
    for meter_records in grouped.values():
        rng.shuffle(meter_records)
        total = len(meter_records)
        train_end = int(total * args.train)
        val_end = train_end + int(total * args.val)
        for index, record in enumerate(meter_records):
            if index < train_end:
                record.split = "train"
            elif index < val_end:
                record.split = "val"
            else:
                record.split = "test"

    save_labels(args.labels, records)
    print(
        f"Updated {args.labels}: "
        f"train={sum(r.split == 'train' for r in records)}, "
        f"val={sum(r.split == 'val' for r in records)}, "
        f"test={sum(r.split == 'test' for r in records)} "
        f"(test ratio={test_ratio:.2f})"
    )


if __name__ == "__main__":
    main()
