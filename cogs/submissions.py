"""
cogs/submissions.py  -  Member signup flow.

Members send a message in #submissions that must include either:
  • A bot mention (@Bot) + availability text
  • An attached speedup screenshot
  • OR both (screenshot + text)

Speedups can also be provided as plain text lines instead of (or in addition to)
a screenshot:
    General: 39d13h26m
    Soldier: 949h26m
    Construction: 56,966min
    Research: 39:13:26

All formats are converted to the canonical 'XdYhZm' representation.
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

        ch_id = database.get_channel("submissions")
        if not ch_id or message.channel.id != ch_id:
            return

        bot_mentioned = self.bot.user in message.mentions
        has_image     = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )
        has_text_speedups = bool(ocr.extract_speedups_from_text(message.content))

        if not bot_mentioned and not has_image and not has_text_speedups:
            return

        if not database.is_accepting():
            await message.reply(
                "⛔ **Submissions are closed.**\n"
                "The registration period has ended. "
                "The schedule will be announced soon!",
                mention_author=False,
            )
            return

        await self._process(message, user=message.author)

    # ── Core processing ───────────────────────────────────────────────────────

    async def _process(
        self,
        message: discord.Message,
        user: discord.Member | discord.User,
        override_username: str | None = None,
        override_user_id: int | None = None,
    ) -> None:
        """
        Process a submission.  When called from admin !users add, `override_*`
        are set to the target user's identity.
        """
        username = override_username or user.display_name
        user_id  = override_user_id  or user.id

        status = await message.reply("⏳ Processing your submission…", mention_author=False)

        try:
            # 1. OCR — extract speedups from attached screenshot
            speedups    = {}
            image_found = False

            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    image_found = True
                    raw = await ocr.download_image(attachment.url)
                    if raw:
                        speedups = await ocr.extract_speedups_from_image(raw)
                        logger.info(f"OCR: {len(speedups)} speedup(s) read for {username}")
                    break

            # 2. Text speedups — override or supplement OCR values
            text_speedups = ocr.extract_speedups_from_text(message.content)
            if text_speedups:
                # Text takes priority over OCR for any key it provides
                speedups.update(text_speedups)
                logger.info(f"Text speedups: {len(text_speedups)} value(s) for {username}")

            # 3. Parse availability
            availability = parser.parse_availability(message.content)

            if not availability:
                await status.edit(content=(
                    "❌ **Couldn't understand your availability.**\n"
                    "Please include the days and time windows. Examples:\n"
                    "```\n"
                    "@Bot Day 1: 10:00-16:00  Day 2: any time  Day 4: 21:00-23:00\n"
                    "@Bot Sign me up any time close to reset on all 3 days\n"
                    "@Bot Day 4 between 20:00 and 22:00\n"
                    "```"
                ))
                return

            # 4. Persist
            database.save_submission(
                user_id=user_id,
                username=username,
                speedups=speedups,
                availability=availability,
            )

            # 5. Confirmation embed
            embed = discord.Embed(
                title="✅ Submission Received!",
                color=discord.Color.green(),
            )
            embed.set_author(name=username, icon_url=user.display_avatar.url)
            embed.add_field(
                name="📅 Availability",
                value=parser.format_availability(availability),
                inline=False,
            )
            embed.add_field(
                name="⚡ Speedups",
                value=ocr.format_speedups(speedups) if speedups else "_No speedups provided._",
                inline=False,
            )

            warnings = []
            if not image_found and not text_speedups:
                warnings.append("No screenshot or text speedups provided — speedups were not recorded.")
            elif image_found and not speedups:
                warnings.append("OCR couldn't read the screenshot. Check the image is legible.")
            if warnings:
                embed.add_field(name="⚠️ Note", value="\n".join(warnings), inline=False)

            embed.set_footer(text="You'll be considered when the schedule is generated.")
            await status.edit(content=None, embed=embed)
            logger.info(f"Submission saved: {username} (ID: {user_id})")

        except Exception as exc:
            logger.error(f"Submission error for {username}: {exc}", exc_info=True)
            await status.edit(content=(
                f"❌ **An unexpected error occurred:** `{exc}`\n"
                "Please try again or contact an administrator."
            ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SubmissionsCog(bot))