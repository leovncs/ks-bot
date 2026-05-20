"""
bot.py  -  Entry point for the Kingshot / Whiteout Survival schedule bot.

Run with:
    python bot.py
"""

import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("KingshotBot")

# ── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members          = True

bot = commands.Bot(command_prefix="!", intents=intents)

COGS = [
    "cogs.setup",        # one-time channel configuration
    "cogs.submissions",  # member signup flow
    "cogs.admin",        # schedule generation and publishing
    "cogs.lookup",       # member !myschedule command
]


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="Kingshot | !help"))


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(f"❌ {error}")
    elif isinstance(error, commands.CommandNotFound):
        pass  # ignore unknown commands silently
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `!help {ctx.command}` for usage.")
    else:
        logger.error(f"Unhandled error in command '{ctx.command}': {error}", exc_info=True)
        await ctx.send(f"❌ An unexpected error occurred: `{error}`")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        await bot.start(os.getenv("DISCORD_TOKEN", ""))


if __name__ == "__main__":
    asyncio.run(main())