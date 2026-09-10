import hashlib

from suwisa.features.receipts.models import OcrEngine, ReceiptError, ReceiptScan
from suwisa.features.receipts.parser import parse_receipt


class ReceiptService:
    def __init__(self, engine: OcrEngine, max_bytes: int = 10 * 1024 * 1024):
        self.engine = engine
        self.max_bytes = max_bytes

    def scan(self, image: bytes) -> ReceiptScan:
        if not image or len(image) > self.max_bytes:
            raise ReceiptError("ไฟล์ว่างหรือใหญ่เกินกำหนด กรุณาส่งภาพที่เล็กลง")
        document = self.engine.read(image)
        return ReceiptScan(
            parse_receipt(document), hashlib.sha256(image).hexdigest(), document.confidence
        )
