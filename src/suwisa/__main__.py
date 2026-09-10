import asyncio
import logging

import discord

from suwisa.bot import SuwisaBot
from suwisa.config import Settings
from suwisa.features.receipts.models import ReceiptError


async def run(settings: Settings):
    async with SuwisaBot(settings) as bot:
        await bot.start(settings.token)


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(run(Settings.from_env()))
    except (ValueError, ReceiptError) as exc:
        raise SystemExit(str(exc)) from None
    except (discord.LoginFailure, discord.PrivilegedIntentsRequired):
        raise SystemExit(
            "Discord login failed: check DISCORD_TOKEN and Message Content Intent"
        ) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
