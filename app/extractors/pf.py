from __future__ import annotations

from app.extractors.base import BaseMeterExtractor


class PFExtractor(BaseMeterExtractor):
    """
    PF meters:
    - Ignore barcode regions (generic barcodes on label)
    - Serial from QR payload or printed text starting with FIOR
    """

    meter_type = "pf"
    serial_prefix = "FIOR"
    skip_all_barcodes = True


class ItronExtractor(BaseMeterExtractor):
    """
    Itron meters:
    - Skip ITGL barcodes
    - Serial from printed text starting with STS
    """

    meter_type = "itron"
    serial_prefix = "STS"
    skip_barcode_prefixes = ("ITGL",)
