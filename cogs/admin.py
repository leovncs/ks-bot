"""
cogs/admin.py  -  Schedule generation and publishing commands.

All commands require the user to be a server administrator OR to be
in the configured admin channel.

Commands
--------
Submissions
  !submissions open    - re-open #submissions
  !submissions close   - close #submissions (also hides #my-schedule)

Schedule management
  !schedule generate   - build the schedule from all submissions
  !schedule preview [day]  - preview schedule in this channel
  !schedule publish [day]  - post to #announcements + open #my-schedule
  !schedule clear      - wipe the generated schedule

User management
  !users list          - list all registered users
  !users remove @user  - remove a user's submission

Danger zone
  !reset CONFIRM       - wipe everything and start over
"""

import json
import logging

import discord
from discord.ext import commands

import database
import scheduler
from config import DAY_ALIASES, DAY_KEYS, DAY_LABELS, DAY_COLORS

logger = logging.getLogger("KingshotBot.admin")


# ── Access guard ──────────────────────────────────────────────────────────────

def _admin_check():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.guild_permissions.administrator:
            return True
        admin_ch = database.get_channel("admin")
        if admin_ch and ctx.channel.id == admin_ch:
            return True
        raise commands.CheckFailure(
            "This command can only be used by administrators or in the admin channel."
        )
    return commands.check(predicate)


# ── Shared embed builder ──────────────────────────────────────────────────────

def _build_day_embeds(day_key: str, entries: list[dict]) -> list[discord.Embed]:
    """Return a list of embeds for one day (chunked to 20 entries each)."""
    label = DAY_LABELS[day_key]
    color = DAY_COLORS[day_key]

    if not entries:
        return [discord.Embed(title=label, description="_No users allocated._", color=color)]

    chunk_size = 20
    chunks     = [entries[i:i+chunk_size] for i in range(0, len(entries), chunk_size)]
    embeds     = []

    for i, chunk in enumerate(chunks):
        suffix = f" (part {i+1}/{len(chunks)})" if len(chunks) > 1 else ""
        embed  = discord.Embed(title=label + suffix, color=color)
        lines  = []

        for entry in chunk:
            slot  = entry["slot"]
            warn  = " ⚠️" if entry.get("outside_preference") else ""
            annot = ""
            if slot == "23:45":
                if day_key in ("day1", "day4") and entry is entries[0]:
                    annot = " _(pre-reset)_"
                elif day_key == "day2" and entry is entries[0]:
                    annot = " _(shared D1→D2)_"
                else:
                    annot = " _(end of day)_"
            lines.append(f"`{slot}`{annot} → **{entry['username']}**{warn}")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{len(entries)} member(s) allocated on this day")
        embeds.append(embed)

    return embeds


async def _send_embeds(target, day_key: str, entries: list[dict]) -> None:
    for embed in _build_day_embeds(day_key, entries):
        await target.send(embed=embed)


# ── Cog ───────────────────────────────────────────────────────────────────────

class AdminCog(commands.Cog, name="Admin"):
    """Schedule generation and publishing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ════════════════════════════════════════════════════════════════════════
    # !submissions group
    # ════════════════════════════════════════════════════════════════════════

    @commands.group(name="submissions", invoke_without_command=True)
    @_admin_check()
    async def submissions(self, ctx: commands.Context) -> None:
        """Manage the submission period. Usage: !submissions <open|close>"""
        await ctx.send("Usage: `!submissions open` or `!submissions close`")

    @submissions.command(name="open")
    @_admin_check()
    async def submissions_open(self, ctx: commands.Context) -> None:
        """Re-open #submissions so members can sign up again."""
        database.set_accepting(True)
        await ctx.send("🟢 Submissions are now **open**.")

        ch_id = database.get_channel("submissions")
        if ch_id and (ch := ctx.guild.get_channel(ch_id)):
            await ch.send(
                "🟢 **Submissions are open!**\n"
                "Send your speedup screenshot and availability to sign up."
            )
        logger.info(f"Submissions opened by {ctx.author.name}")

    @submissions.command(name="close")
    @_admin_check()
    async def submissions_close(self, ctx: commands.Context) -> None:
        """Close #submissions and hide #my-schedule."""
        database.set_accepting(False)
        await self._set_lookup_visible(ctx.guild, visible=False)
        await ctx.send("🔴 Submissions are now **closed**. The `#my-schedule` channel is hidden.")

        ch_id = database.get_channel("submissions")
        if ch_id and (ch := ctx.guild.get_channel(ch_id)):
            await ch.send(
                "⛔ **Submissions are closed.**\n"
                "The registration period has ended. "
                "The schedule will be announced soon!"
            )
        logger.info(f"Submissions closed by {ctx.author.name}")

    # ════════════════════════════════════════════════════════════════════════
    # !schedule group
    # ════════════════════════════════════════════════════════════════════════

    @commands.group(name="schedule", invoke_without_command=True)
    @_admin_check()
    async def schedule(self, ctx: commands.Context) -> None:
        """Manage the event schedule. Usage: !schedule <generate|preview|publish|clear>"""
        await ctx.send(
            "**Schedule commands:**\n"
            "`!schedule generate`         - build schedule from submissions\n"
            "`!schedule preview [day]`    - preview here (day1 / day2 / day4)\n"
            "`!schedule publish [day]`    - post to #announcements + open #my-schedule\n"
            "`!schedule clear`            - wipe the current schedule\n"
        )

    # ── generate ─────────────────────────────────────────────────────────────

    @schedule.command(name="generate")
    @_admin_check()
    async def schedule_generate(self, ctx: commands.Context) -> None:
        """Build the schedule from all current submissions."""
        submissions = database.get_all_submissions()
        if not submissions:
            await ctx.send("❌ No submissions yet — nobody has signed up.")
            return

        await ctx.send("⏳ Generating schedule…")
        database.set_accepting(False)

        sched = scheduler.generate_schedule(submissions)
        database.save_schedule(sched)

        total = sum(len(v) for v in sched.values())
        await ctx.send(
            f"✅ **Schedule generated!** — {total} slot(s) allocated across all days.\n"
            f"Use `!schedule preview` to review, or `!schedule publish` to post it."
        )

        ch_id = database.get_channel("submissions")
        if ch_id and (ch := ctx.guild.get_channel(ch_id)):
            await ch.send(
                "📋 **Schedule generated!**\n"
                "The administrator has built the event schedule. "
                "It will be published to announcements shortly!"
            )
        logger.info(f"Schedule generated by {ctx.author.name} — {total} slots")

    # ── preview ───────────────────────────────────────────────────────────────

    @schedule.command(name="preview")
    @_admin_check()
    async def schedule_preview(self, ctx: commands.Context, day: str = None) -> None:
        """
        Preview the schedule in this channel.
        Usage: !schedule preview           (all days)
               !schedule preview day1     (single day)
        """
        sched = database.get_schedule()
        if not sched:
            await ctx.send("❌ No schedule yet. Run `!schedule generate` first.")
            return

        days = self._resolve_days(day)
        if days is None:
            await ctx.send("❌ Unknown day. Use `day1`, `day2`, or `day4`.")
            return

        for dk in days:
            await _send_embeds(ctx, dk, sched.get(dk, []))

    # ── publish ───────────────────────────────────────────────────────────────

    @schedule.command(name="publish")
    @_admin_check()
    async def schedule_publish(self, ctx: commands.Context, day: str = None) -> None:
        """
        Post the schedule to #announcements and open #my-schedule.
        Usage: !schedule publish           (all days)
               !schedule publish day1     (single day)
        """
        sched = database.get_schedule()
        if not sched:
            await ctx.send("❌ No schedule yet. Run `!schedule generate` first.")
            return

        ann_ch_id = database.get_channel("announcements")
        if not ann_ch_id or not (ann_ch := ctx.guild.get_channel(ann_ch_id)):
            await ctx.send(
                "❌ Announcements channel not configured.\n"
                "Run `!setup announcements` in your #announcements channel first."
            )
            return

        days = self._resolve_days(day)
        if days is None:
            await ctx.send("❌ Unknown day. Use `day1`, `day2`, or `day4`.")
            return

        lookup_ch_id = database.get_channel("lookup")
        lookup_ch    = ctx.guild.get_channel(lookup_ch_id) if lookup_ch_id else None

        # Post header message
        await ann_ch.send(
            "📅 **Event Schedule Published!**\n"
            "Find your slot below and use it to apply your speedups at the right time."
            + (f"\n\nCheck {lookup_ch.mention} to see your personal slot." if lookup_ch else "")
        )

        # Post day embeds
        for dk in days:
            await _send_embeds(ann_ch, dk, sched.get(dk, []))

        # Open the lookup channel
        opened = await self._set_lookup_visible(ctx.guild, visible=True)
        if opened and lookup_ch:
            await lookup_ch.send(
                "📬 **The schedule is live!**\n"
                f"Use `!myschedule` here to see your personal slot(s).\n"
                f"The full schedule has been posted in {ann_ch.mention}."
            )

        days_label = ", ".join(DAY_LABELS[d] for d in days)
        await ctx.send(
            f"✅ Schedule published to {ann_ch.mention} — {days_label}.\n"
            + (f"🔓 {lookup_ch.mention} is now **visible** to members." if opened and lookup_ch else "")
        )
        logger.info(f"Schedule published by {ctx.author.name} — days: {days}")

    # ── clear ─────────────────────────────────────────────────────────────────

    @schedule.command(name="clear")
    @_admin_check()
    async def schedule_clear(self, ctx: commands.Context) -> None:
        """Wipe the generated schedule (submissions are kept)."""
        database.save_schedule({})
        await self._set_lookup_visible(ctx.guild, visible=False)
        await ctx.send("🗑️ Schedule cleared. Submissions are still intact.")
        logger.info(f"Schedule cleared by {ctx.author.name}")

    # ════════════════════════════════════════════════════════════════════════
    # !users group
    # ════════════════════════════════════════════════════════════════════════

    @commands.group(name="users", invoke_without_command=True)
    @_admin_check()
    async def users(self, ctx: commands.Context) -> None:
        """Manage registered users. Usage: !users <list|remove>"""
        await ctx.send("Usage: `!users list` or `!users remove @member`")

    @users.command(name="list")
    @_admin_check()
    async def users_list(self, ctx: commands.Context) -> None:
        """List all registered users with their speedups and availability."""
        subs = database.get_all_submissions()
        if not subs:
            await ctx.send("❌ No submissions found.")
            return

        subs_list  = list(subs.values())
        chunk_size = 10

        for i in range(0, len(subs_list), chunk_size):
            chunk = subs_list[i:i+chunk_size]
            embed = discord.Embed(
                title=f"📋 Registered Members ({i+1}-{i+len(chunk)} of {len(subs_list)})",
                color=discord.Color.gold(),
            )
            for sub in chunk:
                sp = sub.get("speedups", {})
                av = sub.get("availability", {})

                sp_parts = [
                    f"{k[:4].title()}: {sp[k]}"
                    for k in ("construction", "research", "training", "general")
                    if k in sp
                ]
                av_parts = [
                    f"{dk}: {'any' if r == [('any','any')] else ', '.join(f'{s}-{e}' for s,e in r)}"
                    for dk in DAY_KEYS if dk in av
                    for r in [av[dk]]
                ]

                embed.add_field(
                    name=f"👤 {sub['username']}",
                    value=(
                        f"⚡ {' | '.join(sp_parts) or '_none_'}\n"
                        f"📅 {' | '.join(av_parts) or '_none_'}"
                    ),
                    inline=False,
                )
            await ctx.send(embed=embed)

    @users.command(name="remove")
    @_admin_check()
    async def users_remove(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Remove a member's submission. Usage: !users remove @member"""
        if not member:
            await ctx.send("❌ Please mention the member to remove. Example: `!users remove @Alice`")
            return

        removed = database.remove_submission(member.id)
        if removed:
            await ctx.send(f"✅ Submission from **{member.display_name}** has been removed.")
            logger.info(f"Submission of {member.name} removed by {ctx.author.name}")
        else:
            await ctx.send(f"❌ **{member.display_name}** has no submission on record.")

    # ════════════════════════════════════════════════════════════════════════
    # !reset
    # ════════════════════════════════════════════════════════════════════════

    @commands.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: commands.Context, confirm: str = None) -> None:
        """
        Wipe ALL submissions, the schedule, and channel config.
        This cannot be undone.  Usage: !reset CONFIRM
        """
        if confirm != "CONFIRM":
            await ctx.send(
                "⚠️ **This will permanently delete all submissions, the schedule, "
                "and channel settings.**\n"
                "To confirm: `!reset CONFIRM`"
            )
            return

        await self._set_lookup_visible(ctx.guild, visible=False)
        database.reset_all()
        await ctx.send("✅ **Full reset complete.** All data has been cleared.")
        logger.info(f"Full reset executed by {ctx.author.name}")

    # ════════════════════════════════════════════════════════════════════════
    # !status
    # ════════════════════════════════════════════════════════════════════════

    @commands.command(name="status")
    @_admin_check()
    async def status(self, ctx: commands.Context) -> None:
        """Show a summary of the current bot state."""
        state = database.get_state()
        subs  = state["submissions"]
        sched = state["schedule"]

        def mention(key: str) -> str:
            cid = state.get(f"channel_{key}")
            ch  = ctx.guild.get_channel(cid) if cid else None
            return ch.mention if ch else "`not configured`"

        embed = discord.Embed(title="📊 Bot Status", color=discord.Color.blurple())
        embed.add_field(
            name="Submissions",
            value=f"{'🟢 Open' if state['accepting_submissions'] else '🔴 Closed'} — {len(subs)} registered",
            inline=False,
        )
        embed.add_field(
            name="Schedule",
            value=(
                f"✅ Generated — {sum(len(v) for v in sched.values())} slot(s)"
                if sched else "❌ Not generated"
            ),
            inline=False,
        )
        embed.add_field(name="Channels", value=(
            f"Submissions: {mention('submissions')}\n"
            f"Admin: {mention('admin')}\n"
            f"Announcements: {mention('announcements')}\n"
            f"My Schedule: {mention('lookup')} "
            f"({'🟢 visible' if state.get('lookup_open') else '🔴 hidden'})"
        ), inline=False)

        await ctx.send(embed=embed)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_days(self, day_arg: str | None) -> list[str] | None:
        """
        Converts an optional day argument to a list of day keys.
        Returns None if the argument is invalid.
        """
        if day_arg is None:
            return DAY_KEYS
        key = DAY_ALIASES.get(day_arg.lower())
        return [key] if key else None

    async def _set_lookup_visible(self, guild: discord.Guild, visible: bool) -> bool:
        """Show or hide #my-schedule for the USER role. Returns True on success."""
        ch_id = database.get_channel("lookup")
        if not ch_id or not (ch := guild.get_channel(ch_id)):
            return False
        
        user_role = discord.utils.get(guild.roles, name="USER")
        if not user_role:
            logger.error("Could not change visibility: 'USER' role not found.")
            return False

        if visible:
            await ch.set_permissions(
                user_role, view_channel=True, send_messages=True, read_message_history=True
            )
        else:
            await ch.set_permissions(user_role, view_channel=False, send_messages=False)
            
        database.set_lookup_open(visible)
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))