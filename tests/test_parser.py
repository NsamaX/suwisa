from decimal import Decimal

import pytest

from suwisa.features.receipts.models import OcrDocument
from suwisa.features.receipts.parser import parse_date, parse_money, parse_receipt


def doc(text, date_text=""):
    return OcrDocument(text, 90, date_text)


def test_synthetic_bank_slip_keeps_amount_fee_and_reference_separate():
    receipt = parse_receipt(
        doc("""
Bangkok Bank
รายการสำเร็จ
7 ก.ย. 69, 09:15
จำนวนเงิน
1,234.56 THB
จาก นาย ทดสอบ
999-9-xxx999
ไปที่ ร้านตัวอย่าง
หมายเลขโทรศัพท์
0000000000
ค่าธรรมเนียม 5.00 THB
เลขที่อ้างอิง
99999999999999999999999
""")
    )
    assert receipt.amount == Decimal("1234.56")
    assert receipt.fee == Decimal("5.00")
    assert receipt.recipient == "ร้านตัวอย่าง"
    assert receipt.occurred_at.isoformat() == "2026-09-07T09:15:00+07:00"
    assert receipt.reference == "99999999999999999999999"
    assert "0000000000" not in str(receipt.to_dict())


@pytest.mark.parametrize(
    "month,number",
    [
        ("ม.ค.", 1),
        ("ก.พ.", 2),
        ("มี.ค.", 3),
        ("เม.ย.", 4),
        ("พ.ค.", 5),
        ("มิ.ย.", 6),
        ("ก.ค.", 7),
        ("ส.ค.", 8),
        ("ก.ย.", 9),
        ("ต.ค.", 10),
        ("พ.ย.", 11),
        ("ธ.ค.", 12),
    ],
)
def test_thai_months_and_buddhist_years(month, number):
    value = parse_date(f"07 {month} 2569, 09:15")
    assert (value.year, value.month, value.day) == (2026, number, 7)


def test_date_retry_uses_thai_crop_and_does_not_infer_from_reference():
    receipt = parse_receipt(
        doc("Bangkok Bank\n7 n.g.69, 09:15\nจำนวนเงิน\n88.50 THB", "7 ก.ุย.69, 09:15")
    )
    assert receipt.occurred_at.month == 9
    assert parse_date("2026090709150000000000000") is None
    assert parse_date("31 ก.พ.69, 09:15") is None


def test_labeled_total_not_subtotal_change_or_phone():
    receipt = parse_receipt(
        doc(
            "EXAMPLE SHOP\nSUBTOTAL 80.00\nVAT 8.50\nTOTAL 88.50 THB\nCASH 100.00\nCHANGE 11.50\n0000000000"
        )
    )
    assert receipt.amount == Decimal("88.50")


def test_unlabeled_or_ambiguous_money_is_never_guessed():
    assert parse_receipt(doc("Call 0000000000\nPrice 100.00\nCash 200.00")).amount is None
    receipt = parse_receipt(doc("ยอดรวม 50.00\nยอดรวม 60.00"))
    assert receipt.amount is None
    assert any("หลายค่า" in warning for warning in receipt.warnings)


def test_wallet_is_not_classified_as_an_expense():
    receipt = parse_receipt(
        doc("Bangkok Bank\nจำนวนเงิน\n88.50 THB\nไปที่ ng มันนี่\nService Code:TMNTOPUP")
    )
    assert receipt.recipient == "ทรูมันนี่ วอลเล็ท"
    assert "expense" not in receipt.to_dict()
    assert any("ย้ายเงิน" in warning for warning in receipt.warnings)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "12.345", "1000000000", "junk"])
def test_invalid_money_is_rejected(value):
    assert parse_money(value) is None


def test_thai_digits_and_unknown_currency():
    receipt = parse_receipt(doc("ยอดรวม ๘๘.๕๐ บาท\n07/09/2026 09:15"))
    assert receipt.amount == Decimal("88.50")
    assert receipt.currency == "THB"
    assert parse_receipt(doc("TOTAL 88.50 USD")).currency is None


def test_reference_label_with_dropped_tone_marks():
    receipt = parse_receipt(doc("Bangkok Bank\nเลขทีอ้างอิง\n99999999999999999999999"))
    assert receipt.reference == "99999999999999999999999"


def test_bank_brand_does_not_override_explicit_foreign_currency():
    receipt = parse_receipt(doc("Bangkok Bank\nจำนวนเงิน\n88.50 USD"))
    assert receipt.currency is None
