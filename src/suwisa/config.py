import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def positive_int(value: str, name: str) -> int:
    try:
        result = int(value)
        if result <= 0:
            raise ValueError
        return result
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None


def id_set(value: str, name: str) -> frozenset[int]:
    values = frozenset(
        positive_int(part.strip(), name) for part in value.split(",") if part.strip()
    )
    if not values:
        raise ValueError(f"{name} is required; configure an explicit allowlist")
    return values


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    guild_id: int
    allowed_user_ids: frozenset[int]
    receipt_channel_ids: frozenset[int]
    database_path: Path = Path("data/suwisa.sqlite3")
    ocr_timeout: int = 30
    max_attachment_bytes: int = 10 * 1024 * 1024

    def permits(self, user_id: int, guild_id: int | None, channel_id: int | None) -> bool:
        return (
            guild_id == self.guild_id
            and user_id in self.allowed_user_ids
            and channel_id in self.receipt_channel_ids
        )

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(".env")
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_TOKEN is required in .env")
        timeout = positive_int(os.getenv("OCR_TIMEOUT_SECONDS", "30"), "OCR_TIMEOUT_SECONDS")
        size = positive_int(os.getenv("MAX_ATTACHMENT_MB", "10"), "MAX_ATTACHMENT_MB")
        if timeout > 120 or size > 20:
            raise ValueError("OCR timeout must be <=120 seconds and attachment limit <=20 MB")
        return cls(
            token=token,
            guild_id=positive_int(os.getenv("DISCORD_GUILD_ID", ""), "DISCORD_GUILD_ID"),
            allowed_user_ids=id_set(os.getenv("ALLOWED_USER_IDS", ""), "ALLOWED_USER_IDS"),
            receipt_channel_ids=id_set(os.getenv("RECEIPT_CHANNEL_IDS", ""), "RECEIPT_CHANNEL_IDS"),
            database_path=Path(os.getenv("DATABASE_PATH", "data/suwisa.sqlite3")),
            ocr_timeout=timeout,
            max_attachment_bytes=size * 1024 * 1024,
        )
