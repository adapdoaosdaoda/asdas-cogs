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
            "previous_state": None,
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

    @commands.command(name="bork")
    @commands.is_owner()
    async def bork(self, ctx: commands.Context, target: str, *, reason: Optional[str] = None):
        """Mark Luo or Melon (the bot) as 'borked'.

        - `!bork luo [reason]`: Reset Luo's personal streak.
        - `!bork melon [reason]`: Reset the bot's crash counter (BorkedSince).
        """
        if target.lower() == "melon":
            bs_command = self.bot.get_command("borkedsince reset")
            if bs_command:
                await ctx.invoke(bs_command, reason=reason)
            else:
                await ctx.send("Could not find BorkedSince reset command.")
            return

        if target.lower() == "luo":
            user_config = self.config.user(ctx.author)
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
                f"✅ **{ctx.author.display_name}** (Luo) has borked! Streak of **{streak_days}** days lost.{reason_text}\n"
                f"Use `{ctx.prefix}undo luo` if this was a mistake."
            )
        else:
            await ctx.send("Invalid target. Use `!bork luo` or `!bork melon`.")

    @commands.command(name="undo")
    @commands.is_owner()
    async def undo(self, ctx: commands.Context, target: str):
        """Undo the last bork for Luo or Melon.

        - `!undo luo`: Restore Luo's streak.
        - `!undo melon`: Restore the bot's counter (BorkedSince).
        """
        if target.lower() == "melon":
            bs_command = self.bot.get_command("borkedsince undo")
            if bs_command:
                await ctx.invoke(bs_command)
            else:
                await ctx.send("Could not find BorkedSince undo command.")
            return

        if target.lower() == "luo":
            user_config = self.config.user(ctx.author)
            previous_state = await user_config.previous_state()
            if not previous_state:
                await ctx.send("No previous state found for Luo to undo.")
                return

            await user_config.last_borked.set(previous_state["last_borked"])
            await user_config.total_borks.set(previous_state["total_borks"])
            await user_config.previous_state.set(None)
            async with user_config.bork_history() as history:
                if history: history.pop()

            await ctx.send("✅ Luo's last bork has been undone and the streak restored!")
        else:
            await ctx.send("Invalid target. Use `!undo luo` or `!undo melon`.")

    @commands.command(name="borked")
    async def borked(self, ctx: commands.Context, *, user_or_keyword: Optional[str] = None):
        """Check how long it has been since a user last borked.

        - `!borked luo`: Show Luo's bork status.
        - `!borked melon`: Show the bot's crash history (BorkedSince history).
        """
        if user_or_keyword and user_or_keyword.lower() == "melon":
            bs_command = self.bot.get_command("borkedsince history")
            if bs_command:
                await ctx.invoke(bs_command)
            else:
                await ctx.send("Could not find BorkedSince history command.")
            return

        target_user = None
        if not user_or_keyword or user_or_keyword.lower() == "luo":
            if self.bot.owner_ids:
                owner_id = list(self.bot.owner_ids)[0]
                target_user = self.bot.get_user(owner_id)
            else:
                target_user = ctx.author
        else:
            try:
                target_user = await commands.UserConverter().convert(ctx, user_or_keyword)
            except commands.BadArgument:
                await ctx.send(f"Could not find user '{user_or_keyword}'.")
                return

        if not target_user:
            await ctx.send("Could not determine target user.")
            return
        
        user_config = self.config.user(target_user)
        last_borked = await user_config.last_borked()

        if not last_borked:
            is_target_owner = await self.bot.is_owner(target_user)
            if is_target_owner:
                await ctx.send(f"**{target_user.display_name}** has never borked!")
            else:
                await ctx.send(f"**{target_user.display_name}** is not a bot owner.")
            return

        days = self._get_days_since(last_borked)
        await ctx.send(f"**{target_user.display_name}** last borked **{self._format_days(days)}** day{'s' if days != 1 else ''} ago.")

    @commands.group(name="pborkset")
    @commands.is_owner()
    async def pborkset(self, ctx: commands.Context):
        """Manage PersonalBork settings."""
        pass

    @pborkset.command(name="stats")
    async def pborkset_stats(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Show bork statistics for a user."""
        target = user or ctx.author
        user_config = self.config.user(target)
        data = await user_config.all()
        if not data["last_borked"]:
            await ctx.send(f"No bork data found for {target.display_name}.")
            return

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
