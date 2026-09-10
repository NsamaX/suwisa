import asyncio
import logging
from contextlib import asynccontextmanager

import discord
from discord import app_commands
from discord.ext import commands

from suwisa.features.receipts.models import ReceiptError
from suwisa.features.receipts.presentation import receipt_embed
from suwisa.features.receipts.views import ReviewView

log = logging.getLogger(__name__)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class ReceiptCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.busy_users: set[int] = set()
        self.ocr_lock = asyncio.Lock()

    @asynccontextmanager
    async def slot(self, user_id: int):
        # Bound both queued jobs and active OCR CPU usage on a shared home server.
        if user_id in self.busy_users or len(self.busy_users) >= 3:
            raise ReceiptError("กำลังอ่านรูปอยู่ กรุณารอผลก่อนแล้วส่งใหม่")
        self.busy_users.add(user_id)
        try:
            async with self.ocr_lock:
                yield
        finally:
            self.busy_users.discard(user_id)

    async def scan(self, attachment: discord.Attachment, guild_id: int, user_id: int):
        if not attachment.filename.lower().endswith(IMAGE_EXTENSIONS):
            raise ReceiptError("รองรับ JPG, PNG และ WebP กรุณาแนบรูปใบเสร็จ")
        if attachment.size > self.bot.settings.max_attachment_bytes:
            raise ReceiptError("ไฟล์ใหญ่เกินกำหนด กรุณาย่อรูปแล้วส่งใหม่")
        async with self.slot(user_id):
            image = await attachment.read()
            scan = await asyncio.to_thread(self.bot.receipt_service.scan, image)
        return receipt_embed(scan.receipt), ReviewView(scan, self.bot.repository, guild_id, user_id)

    @app_commands.command(name="receipt", description="อ่านใบเสร็จหรือสลิป แล้วตรวจแก้ก่อนเก็บผล")
    @app_commands.guild_only()
    @app_commands.describe(image="รูป JPG, PNG หรือ WebP")
    async def receipt(self, interaction: discord.Interaction, image: discord.Attachment):
        if not self.bot.settings.permits(
            interaction.user.id, interaction.guild_id, interaction.channel_id
        ):
            await interaction.response.send_message(
                "ใช้คำสั่งนี้ได้เฉพาะผู้ใช้และห้องที่ตั้งค่าไว้", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            embed, view = await self.scan(image, interaction.guild_id, interaction.user.id)
            view.message = await interaction.followup.send(
                embed=embed, view=view, ephemeral=True, wait=True
            )
        except ReceiptError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception as exc:
            log.error("Receipt command failed (%s)", type(exc).__name__)
            await interaction.followup.send("อ่านรูปไม่สำเร็จ กรุณาลองใหม่", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.attachments:
            return
        if not self.bot.settings.permits(
            message.author.id, message.guild.id if message.guild else None, message.channel.id
        ):
            return
        if len(message.attachments) != 1:
            await message.reply(
                "กรุณาส่งใบเสร็จครั้งละ 1 รูป เพื่อให้ตรวจสอบแต่ละรายการได้", mention_author=False
            )
            return
        attachment = message.attachments[0]
        if not attachment.filename.lower().endswith(IMAGE_EXTENSIONS):
            return
        try:
            async with message.channel.typing():
                embed, view = await self.scan(attachment, message.guild.id, message.author.id)
                view.message = await message.reply(embed=embed, view=view, mention_author=False)
        except ReceiptError as exc:
            await message.reply(str(exc), mention_author=False)
        except Exception as exc:
            # Log only exception type, never receipt text, file URLs, or credentials.
            log.error("Receipt message failed (%s)", type(exc).__name__)
            try:
                await message.reply("อ่านรูปไม่สำเร็จ กรุณาลองใหม่", mention_author=False)
            except discord.HTTPException:
                pass


async def setup(bot):
    await bot.add_cog(ReceiptCog(bot))
