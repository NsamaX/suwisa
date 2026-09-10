import os
import re
import shutil
import warnings
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from suwisa.features.receipts.models import OcrDocument, ReceiptError

MAX_PIXELS = 20_000_000


class TesseractEngine:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        executable = os.getenv("TESSERACT_CMD", "").strip() or shutil.which("tesseract")
        if not executable:
            candidate = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
            if candidate.exists():
                executable = str(candidate)
        if not executable:
            raise ReceiptError("ไม่พบ Tesseract กรุณาติดตั้งพร้อมภาษา tha และ eng")
        pytesseract.pytesseract.tesseract_cmd = executable
        directory = os.getenv("TESSDATA_DIR", "").strip()
        # Environment avoids Windows subprocess quoting bugs in paths with spaces.
        if directory:
            os.environ["TESSDATA_PREFIX"] = str(Path(directory).resolve())
        self.config = ""
        try:
            languages = pytesseract.get_languages(config=self.config)
        except pytesseract.TesseractNotFoundError:
            raise ReceiptError("ไม่พบโปรแกรม Tesseract ตาม TESSERACT_CMD") from None
        if not {"tha", "eng"}.issubset(languages):
            raise ReceiptError("Tesseract ต้องมีภาษา tha และ eng ตรวจสอบ TESSDATA_DIR")

    def read(self, image: bytes) -> OcrDocument:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(image)) as source:
                    if source.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ReceiptError("รองรับเฉพาะภาพ JPG, PNG และ WebP")
                    if source.width * source.height > MAX_PIXELS:
                        raise ReceiptError("ภาพใหญ่เกิน 20 ล้านพิกเซล กรุณาย่อภาพก่อน")
                    if getattr(source, "n_frames", 1) > 1:
                        raise ReceiptError("กรุณาส่งภาพนิ่งเพียงภาพเดียว")
                    source.load()
                    corrected = ImageOps.exif_transpose(source).convert("RGBA")
                    background = Image.new("RGBA", corrected.size, "white")
                    background.alpha_composite(corrected)
                    prepared = ImageOps.grayscale(background.convert("RGB"))
                    prepared.thumbnail((2400, 3600))
                    prepared = ImageOps.autocontrast(prepared)
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise ReceiptError("เปิดรูปไม่ได้ หรือรูปใหญ่เกินกำหนด กรุณาส่งภาพใหม่") from None
        try:
            # Tesseract's TXT renderer preserves Thai word boundaries. Joining TSV
            # tokens adds spaces inside Thai words; TSV is used only for geometry.
            rendered_text = pytesseract.image_to_string(
                prepared,
                lang="tha+eng",
                config=f"{self.config} --psm 6",
                timeout=self.timeout,
            ).strip()
            data = pytesseract.image_to_data(
                prepared,
                lang="tha+eng",
                config=f"{self.config} --psm 6",
                output_type=pytesseract.Output.DICT,
                timeout=self.timeout,
            )
            lines = defaultdict(list)
            confidences = []
            for index, value in enumerate(data["text"]):
                if value.strip():
                    key = (
                        data["block_num"][index],
                        data["par_num"][index],
                        data["line_num"][index],
                    )
                    lines[key].append(index)
                    if float(data["conf"][index]) >= 0:
                        confidences.append(float(data["conf"][index]))
            text_lines = [" ".join(data["text"][i] for i in indices) for indices in lines.values()]
            # Mixed Thai/English OCR often reads Thai month abbreviations as Latin text.
            # A second Thai-only pass on the date line preserves the original pixels.
            date_text = ""
            for indices, text in zip(lines.values(), text_lines, strict=True):
                if re.search(r"\d{1,2}:\d{2}", text):
                    top = max(0, min(data["top"][i] for i in indices) - 8)
                    bottom = min(
                        prepared.height,
                        max(data["top"][i] + data["height"][i] for i in indices) + 8,
                    )
                    date_text = pytesseract.image_to_string(
                        prepared.crop((0, top, prepared.width, bottom)),
                        lang="tha",
                        config=f"{self.config} --psm 7",
                        timeout=self.timeout,
                    ).strip()
                    break
        except (RuntimeError, pytesseract.TesseractError):
            raise ReceiptError("อ่านภาพไม่สำเร็จหรือใช้เวลานานเกินไป กรุณาลองภาพที่ชัดขึ้น") from None
        text = rendered_text
        if not text:
            raise ReceiptError("ไม่พบข้อความในภาพ กรุณาส่งใบเสร็จที่ชัดและตรง")
        return OcrDocument(text, sum(confidences) / max(1, len(confidences)), date_text)
