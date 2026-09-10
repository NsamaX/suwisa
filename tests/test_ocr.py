import os
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont

from suwisa.features.receipts.models import OcrDocument, ReceiptError
from suwisa.features.receipts.service import ReceiptService
from suwisa.infrastructure.ocr.tesseract import TesseractEngine


class FakeEngine:
    def read(self, image):
        return OcrDocument("TOTAL 88.50 THB", 99)


def test_empty_and_oversized_input_is_rejected_before_ocr():
    service = ReceiptService(FakeEngine(), max_bytes=4)
    for value in [b"", b"12345"]:
        with pytest.raises(ReceiptError):
            service.scan(value)


def test_hash_is_stable():
    service = ReceiptService(FakeEngine())
    assert service.scan(b"synthetic").image_sha256 == service.scan(b"synthetic").image_sha256


@pytest.fixture
def engine():
    if os.getenv("RUN_OCR_TESTS") != "1":
        pytest.skip("Set RUN_OCR_TESTS=1 with Tesseract tha+eng installed")
    return TesseractEngine()


@pytest.mark.integration
def test_real_ocr_on_generated_receipt(engine):
    image = Image.new("RGB", (1000, 650), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except OSError:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 42)
    draw.multiline_text(
        (60, 60),
        "EXAMPLE SHOP\n07/09/2026 09:15\nSUBTOTAL 80.00\nVAT 8.50\nTOTAL 88.50 THB\nCASH 100.00",
        font=font,
        fill="black",
        spacing=25,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    receipt = ReceiptService(engine).scan(buffer.getvalue()).receipt
    assert str(receipt.amount) == "88.50"
    assert receipt.occurred_at.day == 7


@pytest.mark.integration
def test_corrupt_and_unsupported_images(engine):
    with pytest.raises(ReceiptError):
        engine.read(b"not an image")
    buffer = BytesIO()
    Image.new("RGB", (10, 10)).save(buffer, format="GIF")
    with pytest.raises(ReceiptError):
        engine.read(buffer.getvalue())
