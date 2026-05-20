"""
cogs/submissions.py  -  Member signup flow.

Members send a message in #submissions that must contain:
  • A mention of the bot (@Bot)  OR  an attached speedup screenshot
  • Their availability in natural language

The bot reads the screenshot via OCR, parses the availability message,
and saves both to the database.

Commands
--------
(none — all interaction happens via on_message)
"""

import discord
from discord.ext import commands
import logging

import database
import ocr
import parser

logger = logging.getLogger("KingshotBot.submissions")


class SubmissionsCog(commands.Cog, name="Submissions"):
    """Handles the member submission flow in #submissions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # Only act in the configured submissions channel
        ch_id = database.get_channel("submissions")
        if not ch_id or message.channel.id != ch_id:
            return

        bot_mentioned = self.bot.user in message.mentions
        has_image     = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )

        if not bot_mentioned and not has_image:
            return

        if not database.is_accepting():
            await message.reply(
                "⛔ **Submissions are closed.**\n"
                "The registration period has ended. "
                "The schedule is being generated — stay tuned for the announcement!",
                mention_author=False,
            )
            return

        await self._process(message)

    # ── Core processing ───────────────────────────────────────────────────────

    async def _process(self, message: discord.Message) -> None:
        user   = message.author
        status = await message.reply("⏳ Processing your submission…", mention_author=False)

        try:
            # 1. OCR — extract speedups from the first attached image
            speedups    = {}
            image_found = False

            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    image_found = True
                    raw = await ocr.download_image(attachment.url)
                    if raw:
                        speedups = await ocr.extract_speedups_from_image(raw)
                        logger.info(f"OCR: {len(speedups)} speedup(s) from {user.name}")
                    break  # process only the first image

            # 2. Parse availability from the message text
            availability = parser.parse_availability(message.content)

            if not availability:
                await status.edit(content=(
                    "❌ **Couldn't understand your availability.**\n"
                    "Please include the days and time windows you're free. Examples:\n"
                    "```\n"
                    "@Bot Day 1: 10:00-16:00  Day 2: any time  Day 4: 21:00-23:00\n"
                    "@Bot Sign me up any time close to reset on all 3 days\n"
                    "@Bot Day 4 between 20:00 and 22:00\n"
                    "```"
                ))
                return

            # 3. Persist
            database.save_submission(
                user_id=user.id,
                username=user.display_name,
                speedups=speedups,
                availability=availability,
            )

            # 4. Confirmation embed
            embed = discord.Embed(
                title="✅ Submission Received!",
                color=discord.Color.green(),
            )
            embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
            embed.add_field(
                name="📅 Availability",
                value=parser.format_availability(availability),
                inline=False,
            )
            embed.add_field(
                name="⚡ Speedups Detected",
                value=ocr.format_speedups(speedups) if speedups else "_No speedups detected._",
                inline=False,
            )

            warnings = []
            if not image_found:
                warnings.append("No screenshot attached — speedups were not recorded.")
            elif not speedups:
                warnings.append("OCR couldn't read the speedups. Make sure the image is legible.")
            if warnings:
                embed.add_field(name="⚠️ Note", value="\n".join(warnings), inline=False)

            embed.set_footer(text="You'll be considered when the schedule is generated.")
            await status.edit(content=None, embed=embed)
            logger.info(f"Submission saved: {user.name} (ID: {user.id})")

        except Exception as exc:
            logger.error(f"Submission error for {user.name}: {exc}", exc_info=True)
            await status.edit(content=(
                f"❌ **An unexpected error occurred:** `{exc}`\n"
                "Please try again or contact an administrator."
            ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SubmissionsCog(bot))