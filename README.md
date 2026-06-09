# Meter OCR Service

Fast HTTP service that downloads a meter photo from a URL and extracts serial numbers using type-specific rules.

## Stack (free & open source)

| Component | Role |
|-----------|------|
| [FastAPI](https://fastapi.tiangolo.com/) | HTTP API |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (ONNX) | Fast CPU OCR for printed serials |
| [pyzbar](https://github.com/NaturalHistoryMuseum/pyzbar) + ZBar | QR / barcode decoding |
| OpenCV | Image decode & preprocessing |

RapidOCR uses the same models as PaddleOCR but runs via ONNX Runtime — no Paddle/PyTorch install, good speed on a plain Ubuntu CPU VM.

## Meter rules

| Type | Barcodes | Serial source |
|------|----------|---------------|
| `pf` | All barcodes ignored | QR payload or printed text starting with `FIOR` |
| `itron` | Barcodes starting with `ITGL` ignored | Printed text starting with `STS` |

Add more types in `app/extractors/` by subclassing `BaseMeterExtractor`.

## API

### Health

```bash
curl http://localhost:8080/health
```

### OCR (POST)

```bash
curl -X POST http://localhost:8080/ocr \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/meter.jpg", "meter_type": "pf"}'
```

### OCR (GET)

```bash
curl "http://localhost:8080/ocr?image_url=https%3A%2F%2Fexample.com%2Fmeter.jpg&meter_type=itron"
```

### Response

```json
{
  "success": true,
  "meter_type": "pf",
  "serial": "FIOR12345678",
  "serial_source": "qr",
  "reading": null,
  "qr_data": ["FIOR12345678"],
  "skipped_barcodes": ["0123456789012"],
  "ocr_text": "...",
  "confidence": null,
  "error": null
}
```

Interactive docs: `http://localhost:8080/docs`

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# macOS: brew install zbar
# Ubuntu: sudo apt install libzbar0 libgl1 libglib2.0-0

uvicorn app.main:app --reload --port 8080
```

## Ubuntu deployment

```bash
chmod +x deploy/install-ubuntu.sh
sudo ./deploy/install-ubuntu.sh
```

Or Docker:

```bash
docker build -t meter-ocr .
docker run -p 8080:8080 meter-ocr
```

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `METER_OCR_HOST` | `0.0.0.0` | Bind address |
| `METER_OCR_PORT` | `8080` | Port |
| `METER_OCR_DOWNLOAD_TIMEOUT_SECONDS` | `30` | Image download timeout |
| `METER_OCR_MAX_IMAGE_BYTES` | `15728640` | Max image size (15 MB) |

## Adding a new meter type

1. Create `app/extractors/your_meter.py`:

```python
from app.extractors.base import BaseMeterExtractor

class YourMeterExtractor(BaseMeterExtractor):
    meter_type = "your_meter"
    serial_prefix = "ABC"
    skip_barcode_prefixes = ("XYZ",)
```

2. Register it in `app/extractors/__init__.py`.
3. Add the type to `OcrRequest.meter_type` in `app/models.py`.

For meters with fixed label layouts, override `extract()` and crop regions before OCR (OpenCV `image[y1:y2, x1:x2]`).

## Training with your image dataset

You do **not** need to retrain the OCR neural net to get good results on meter photos. With hundreds of images, the fastest path is:

1. **Organize images** into `data/images/pf/` and `data/images/itron/`
2. **Bootstrap draft labels** with the current rules (then manually fix wrong serials)
3. **Evaluate accuracy** and inspect failures
4. **Tune crop regions / rules** in `data/regions.yaml` and extractors
5. Repeat until accuracy is acceptable

This is much lighter than fine-tuning PaddleOCR (GPU, days of work) and usually enough when meter layouts are consistent.

### 1. Import images

```bash
# Move a folder of PF photos into the dataset layout
python scripts/import_images.py /path/to/pf_photos --meter-type pf

# Or copy instead of move
python scripts/import_images.py /path/to/itron_photos --meter-type itron --copy
```

Expected layout:

```
data/
  images/
    pf/       # hundreds of PF meter photos
    itron/    # hundreds of Itron photos
  labels.csv
  regions.yaml
```

### 2. Bootstrap labels (semi-automated)

Runs the current OCR pipeline on every image and writes a draft CSV. **Review and correct** the `serial` and `reading` columns — treat OCR output as a starting point, not ground truth.

```bash
python scripts/bootstrap_labels.py --images-dir data/images --output data/labels.csv
```

`labels.csv` columns:

| Column | Description |
|--------|-------------|
| `image_path` | Absolute or project-relative path |
| `meter_type` | `pf` or `itron` |
| `serial` | Ground-truth serial (FIOR… / STS…) |
| `reading` | Ground-truth meter reading (optional) |
| `split` | `train`, `val`, or `test` (optional) |
| `notes` | Free text |

### 3. Split train / val / test

```bash
python scripts/split_dataset.py --labels data/labels.csv
```

### 4. Evaluate

```bash
python scripts/evaluate.py --labels data/labels.csv
python scripts/evaluate.py --labels data/labels.csv --split test
```

Outputs accuracy summary plus `data/eval_failures.json` with every missed serial/reading for review.

### 5. Tune crop regions

Edit `data/regions.yaml` using normalized coordinates (0.0–1.0):

```yaml
pf:
  serial_crop: [0.05, 0.55, 0.95, 0.95]
  reading_crop: [0.10, 0.20, 0.90, 0.45]
```

Re-run `evaluate.py` after each change. Cropping the serial/reading area away from barcodes and logos is often the biggest accuracy win.

### Recommended workflow for hundreds of images

```bash
python scripts/import_images.py ~/Downloads/pf_batch --meter-type pf
python scripts/import_images.py ~/Downloads/itron_batch --meter-type itron
python scripts/bootstrap_labels.py
# Open data/labels.csv in Excel/Numbers and fix serial + reading columns
python scripts/split_dataset.py
python scripts/evaluate.py --split test
# Tune data/regions.yaml and extractor rules, then evaluate again
```
