import asyncio
import logging
import time

import discord
from discord.ext import commands, tasks

from suwisa.config import Settings
from suwisa.features.receipts.service import ReceiptService
from suwisa.infrastructure.ocr.tesseract import TesseractEngine
from suwisa.infrastructure.storage import ReceiptRepository

FEATURE_EXTENSIONS = ("suwisa.features.receipts.cog",)
log = logging.getLogger(__name__)


class SuwisaBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
            help_command=None,
            max_messages=None,
        )
        self.settings = settings
        self.receipt_service = ReceiptService(
            TesseractEngine(settings.ocr_timeout), settings.max_attachment_bytes
        )
        self.repository = ReceiptRepository(settings.database_path)
        self.health_path = settings.database_path.parent / "gateway-health"
        self.health_path.unlink(missing_ok=True)

    async def setup_hook(self):
        for extension in FEATURE_EXTENSIONS:
            await self.load_extension(extension)
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.health_tick.start()

    async def on_ready(self):
        log.info("Suwisa connected; receipt feature ready")

    async def on_command_error(self, context, exception):
        if not isinstance(exception, commands.CommandNotFound):
            log.error("Command failed (%s)", type(exception).__name__)

    @tasks.loop(seconds=30)
    async def health_tick(self):
        if self.is_ready() and self.latency < 60:
            await asyncio.to_thread(self.health_path.write_text, str(time.time()), encoding="utf-8")

    async def close(self):
        self.health_tick.cancel()
        self.health_path.unlink(missing_ok=True)
        await super().close()
