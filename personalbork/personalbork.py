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

    async def _show_luo_history(self, ctx: commands.Context, limit: int):
        """Show Luo's bork history in an embed identical to borkedsince history."""
        if limit < 1:
            limit = 1
        elif limit > 50:
            limit = 50

        # Get Luo (first owner)
        target_user = None
        if self.bot.owner_ids:
            owner_id = list(self.bot.owner_ids)[0]
            target_user = self.bot.get_user(owner_id)
        
        if not target_user:
            target_user = ctx.author

        user_config = self.config.user(target_user)
        bork_history = await user_config.bork_history()

        if not bork_history:
            await ctx.send(
                f"✅ **{target_user.display_name}** has no borks recorded!\n\n"
                "Either they have never borked, or history was recently cleared."
            )
            return

        # Sort by streak length (descending) for highscores
        sorted_borks = sorted(bork_history, key=lambda x: x["streak_length"], reverse=True)

        # Determine embed color: bot's role color in guild, or #58b99c fallback
        embed_color = discord.Color(0x58b99c)
        if ctx.guild and ctx.guild.me:
            bot_color = ctx.guild.me.color
            if bot_color.value != 0:
                embed_color = bot_color

        embed = discord.Embed(
            title="🏆 Bork History - Longest Streaks",
            description=f"Showing top {min(limit, len(sorted_borks))} longest streaks before borking",
            color=embed_color,
        )

        for i, bork in enumerate(sorted_borks[:limit], 1):
            timestamp = datetime.fromisoformat(bork["timestamp"])
            streak = bork["streak_length"]
            streak_formatted = self._format_days(streak)

            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"#{i}"

            embed.add_field(
                name=f"{emoji} {streak_formatted} day{'s' if streak != 1 else ''}",
                value=f"Borked <t:{int(timestamp.timestamp())}:R>",
                inline=False
            )

        total_borks = len(bork_history)
        embed.set_footer(text=f"Borks on record: {total_borks}")

        await ctx.send(embed=embed)

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
    async def borked(self, ctx: commands.Context, target: str, limit: int = 10):
        """Check how long it has been since a user last borked.

        - `!borked luo [limit]`: Show Luo's bork history.
        - `!borked melon [limit]`: Show the bot's crash history (BorkedSince history).
        - `!borked <user>`: Check how long ago a specific user last borked.
        """
        if target.lower() == "melon":
            bs_command = self.bot.get_command("borkedsince history")
            if bs_command:
                await ctx.invoke(bs_command, limit=limit)
            else:
                await ctx.send("Could not find BorkedSince history command.")
            return

        if target.lower() == "luo":
            await self._show_luo_history(ctx, limit)
            return

        try:
            target_user = await commands.UserConverter().convert(ctx, target)
        except commands.BadArgument:
            await ctx.send(f"Could not find user '{target}'.")
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
