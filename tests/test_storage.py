import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal

import pytest

from suwisa.features.receipts.models import Receipt, ReceiptError, ReceiptScan
from suwisa.infrastructure.storage import ReceiptRepository


def scan(digest="a", reference=None, amount="88.50"):
    return ReceiptScan(
        Receipt(amount=Decimal(amount), currency="THB", reference=reference), digest, 90
    )


def test_duplicate_hash_and_reference_are_scoped_to_owner(tmp_path):
    repo = ReceiptRepository(tmp_path / "data.sqlite3")
    first = repo.save(scan(reference="example-reference"), 1, 2)
    assert first == (1, True)
    assert repo.save(scan(), 1, 2) == (1, False)
    assert repo.save(scan("new-image", "example-reference"), 1, 2) == (1, False)
    assert repo.save(scan(reference="example-reference"), 1, 3)[1] is True


def test_concurrent_confirmations_create_one_record(tmp_path):
    repo = ReceiptRepository(tmp_path / "data.sqlite3")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repo.save(scan(), 1, 2), range(8)))
    assert sum(created for _, created in results) == 1


def test_backup_can_be_restored_with_exact_decimal_values(tmp_path):
    repo = ReceiptRepository(tmp_path / "data.sqlite3")
    repo.save(scan(), 1, 2)
    target = tmp_path / "backup.sqlite3"
    repo.backup(target)
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        payload = json.loads(connection.execute("SELECT payload FROM receipts").fetchone()[0])
    assert payload["amount"] == "88.50"
    assert "raw_text" not in payload


def test_unread_or_zero_total_cannot_be_confirmed(tmp_path):
    repo = ReceiptRepository(tmp_path / "data.sqlite3")
    with pytest.raises(ReceiptError):
        repo.save(scan(amount="0"), 1, 2)
    with pytest.raises(ValueError):
        repo.backup(repo.path)
