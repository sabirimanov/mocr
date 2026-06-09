FROM python:3.12-slim-bookworm

# libzbar0: pyzbar barcode/QR decoding
# libgl1 + libglib2.0-0: opencv runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV METER_OCR_HOST=0.0.0.0
ENV METER_OCR_PORT=8080

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
