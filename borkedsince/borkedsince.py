"""BorkedSince cog - Track days since last bot crash."""
import asyncio
import discord
from datetime import datetime, timezone
from typing import Optional, List, Dict
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list


class BorkedSince(commands.Cog):
    """Track and display days since the bot last crashed."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571752,
            force_registration=True,
        )

        default_global = {
            "enabled": False,
            "base_bio": "",  # User's base bio text
            "days_since_borked": 0,  # Current streak
            "last_update": None,  # ISO timestamp of last daily update
            "clean_shutdown": False,  # Flag to detect crashes
            "crash_history": [],  # List of crash records
            "longest_streak": 0,  # All-time longest streak
            "total_crashes": 0,  # Total number of crashes detected
            "start_time": None,  # When current streak started
            "update_interval": 86400,  # 24 hours in seconds
        }

        self.config.register_global(**default_global)
        self._task = None
        self._ready = False

    async def cog_load(self):
        """Handle cog initialization."""
        await self.bot.wait_until_red_ready()
        self._ready = True

        # Check if previous shutdown was clean
        await self._check_for_crash()

        # Start the daily update loop if enabled
        if await self.config.enabled():
            self._task = asyncio.create_task(self._daily_update_loop())

    async def cog_unload(self):
        """Handle cog shutdown - mark as clean shutdown."""
        # Mark this as an intentional shutdown
        await self.config.clean_shutdown.set(True)

        # Cancel the update task
        if self._task:
            self._task.cancel()

    async def _check_for_crash(self):
        """Check if the bot crashed on last run."""
        was_clean = await self.config.clean_shutdown()

        if not was_clean:
            # Bot crashed! Record it and reset counter
            current_streak = await self.config.days_since_borked()

            # Only count as crash if we had a streak going (ignore first startup)
            start_time = await self.config.start_time()
            if start_time is not None:
                await self._record_crash(current_streak)

                # Reset counter
                await self.config.days_since_borked.set(0)
                await self.config.start_time.set(datetime.now(timezone.utc).isoformat())

                # Update bio if enabled
                if await self.config.enabled():
                    await self._update_bio()
        else:
            # Clean restart - keep the counter going
            # Check if we need to increment days based on time elapsed
            await self._check_daily_increment()

        # Mark as dirty - if bot crashes before clean shutdown, we'll know
        await self.config.clean_shutdown.set(False)

    async def _record_crash(self, streak_length: int):
        """Record a crash in history."""
        crash_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "streak_length": streak_length,
        }

        async with self.config.crash_history() as history:
            history.append(crash_record)
            # Keep only last 100 crashes
            if len(history) > 100:
                history.pop(0)

        # Update total crashes
        total = await self.config.total_crashes()
        await self.config.total_crashes.set(total + 1)

        # Update longest streak if applicable
        longest = await self.config.longest_streak()
        if streak_length > longest:
            await self.config.longest_streak.set(streak_length)

    async def _check_daily_increment(self):
        """Check if a day has passed and increment counter if needed."""
        last_update = await self.config.last_update()

        if last_update is None:
            # First time - initialize
            await self.config.last_update.set(datetime.now(timezone.utc).isoformat())
            start_time = await self.config.start_time()
            if start_time is None:
                await self.config.start_time.set(datetime.now(timezone.utc).isoformat())
            return

        last_update_dt = datetime.fromisoformat(last_update)
        now = datetime.now(timezone.utc)

        # Calculate days elapsed
        days_elapsed = (now - last_update_dt).days

        if days_elapsed >= 1:
            # Increment the counter
            current_days = await self.config.days_since_borked()
            new_days = current_days + days_elapsed
            await self.config.days_since_borked.set(new_days)
            await self.config.last_update.set(now.isoformat())

            # Update longest streak if applicable
            longest = await self.config.longest_streak()
            if new_days > longest:
                await self.config.longest_streak.set(new_days)

            # Update bio if enabled
            if await self.config.enabled():
                await self._update_bio()

    async def _daily_update_loop(self):
        """Background loop to check for daily increments."""
        await self.bot.wait_until_ready()

        while True:
            try:
                await self._check_daily_increment()

                # Sleep for the configured interval
                interval = await self.config.update_interval()
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in BorkedSince daily update loop: {e}")
                await asyncio.sleep(3600)  # Wait an hour before retrying

    def _format_days(self, days: int) -> str:
        """Format days with period as thousand separator (e.g., 10.000)."""
        return f"{days:,}".replace(",", ".")

    async def _update_bio(self):
        """Update the bot's bio with current streak."""
        days = await self.config.days_since_borked()
        base_bio = await self.config.base_bio()

        # Format the suffix
        days_formatted = self._format_days(days)
        suffix = f"\nLast borked: {days_formatted} day{'s' if days != 1 else ''} ago"

        # Combine and truncate to 190 chars
        full_bio = (base_bio + suffix)[:190]

        try:
            await self.bot.user.edit(bio=full_bio)
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                print("BorkedSince: Rate limited on bio update")
            else:
                print(f"BorkedSince: Error updating bio: {e}")

    def _validate_bio_length(self, base_bio: str) -> tuple[bool, str]:
        """Validate if bio is short enough to fit the maximum possible counter.

        Returns:
            (is_valid, message)
        """
        # Test with 10.000 days as the sample
        test_suffix = "\nLast borked: 10.000 days ago"
        test_full = base_bio + test_suffix

        if len(test_full) > 190:
            overflow = len(test_full) - 190
            return False, (
                f"⚠️ **Bio Length Warning**\n\n"
                f"Your base bio is too long to accommodate large day counts!\n\n"
                f"**Current base bio length:** {len(base_bio)} characters\n"
                f"**Sample with 10.000 days:** {len(test_full)} characters\n"
                f"**Discord limit:** 190 characters\n"
                f"**Overflow:** {overflow} characters\n\n"
                f"**Recommendation:** Reduce your base bio by at least **{overflow}** characters "
                f"to ensure the counter displays correctly even at high day counts.\n\n"
                f"**Sample output:**\n{box(test_full[:190] + '...' if len(test_full) > 190 else test_full)}"
            )

        return True, (
            f"✅ **Bio Length OK**\n\n"
            f"Your bio will display correctly even at 10.000+ days.\n\n"
            f"**Current base bio length:** {len(base_bio)} characters\n"
            f"**Sample with 10.000 days:** {len(test_full)} characters\n"
            f"**Discord limit:** 190 characters\n"
            f"**Remaining space:** {190 - len(test_full)} characters\n\n"
            f"**Sample output:**\n{box(test_full)}"
        )

    @commands.group(name="borkedsince", aliases=["bs"])
    @commands.is_owner()
    async def borkedsince(self, ctx: commands.Context):
        """
        Manage the BorkedSince bot uptime tracker.

        Tracks days since the bot last crashed and displays it in the bot's About Me section.
        """
        pass

    @borkedsince.command(name="enable")
    async def bs_enable(self, ctx: commands.Context):
        """Enable the BorkedSince counter and bio updates."""
        # Check if base bio is set
        base_bio = await self.config.base_bio()
        if not base_bio:
            await ctx.send(
                "❌ Please set a base bio first using `[p]borkedsince setbio <text>`\n\n"
                "The base bio is the main text that will appear in your bot's About Me, "
                "before the 'Last borked: X days ago' suffix is added."
            )
            return

        await self.config.enabled.set(True)

        # Initialize start time if not set
        start_time = await self.config.start_time()
        if start_time is None:
            await self.config.start_time.set(datetime.now(timezone.utc).isoformat())

        # Start the update loop
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._daily_update_loop())

        # Update bio immediately
        await self._update_bio()

        days = await self.config.days_since_borked()
        await ctx.send(
            f"✅ BorkedSince enabled!\n\n"
            f"Current streak: **{days}** day{'s' if days != 1 else ''}\n"
            f"Bot bio has been updated."
        )

    @borkedsince.command(name="disable")
    async def bs_disable(self, ctx: commands.Context):
        """Disable bio updates (counter continues in background)."""
        await self.config.enabled.set(False)

        # Cancel the update task
        if self._task:
            self._task.cancel()

        await ctx.send(
            "✅ BorkedSince bio updates disabled.\n\n"
            "The counter will continue tracking in the background.\n"
            "Use `[p]borkedsince enable` to resume bio updates."
        )

    @borkedsince.command(name="setbio")
    async def bs_setbio(self, ctx: commands.Context, *, bio_text: str):
        """Set the base bio text (before the counter suffix).

        **Arguments:**
        - `bio_text`: The main text for your bot's About Me

        **Example:**
        - `[p]borkedsince setbio Serving Discord servers since 2024!`

        **Note:** The suffix "Last borked: X days ago" will be automatically added.
        """
        # Validate length
        is_valid, message = self._validate_bio_length(bio_text)

        # Save the bio
        await self.config.base_bio.set(bio_text)

        # Send validation message
        await ctx.send(message)

        # Update bio if enabled
        if await self.config.enabled():
            await self._update_bio()
            await ctx.send("Bio has been updated on Discord.")

    @borkedsince.command(name="reset")
    async def bs_reset(self, ctx: commands.Context, *, reason: Optional[str] = None):
        """Manually reset the counter to 0 (e.g., after fixing a bug).

        **Arguments:**
        - `reason`: Optional reason for the reset

        **Example:**
        - `[p]borkedsince reset Fixed memory leak in event handler`
        """
        # Record current streak as a "crash" for history
        current_streak = await self.config.days_since_borked()

        if current_streak > 0:
            await self._record_crash(current_streak)

        # Reset counter
        await self.config.days_since_borked.set(0)
        await self.config.start_time.set(datetime.now(timezone.utc).isoformat())
        await self.config.last_update.set(datetime.now(timezone.utc).isoformat())

        # Update bio if enabled
        if await self.config.enabled():
            await self._update_bio()

        reason_text = f"\n**Reason:** {reason}" if reason else ""
        await ctx.send(
            f"✅ Counter reset to 0 days!\n"
            f"**Previous streak:** {current_streak} day{'s' if current_streak != 1 else ''}{reason_text}"
        )

    @borkedsince.command(name="info")
    async def bs_info(self, ctx: commands.Context):
        """Show current BorkedSince status and statistics."""
        config = await self.config.all()

        embed = discord.Embed(
            title="📊 BorkedSince Status",
            color=discord.Color.green() if config["enabled"] else discord.Color.greyple(),
        )

        # Current streak info
        days = config["days_since_borked"]
        days_formatted = self._format_days(days)

        start_time = config["start_time"]
        if start_time:
            start_dt = datetime.fromisoformat(start_time)
            start_text = f"<t:{int(start_dt.timestamp())}:R>"
        else:
            start_text = "Not started"

        streak_text = (
            f"**Current Streak:** {days_formatted} day{'s' if days != 1 else ''}\n"
            f"**Started:** {start_text}\n"
            f"**Status:** {'✅ Enabled' if config['enabled'] else '❌ Disabled'}"
        )
        embed.add_field(name="Current Status", value=streak_text, inline=False)

        # All-time stats
        longest = config["longest_streak"]
        longest_formatted = self._format_days(longest)
        total_crashes = config["total_crashes"]

        stats_text = (
            f"**Longest Streak:** {longest_formatted} day{'s' if longest != 1 else ''}\n"
            f"**Total Crashes:** {total_crashes}\n"
            f"**Crash History:** {len(config['crash_history'])} recorded"
        )
        embed.add_field(name="All-Time Statistics", value=stats_text, inline=False)

        # Bio preview
        if config["base_bio"]:
            suffix = f"\nLast borked: {days_formatted} day{'s' if days != 1 else ''} ago"
            full_bio = (config["base_bio"] + suffix)[:190]

            is_valid, _ = self._validate_bio_length(config["base_bio"])
            validation_emoji = "✅" if is_valid else "⚠️"

            embed.add_field(
                name=f"Bio Preview {validation_emoji}",
                value=box(full_bio),
                inline=False
            )

            if not is_valid:
                embed.set_footer(text="⚠️ Bio may be truncated at high day counts. Use [p]borkedsince setbio to check.")
        else:
            embed.add_field(
                name="Bio Preview",
                value="*No base bio set*\nUse `[p]borkedsince setbio` to set one.",
                inline=False
            )

        await ctx.send(embed=embed)

    @borkedsince.command(name="history")
    async def bs_history(self, ctx: commands.Context, limit: int = 10):
        """Show crash history with longest streaks.

        **Arguments:**
        - `limit`: Number of entries to show (default: 10, max: 50)

        **Example:**
        - `[p]borkedsince history` - Show last 10 crashes
        - `[p]borkedsince history 20` - Show last 20 crashes
        """
        if limit < 1:
            limit = 1
        elif limit > 50:
            limit = 50

        crash_history = await self.config.crash_history()

        if not crash_history:
            await ctx.send(
                "✅ No crashes recorded!\n\n"
                "Your bot has either never crashed, or you recently started using this cog."
            )
            return

        # Sort by streak length (descending) for highscores
        sorted_crashes = sorted(crash_history, key=lambda x: x["streak_length"], reverse=True)

        embed = discord.Embed(
            title="🏆 Crash History - Longest Streaks",
            description=f"Showing top {min(limit, len(sorted_crashes))} longest streaks before crashes",
            color=discord.Color.gold(),
        )

        # Show top streaks
        for i, crash in enumerate(sorted_crashes[:limit], 1):
            timestamp = datetime.fromisoformat(crash["timestamp"])
            streak = crash["streak_length"]
            streak_formatted = self._format_days(streak)

            # Medal emojis for top 3
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
                value=f"Crashed <t:{int(timestamp.timestamp())}:R>",
                inline=False
            )

        # Add summary footer
        total_crashes = len(crash_history)
        longest = await self.config.longest_streak()
        longest_formatted = self._format_days(longest)

        embed.set_footer(
            text=f"Total crashes recorded: {total_crashes} | "
                 f"All-time longest: {longest_formatted} days"
        )

        await ctx.send(embed=embed)

    @borkedsince.command(name="recent")
    async def bs_recent(self, ctx: commands.Context, limit: int = 10):
        """Show most recent crashes chronologically.

        **Arguments:**
        - `limit`: Number of entries to show (default: 10, max: 50)

        **Example:**
        - `[p]borkedsince recent` - Show last 10 crashes
        - `[p]borkedsince recent 20` - Show last 20 crashes
        """
        if limit < 1:
            limit = 1
        elif limit > 50:
            limit = 50

        crash_history = await self.config.crash_history()

        if not crash_history:
            await ctx.send(
                "✅ No crashes recorded!\n\n"
                "Your bot has either never crashed, or you recently started using this cog."
            )
            return

        # Reverse to show most recent first
        recent_crashes = list(reversed(crash_history[-limit:]))

        embed = discord.Embed(
            title="📋 Recent Crash History",
            description=f"Showing last {len(recent_crashes)} crash{'es' if len(recent_crashes) != 1 else ''}",
            color=discord.Color.red(),
        )

        for i, crash in enumerate(recent_crashes, 1):
            timestamp = datetime.fromisoformat(crash["timestamp"])
            streak = crash["streak_length"]
            streak_formatted = self._format_days(streak)

            embed.add_field(
                name=f"Crash #{len(crash_history) - (limit - i) if len(crash_history) > limit else len(crash_history) - i + 1}",
                value=(
                    f"**Streak lost:** {streak_formatted} day{'s' if streak != 1 else ''}\n"
                    f"**When:** <t:{int(timestamp.timestamp())}:R>"
                ),
                inline=False
            )

        total_crashes = len(crash_history)
        embed.set_footer(text=f"Total crashes recorded: {total_crashes}")

        await ctx.send(embed=embed)

    @borkedsince.command(name="checkbio")
    async def bs_checkbio(self, ctx: commands.Context):
        """Check if your current base bio will fit the 10.000 days format."""
        base_bio = await self.config.base_bio()

        if not base_bio:
            await ctx.send(
                "❌ No base bio set!\n\n"
                "Use `[p]borkedsince setbio <text>` to set your base bio first."
            )
            return

        is_valid, message = self._validate_bio_length(base_bio)
        await ctx.send(message)

    @borkedsince.command(name="updatenow")
    async def bs_updatenow(self, ctx: commands.Context):
        """Manually trigger a bio update immediately."""
        if not await self.config.enabled():
            await ctx.send(
                "❌ BorkedSince is currently disabled!\n\n"
                "Enable it first with `[p]borkedsince enable`"
            )
            return

        await self._update_bio()
        days = await self.config.days_since_borked()
        days_formatted = self._format_days(days)

        await ctx.send(
            f"✅ Bio updated!\n\n"
            f"Current streak: **{days_formatted}** day{'s' if days != 1 else ''}"
        )
