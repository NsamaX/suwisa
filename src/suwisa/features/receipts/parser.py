"""Conservative text parsing: labeled totals only; never guess the largest number."""

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from suwisa.features.receipts.models import OcrDocument, Receipt

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
MONEY = re.compile(r"(?<![\d.,-])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)")
MONTHS = {
    "มค": 1,
    "กพ": 2,
    "มีค": 3,
    "เมย": 4,
    "พค": 5,
    "มิย": 6,
    "กค": 7,
    "สค": 8,
    "กย": 9,
    "ตค": 10,
    "พย": 11,
    "ธค": 12,
}
DATE_WARNING = "อ่านวันเวลาไม่ชัด กรุณาตรวจจากภาพต้นฉบับ"
AMOUNT_WARNING = "ไม่พบยอดรวมที่ชัดเจน กรุณากรอกยอดจากภาพต้นฉบับ"


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(THAI_DIGITS)


def compact(text: str) -> str:
    return re.sub(r"\s+", "", normalized(text)).casefold()


def parse_money(text: str) -> Decimal | None:
    try:
        amount = Decimal(text.replace(",", "").strip())
        if not amount.is_finite() or amount < 0 or amount > Decimal("999999999.99"):
            return None
        if amount != amount.quantize(Decimal("0.01")):
            return None
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_date(text: str) -> datetime | None:
    text = normalized(text)
    # Thai short years are Buddhist Era (69 -> 2569 -> 2026).
    thai = re.search(r"(\d{1,2})\s*([ก-๙.\s]+?)\s*(\d{2,4})\s*[, ]+\s*(\d{1,2}):(\d{2})", text)
    if thai:
        day, label, year, hour, minute = thai.groups()
        label = re.sub(r"[.\s\u0e38-\u0e3a\u0e48-\u0e4c]", "", label)
        month = MONTHS.get(label)
        if not month:
            return None
        year = int(year)
        year = year + 2500 if year < 100 else year
        year = year - 543 if year >= 2400 else year
    else:
        numeric = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*[, ]+\s*(\d{1,2}):(\d{2})", text)
        if not numeric:
            return None
        day, month, year, hour, minute = map(int, numeric.groups())
        year = year - 543 if year >= 2400 else year
    try:
        return datetime(
            int(year), int(month), int(day), int(hour), int(minute), tzinfo=ZoneInfo("Asia/Bangkok")
        )
    except ValueError:
        return None


def labeled_amount(lines: list[str], labels: tuple[str, ...]) -> tuple[Decimal | None, bool]:
    candidates = set()
    for index, line in enumerate(lines):
        key = compact(line)
        if any(label in key for label in labels):
            matches = MONEY.findall(line)
            if not matches and index + 1 < len(lines):
                # Only a neighboring numeric line may supply a separated value.
                next_line = lines[index + 1]
                if re.match(r"^\s*[\d฿]", next_line):
                    matches = MONEY.findall(next_line)
            for match in matches:
                amount = parse_money(match)
                if amount is not None:
                    candidates.add(amount)
    return (next(iter(candidates)), False) if len(candidates) == 1 else (None, len(candidates) > 1)


def recipient_from(lines: list[str]) -> str | None:
    parts = []
    active = False
    for line in lines:
        key = compact(line)
        if key.startswith("ไปที่") or re.match(r"^to\s*[: ]", line, re.I):
            active = True
            line = re.sub(r"^\s*(ไป\s*ที่|To)\s*:?\s*", "", line, flags=re.I)
        elif active and (
            any(
                marker in key
                for marker in ("servicecode", "หมายเลข", "เบอร์โทร", "ค่าธรรมเนียม", "เลขที่", "ธนาคาร")
            )
            or re.match(r"^[\dXx*%-]{5}", key)
        ):
            break
        elif not active:
            continue
        # Logos can be read as isolated symbols or digits next to a name.
        line = re.sub(r"^[^ก-๙A-Za-z]+", "", line).strip()
        if line:
            parts.append(line)
        if len(parts) >= 3:
            break
    if not parts:
        return None
    result = " ".join(parts)
    # Stitch a Thai word wrapped immediately before a single consonant + space.
    result = re.sub(r"([ก-๙]) ([ก-ฮ]) (?=[ก-๙])", r"\1\2 ", result)
    return result[:300]


def parse_receipt(document: OcrDocument) -> Receipt:
    text = normalized(document.text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    key = compact(text)
    bank_slip = "bangkokbank" in key or "ธนาคารกรุงเทพ" in key
    receipt = Receipt(document_type="bank_slip" if bank_slip else "receipt")
    receipt.amount, ambiguous = labeled_amount(
        lines,
        (
            "จํานวนเงิน",
            "จำนวนเงิน",
            "ยอดชําระ",
            "ยอดชำระ",
            "ยอดสุทธิ",
            "รวมสุทธิ",
            "grandtotal",
            "amountpaid",
        )
        if bank_slip
        else ("รวมสุทธิ", "ยอดสุทธิ", "ยอดรวม", "grandtotal", "amountpaid", "totaldue"),
    )
    # English TOTAL must stand alone: SUBTOTAL is not the amount paid.
    if receipt.amount is None and not ambiguous and not bank_slip:
        total_lines = [line for line in lines if re.match(r"^total\b", line, re.I)]
        receipt.amount, ambiguous = labeled_amount(total_lines, ("total",))
    receipt.fee, _ = labeled_amount(lines, ("ค่าธรรมเนียม", "fee"))
    receipt.currency = "THB" if bank_slip or re.search(r"\bTHB\b|บาท|฿", text, re.I) else None
    receipt.occurred_at = parse_date(document.date_text) or parse_date(text)
    receipt.recipient = recipient_from(lines) if bank_slip else None
    if bank_slip and "servicecode:tmntopup" in key:
        receipt.recipient = "ทรูมันนี่ วอลเล็ท"
    for index, line in enumerate(lines):
        label = re.sub(r"[\u0e48-\u0e4c]", "", compact(line))
        if "เลขทีอางอิง" in label:
            match = re.search(r"\b\d{10,30}\b", " ".join(lines[index : index + 2]))
            if match:
                receipt.reference = match.group()
                break
    if receipt.amount is None:
        receipt.warnings.append(
            "พบยอดรวมหลายค่า กรุณาตรวจและกรอกยอดเอง" if ambiguous else AMOUNT_WARNING
        )
    if receipt.occurred_at is None:
        receipt.warnings.append(DATE_WARNING)
    if receipt.recipient is None:
        receipt.warnings.append("อ่านชื่อผู้รับหรือร้านค้าไม่ชัด กรุณาตรวจจากภาพ")
    if document.confidence < 80:
        receipt.warnings.append("ข้อความบางส่วนอ่านไม่ชัด โดยเฉพาะชื่อผู้รับ โปรดตรวจทุกช่อง")
    if "ทรูมันนี่" in key or "tmntopup" in key:
        receipt.warnings.append("อาจเป็นการเติมวอลเล็ต ต้องแยกการย้ายเงินจากรายจ่าย")
    if not bank_slip:
        receipt.warnings.append("รูปแบบทั่วไป: ยังไม่รองรับการแยกรายการสินค้า และชื่อร้านอัตโนมัติ")
    if receipt.currency is None:
        receipt.warnings.append("ไม่พบสกุลเงินที่ชัดเจน รุ่นนี้ยืนยันได้เฉพาะ THB")
    return receipt
