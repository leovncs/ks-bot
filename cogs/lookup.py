"""
cogs/lookup.py  -  Personal schedule lookup for members.

Commands (only active in the configured #my-schedule channel)
-------------------------------------------------------------
!myschedule  -  Shows the days and slots the member was allocated to.

The channel is hidden by default and becomes visible only after the
admin runs `!schedule publish`.  It is hidden again by `!submissions close`.
"""

import discord
from discord.ext import commands
import logging

import database
from config import DAY_KEYS, DAY_LABELS

logger = logging.getLogger("KingshotBot.lookup")


class LookupCog(commands.Cog, name="Lookup"):
    """Personal schedule lookup for members."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="myschedule")
    async def my_schedule(self, ctx: commands.Context) -> None:
        """Show your allocated slots for the event."""

        # Silently ignore if not in the right channel
        lookup_ch_id = database.get_channel("lookup")
        if not lookup_ch_id or ctx.channel.id != lookup_ch_id:
            return

        if not database.is_lookup_open():
            await ctx.send(
                "⏳ The schedule hasn't been published yet. "
                "Check back after the admin announces it!",
                delete_after=10,
            )
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass
            return

        sched = database.get_schedule()
        if not sched:
            await ctx.send("❌ No schedule has been generated yet.", delete_after=15)
            return

        # Find all slots this user was allocated to
        user    = ctx.author
        found: dict[str, dict] = {}

        for day_key in DAY_KEYS:
            for entry in sched.get(day_key, []):
                if entry.get("user_id") == user.id:
                    found[day_key] = entry
                    break

        # Build the response embed
        if not found:
            embed = discord.Embed(
                title="📭 No slots found for you",
                description=(
                    "You weren't allocated to any day in the current schedule.\n\n"
                    "**Why might this happen?**\n"
                    "• You didn't submit before submissions closed.\n"
                    "• Your preferred time window was already taken by members "
                    "with higher speedup totals.\n\n"
                    "Contact an administrator if you think this is a mistake."
                ),
                color=discord.Color.light_grey(),
            )
        else:
            embed = discord.Embed(
                title="📅 Your Schedule",
                description="Here are your allocated slots for the event:",
                color=discord.Color.green(),
            )
            for day_key in DAY_KEYS:
                if day_key not in found:
                    continue

                entry = found[day_key]
                slot  = entry["slot"]
                label = DAY_LABELS[day_key]
                warn  = "\n⚠️ _You were placed outside your preferred window._" \
                        if entry.get("outside_preference") else ""

                note = ""
                if slot == "23:45":
                    if day_key in ("day1", "day4"):
                        note = (
                            "\n> 📌 **Pre-reset slot** — apply your speedups in the "
                            "15 minutes before the event day begins."
                        )
                    elif day_key == "day2":
                        note = (
                            "\n> 📌 **Bridge slot** — you have 15 min at the end of "
                            "Day 1 and 15 min at the start of Day 2."
                        )

                embed.add_field(
                    name=label,
                    value=f"🕐 **`{slot}`**{warn}{note}",
                    inline=False,
                )
            embed.set_footer(text="Use your slot to apply speedups for maximum kingdom impact!")

        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

        # Delete the command to keep the channel clean
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        await ctx.send(embed=embed)
        logger.info(f"Schedule lookup: {user.name} → {list(found.keys())}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LookupCog(bot))