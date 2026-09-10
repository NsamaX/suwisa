import json
import sqlite3
from contextlib import closing
from pathlib import Path

from suwisa.features.receipts.models import ReceiptError, ReceiptScan

SCHEMA_VERSION = 1


class ReceiptRepository:
    """Stores reviewed extraction results, never ledger entries or original images."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection, connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Database is newer than this application; do not downgrade")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    image_sha256 TEXT NOT NULL,
                    reference TEXT,
                    payload TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    UNIQUE(guild_id, user_id, image_sha256)
                )
            """)
            connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS receipts_reference
                ON receipts(guild_id, user_id, reference) WHERE reference IS NOT NULL
            """)
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def save(self, scan: ReceiptScan, guild_id: int, user_id: int) -> tuple[int, bool]:
        receipt = scan.receipt
        if receipt.amount is None or receipt.amount <= 0 or receipt.currency != "THB":
            raise ReceiptError("กรุณาระบุยอดมากกว่า 0 และตรวจว่าสกุลเงินเป็น THB ก่อนยืนยัน")
        with closing(self.connect()) as connection, connection:
            cursor = connection.execute(
                """INSERT INTO receipts(guild_id, user_id, image_sha256, reference, payload)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (
                    str(guild_id),
                    str(user_id),
                    scan.image_sha256,
                    receipt.reference,
                    json.dumps(receipt.to_dict(), ensure_ascii=False),
                ),
            )
            if cursor.rowcount:
                return cursor.lastrowid, True
            row = connection.execute(
                """SELECT id FROM receipts WHERE guild_id=? AND user_id=?
                   AND (image_sha256=? OR (reference IS NOT NULL AND reference=?))""",
                (str(guild_id), str(user_id), scan.image_sha256, receipt.reference),
            ).fetchone()
            return row[0], False

    def backup(self, destination: Path) -> None:
        if destination.resolve() == self.path.resolve():
            raise ValueError("Backup destination must differ from the live database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
