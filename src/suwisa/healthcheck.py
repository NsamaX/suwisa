import os
import time
from pathlib import Path


def main():
    path = Path(os.getenv("DATABASE_PATH", "data/suwisa.sqlite3")).parent / "gateway-health"
    try:
        age = time.time() - float(path.read_text(encoding="utf-8"))
        raise SystemExit(0 if 0 <= age < 150 else 1)
    except (OSError, ValueError):
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
