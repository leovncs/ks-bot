"""
cogs/setup.py  -  One-time channel configuration commands.

These commands are run once by a server administrator to tell the bot
which channels it should use.  Requires the Discord "Administrator"
permission — not just the admin channel guard used elsewhere.

Commands
--------
!setup submissions   - designate the current channel as #submissions
!setup admin         - designate the current channel as #admin
!setup announcements - designate the current channel as #announcements
!setup lookup        - designate the current channel as #my-schedule
                       (immediately hidden from @everyone)
!setup status        - show all configured channels
"""

import discord
from discord.ext import commands
import logging

import database

logger = logging.getLogger("KingshotBot.setup")

_DESCRIPTIONS = {
    "submissions":   "Members send their speedup screenshots and availability here.",
    "admin":         "Administrators run bot commands here.",
    "announcements": "The published schedule is posted here.",
    "lookup":        "Members run `!myschedule` here to see their personal slots.",
}

_VALID = set(_DESCRIPTIONS.keys())


class SetupCog(commands.Cog, name="Setup"):
    """One-time channel configuration."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── !setup <target> ───────────────────────────────────────────────────────

    @commands.group(name="setup", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: commands.Context) -> None:
        """Configure bot channels. Usage: !setup <submissions|admin|announcements|lookup|status>"""
        await ctx.send(
            "**Usage:** `!setup <target>`\n\n"
            "Targets:\n"
            "  `submissions`   - channel where members submit screenshots\n"
            "  `admin`         - channel where admins run commands\n"
            "  `announcements` - channel where the schedule is published\n"
            "  `lookup`        - channel where members check their schedule\n"
            "  `status`        - show all currently configured channels\n"
        )

    @setup.command(name="submissions")
    @commands.has_permissions(administrator=True)
    async def setup_submissions(self, ctx: commands.Context) -> None:
        """Set this channel as the submissions channel."""
        await self._configure(ctx, "submissions")

    @setup.command(name="admin")
    @commands.has_permissions(administrator=True)
    async def setup_admin(self, ctx: commands.Context) -> None:
        """Set this channel as the admin channel."""
        await self._configure(ctx, "admin")

    @setup.command(name="announcements")
    @commands.has_permissions(administrator=True)
    async def setup_announcements(self, ctx: commands.Context) -> None:
        """Set this channel as the announcements channel."""
        await self._configure(ctx, "announcements")

    @setup.command(name="lookup")
    @commands.has_permissions(administrator=True)
    async def setup_lookup(self, ctx: commands.Context) -> None:
        """Set this channel as the #my-schedule lookup channel (hidden by default)."""
        await self._configure(ctx, "lookup")

        everyone = ctx.guild.default_role
        await ctx.channel.set_permissions(
            everyone, view_channel=False, send_messages=False
        )

        user_role = discord.utils.get(ctx.guild.roles, name="USER")
        if user_role:
            await ctx.channel.set_permissions(
                user_role, view_channel=False, send_messages=False
            )
            role_msg = "and hidden from the **USER** role"
        else:
            role_msg = "⚠️ (Warning: **USER** role not found in this server)"

        database.set_lookup_open(False)
        await ctx.send(
            f"🔒 This channel is now **hidden** from everyone {role_msg}.\n"
            "It will become visible to the USER role automatically when you run `!schedule publish`."
        )

    @setup.command(name="status")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, ctx: commands.Context) -> None:
        """Show which channels are currently configured."""
        embed = discord.Embed(title="⚙️ Channel Configuration", color=discord.Color.blurple())

        for name, desc in _DESCRIPTIONS.items():
            ch_id = database.get_channel(name)
            ch    = ctx.guild.get_channel(ch_id) if ch_id else None
            embed.add_field(
                name=f"#{name}",
                value=f"{ch.mention if ch else '`not configured`'}\n{desc}",
                inline=False,
            )

        await ctx.send(embed=embed)

    # ── Shared helper ─────────────────────────────────────────────────────────

    async def _configure(self, ctx: commands.Context, name: str) -> None:
        database.set_channel(name, ctx.channel.id)
        desc = _DESCRIPTIONS[name]
        await ctx.send(
            f"✅ **`#{name}` channel configured** → {ctx.channel.mention}\n_{desc}_"
        )
        logger.info(f"Channel '{name}' set to #{ctx.channel.name} ({ctx.channel.id})")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))