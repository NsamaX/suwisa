import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from suwisa.features.receipts.models import ReceiptError
from suwisa.features.receipts.service import ReceiptService
from suwisa.infrastructure.ocr.tesseract import TesseractEngine
from suwisa.infrastructure.storage import ReceiptRepository


def main():
    parser = argparse.ArgumentParser(description="Read a local receipt without a Discord token")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    load_dotenv(".env")
    try:
        service = ReceiptService(TesseractEngine(int(os.getenv("OCR_TIMEOUT_SECONDS", "30"))))
        if args.image.stat().st_size > service.max_bytes:
            raise ReceiptError("Image exceeds the 10 MB CLI limit")
        scan = service.scan(args.image.read_bytes())
    except (OSError, ValueError, ReceiptError) as exc:
        parser.exit(1, f"Cannot read receipt: {exc}\n")
    print(
        json.dumps(
            {"receipt": scan.receipt.to_dict(), "ocr_confidence": round(scan.confidence, 1)},
            ensure_ascii=False,
            indent=2,
        )
    )


def backup_main():
    parser = argparse.ArgumentParser(
        description="Consistent SQLite backup, including live WAL data"
    )
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    load_dotenv(".env")
    source = Path(os.getenv("DATABASE_PATH", "data/suwisa.sqlite3"))
    if not source.is_file():
        parser.exit(1, "Database does not exist\n")
    ReceiptRepository(source).backup(args.destination)
    print("Backup completed")


if __name__ == "__main__":
    main()
