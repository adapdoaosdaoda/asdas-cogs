"""PersonalBork cog - Track days since owners last borked."""
import discord
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Union
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list


class PersonalBork(commands.Cog):
    """Track and display days since owners last borked."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571753,
            force_registration=True,
        )

        default_user = {
            "last_borked": None,
            "bork_history": [],
            "longest_streak": 0,
            "total_borks": 0,
            "previous_state": {},
        }

        self.config.register_user(**default_user)

    def _format_days(self, days: int) -> str:
        """Format days with period as thousand separator."""
        return f"{days:,}".replace(",", ".")

    def _get_days_since(self, timestamp: str) -> int:
        """Calculate full days since a given ISO timestamp."""
        if not timestamp:
            return 0
        last_dt = datetime.fromisoformat(timestamp)
        now = datetime.now(timezone.utc)
        return (now - last_dt).days

    BORK_ROLE_IDS = (1439747785644703754, 1452430729115078850)

    def _has_bork_role(self, member: discord.Member) -> bool:
        return any(r.id in self.BORK_ROLE_IDS for r in getattr(member, "roles", []))

    @commands.hybrid_group(name="bork")
    async def bork(self, ctx: commands.Context):
        """Mark a member or the bot itself as 'borked'."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @bork.command(name="member")
    @commands.guild_only()
    async def bork_member(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        """Reset a member's bork streak.

        - `!bork member @user [reason]`
        """
        if not self._has_bork_role(ctx.author):
            await ctx.send("❌ You do not have permission to use this command.", ephemeral=True)
            return

        user_config = self.config.user(member)
        data = await user_config.all()
        last_borked = data["last_borked"]

        streak_days = self._get_days_since(last_borked) if last_borked else 0
        if last_borked and streak_days > data["longest_streak"]:
            await user_config.longest_streak.set(streak_days)

        await user_config.previous_state.set({
            "last_borked": last_borked,
            "total_borks": data["total_borks"],
        })

        now = datetime.now(timezone.utc).isoformat()
        async with user_config.bork_history() as history:
            history.append({"timestamp": now, "streak_length": streak_days, "reason": reason})
            if len(history) > 100: history.pop(0)

        await user_config.last_borked.set(now)
        await user_config.total_borks.set(data["total_borks"] + 1)

        reason_text = f" Reason: {reason}" if reason else ""
        await ctx.send(
            f"✅ **{member.display_name}** has borked! Streak of **{streak_days}** days lost.{reason_text}\n"
            f"Use `{ctx.prefix}undo member {member.mention}` if this was a mistake."
        )

    @bork.command(name="melon")
    @commands.is_owner()
    async def bork_melon(self, ctx: commands.Context, *, reason: Optional[str] = None):
        """Reset the bot's crash counter (BorkedSince). Bot Owner only."""
        bs_command = self.bot.get_command("borkedsince reset")
        if bs_command:
            await ctx.invoke(bs_command, reason=reason)
        else:
            await ctx.send("Could not find BorkedSince reset command.")

    @commands.hybrid_group(name="undo")
    async def undo(self, ctx: commands.Context):
        """Undo the last bork for a member or the bot itself."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @undo.command(name="member")
    @commands.guild_only()
    async def undo_member(self, ctx: commands.Context, member: discord.Member):
        """Undo a member's last bork, restoring their previous streak.

        - `!undo member @user`
        """
        if ctx.author.id != member.id and not self._has_bork_role(ctx.author):
            await ctx.send("❌ You do not have permission to undo another member's bork.", ephemeral=True)
            return

        user_config = self.config.user(member)
        previous_state = await user_config.previous_state()
        if not previous_state:
            await ctx.send(f"No previous state found for **{member.display_name}** to undo.")
            return

        await user_config.last_borked.set(previous_state["last_borked"])
        await user_config.total_borks.set(previous_state["total_borks"])
        await user_config.previous_state.set({})
        async with user_config.bork_history() as history:
            if history: history.pop()

        await ctx.send(f"✅ **{member.display_name}**'s last bork has been undone and the streak restored!")

    @undo.command(name="melon")
    @commands.is_owner()
    async def undo_melon(self, ctx: commands.Context):
        """Undo the bot's last crash reset (BorkedSince). Bot Owner only."""
        bs_command = self.bot.get_command("borkedsince undo")
        if bs_command:
            await ctx.invoke(bs_command)
        else:
            await ctx.send("Could not find BorkedSince undo command.")

    async def _build_stats_embed(self, target: discord.abc.User) -> Optional[discord.Embed]:
        """Build the bork stats embed for a user, or None if they have no data."""
        user_config = self.config.user(target)
        data = await user_config.all()
        if not data["last_borked"]:
            return None

        days = self._get_days_since(data["last_borked"])
        embed = discord.Embed(title=f"📊 Bork Stats: {target.display_name}", color=discord.Color.blue())
        embed.add_field(name="Current Streak", value=f"{days} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"{data['longest_streak']} days", inline=True)
        embed.add_field(name="Total Borks", value=data["total_borks"], inline=True)

        if data["bork_history"]:
            history_text = ""
            for b in reversed(data["bork_history"][-5:]):
                ts = int(datetime.fromisoformat(b["timestamp"]).timestamp())
                history_text += f"<t:{ts}:d>: {b['streak_length']} days" + (f" ({b['reason']})" if b.get('reason') else "") + "\n"
            embed.add_field(name="Recent History", value=history_text, inline=False)
        return embed

    @commands.hybrid_command(name="borked")
    @commands.guild_only()
    async def borked(self, ctx: commands.Context, member: discord.Member):
        """Check a member's bork stats.

        - `!borked @user`
        """
        if not self._has_bork_role(ctx.author):
            await ctx.send("❌ You do not have permission to use this command.", ephemeral=True)
            return

        embed = await self._build_stats_embed(member)
        if embed is None:
            await ctx.send(f"No bork data found for **{member.display_name}**.", ephemeral=True)
            return

        await ctx.send(embed=embed, ephemeral=True)

    @commands.group(name="pborkset")
    @commands.is_owner()
    async def pborkset(self, ctx: commands.Context):
        """Manage PersonalBork settings."""
        pass

    @pborkset.command(name="stats")
    async def pborkset_stats(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Show bork statistics for a user."""
        target = user or ctx.author
        embed = await self._build_stats_embed(target)
        if embed is None:
            await ctx.send(f"No bork data found for {target.display_name}.")
            return
        await ctx.send(embed=embed)

    @pborkset.command(name="clear")
    @commands.is_owner()
    async def pborkset_clear(self, ctx: commands.Context, user: discord.User):
        """Clear bork data for a user."""
        await self.config.user(user).clear()
        await ctx.send(f"✅ Cleared bork data for {user.display_name}.")

    @pborkset.command(name="setdate")
    @commands.is_owner()
    async def pborkset_setdate(self, ctx: commands.Context, days_ago: int, user: Optional[discord.User] = None):
        """Manually set the last borked date to X days ago."""
        target = user or ctx.author
        if days_ago < 0:
            await ctx.send("Days ago must be a positive number.")
            return
        bork_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
        await self.config.user(target).last_borked.set(bork_date.isoformat())
        await ctx.send(f"✅ Set last borked date for **{target.display_name}** to {days_ago} days ago.")
