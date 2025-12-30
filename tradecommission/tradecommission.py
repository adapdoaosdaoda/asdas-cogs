"""Trade Commission weekly message cog for Where Winds Meet."""
import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list
import pytz

from .views import TradeCommissionView


class TradeCommission(commands.Cog):
    """Send weekly Trade Commission information for Where Winds Meet."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571751,
            force_registration=True,
        )
        default_guild = {
            "channel_id": None,
            "schedule_day": 0,  # 0 = Monday, 6 = Sunday
            "schedule_hour": 9,  # Hour in 24h format
            "schedule_minute": 0,
            "timezone": "UTC",
            "enabled": False,
            "current_message_id": None,
            "current_channel_id": None,
            "trade_info": {
                "option1": {"emoji": "1️⃣", "title": "Option 1", "description": ""},
                "option2": {"emoji": "2️⃣", "title": "Option 2", "description": ""},
                "option3": {"emoji": "3️⃣", "title": "Option 3", "description": ""},
            },
            "active_options": [],  # List of option keys that are currently active
        }
        self.config.register_guild(**default_guild)
        self._task = None
        self._ready = False

    async def cog_load(self):
        """Start the background task when cog loads."""
        await self.bot.wait_until_red_ready()
        self._ready = True
        self._task = asyncio.create_task(self._check_schedule_loop())

    async def cog_unload(self):
        """Cancel background task when cog unloads."""
        if self._task:
            self._task.cancel()

    async def _check_schedule_loop(self):
        """Background loop to check for scheduled messages."""
        await self.bot.wait_until_ready()
        while True:
            try:
                for guild in self.bot.guilds:
                    await self._check_guild_schedule(guild)
                # Check every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in Trade Commission schedule loop: {e}")
                await asyncio.sleep(3600)

    async def _check_guild_schedule(self, guild: discord.Guild):
        """Check if it's time to send the weekly message for a guild."""
        config = await self.config.guild(guild).all()

        if not config["enabled"] or not config["channel_id"]:
            return

        channel = guild.get_channel(config["channel_id"])
        if not channel:
            return

        # Get timezone
        tz = pytz.timezone(config["timezone"])
        now = datetime.now(tz)

        # Check if it's the right day and hour
        if (now.weekday() == config["schedule_day"] and
            now.hour == config["schedule_hour"] and
            now.minute >= config["schedule_minute"] and
            now.minute < config["schedule_minute"] + 60):

            # Check if we already sent a message this week
            last_sent = await self.config.guild(guild).get_raw("last_sent", default=None)
            if last_sent:
                last_sent_dt = datetime.fromisoformat(last_sent)
                if (now - last_sent_dt).days < 7:
                    return

            # Send the weekly message
            await self._send_weekly_message(guild, channel)
            await self.config.guild(guild).last_sent.set(now.isoformat())

    async def _send_weekly_message(self, guild: discord.Guild, channel: discord.TextChannel):
        """Send the weekly Trade Commission message."""
        # Clear active options for new week
        await self.config.guild(guild).active_options.clear()

        embed = discord.Embed(
            title="📊 Weekly Trade Commission - Where Winds Meet",
            description="This week's Trade Commission information will be added soon!\n\nCheck back later for updates.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Where Winds Meet | Trade Commission")

        try:
            message = await channel.send(embed=embed)
            await self.config.guild(guild).current_message_id.set(message.id)
            await self.config.guild(guild).current_channel_id.set(channel.id)
        except discord.Forbidden:
            pass

    @commands.group(name="tradecommission", aliases=["tc"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tradecommission(self, ctx: commands.Context):
        """Manage Trade Commission weekly messages."""
        pass

    @tradecommission.command(name="schedule")
    async def tc_schedule(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        day: str,
        hour: int,
        minute: int = 0,
        timezone: str = "UTC"
    ):
        """
        Schedule weekly Trade Commission messages.

        **Arguments:**
        - `channel`: The channel to send messages to
        - `day`: Day of week (Monday, Tuesday, etc.)
        - `hour`: Hour in 24h format (0-23)
        - `minute`: Minute (0-59), default 0
        - `timezone`: Timezone (e.g., UTC, America/New_York), default UTC

        **Example:**
        - `[p]tc schedule #trade-info Monday 9 0 America/New_York`
        """
        # Validate day
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        day_lower = day.lower()
        if day_lower not in days:
            await ctx.send(f"Invalid day! Use: {humanize_list(list(days.keys()))}")
            return

        # Validate hour and minute
        if not 0 <= hour <= 23:
            await ctx.send("Hour must be between 0 and 23!")
            return
        if not 0 <= minute <= 59:
            await ctx.send("Minute must be between 0 and 59!")
            return

        # Validate timezone
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            await ctx.send(f"Invalid timezone! Use a valid timezone like UTC or America/New_York.")
            return

        # Save config
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.config.guild(ctx.guild).schedule_day.set(days[day_lower])
        await self.config.guild(ctx.guild).schedule_hour.set(hour)
        await self.config.guild(ctx.guild).schedule_minute.set(minute)
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await self.config.guild(ctx.guild).enabled.set(True)

        await ctx.send(
            f"✅ Trade Commission messages scheduled!\n"
            f"**Channel:** {channel.mention}\n"
            f"**Schedule:** Every {day.title()} at {hour:02d}:{minute:02d} {timezone}"
        )

    @tradecommission.command(name="disable")
    async def tc_disable(self, ctx: commands.Context):
        """Disable weekly Trade Commission messages."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("✅ Weekly Trade Commission messages disabled.")

    @tradecommission.command(name="enable")
    async def tc_enable(self, ctx: commands.Context):
        """Enable weekly Trade Commission messages."""
        channel_id = await self.config.guild(ctx.guild).channel_id()
        if not channel_id:
            await ctx.send("❌ Please set up a schedule first using `[p]tc schedule`!")
            return

        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Weekly Trade Commission messages enabled.")

    @tradecommission.command(name="post")
    async def tc_post(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """
        Manually post a Trade Commission message now.

        **Arguments:**
        - `channel`: Optional channel to post to. Uses configured channel if not specified.
        """
        if not channel:
            channel_id = await self.config.guild(ctx.guild).channel_id()
            if not channel_id:
                await ctx.send("❌ No channel configured! Please specify a channel.")
                return
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                await ctx.send("❌ Configured channel not found!")
                return

        await self._send_weekly_message(ctx.guild, channel)
        await ctx.send(f"✅ Posted Trade Commission message to {channel.mention}")

    @tradecommission.command(name="addinfo")
    async def tc_addinfo(self, ctx: commands.Context):
        """
        Add information to the current week's Trade Commission message via reactions.

        This will create an interactive message where you can click up to 3 options
        to add their information to the weekly Trade Commission message.
        """
        current_msg_id = await self.config.guild(ctx.guild).current_message_id()
        current_ch_id = await self.config.guild(ctx.guild).current_channel_id()

        if not current_msg_id or not current_ch_id:
            await ctx.send("❌ No current Trade Commission message found! Use `[p]tc post` first.")
            return

        channel = ctx.guild.get_channel(current_ch_id)
        if not channel:
            await ctx.send("❌ Channel not found!")
            return

        try:
            message = await channel.fetch_message(current_msg_id)
        except discord.NotFound:
            await ctx.send("❌ Message not found!")
            return

        # Create interactive view
        view = TradeCommissionView(self, ctx.guild, message)

        embed = discord.Embed(
            title="📝 Add Trade Commission Information",
            description=(
                "Click the buttons below to add information to this week's Trade Commission message.\n\n"
                "You can select up to **3 options**. Each option will add its configured information "
                "to the weekly message."
            ),
            color=discord.Color.green(),
        )

        # Show current options
        trade_info = await self.config.guild(ctx.guild).trade_info()
        active_options = await self.config.guild(ctx.guild).active_options()

        options_text = []
        for key, info in trade_info.items():
            status = "✅" if key in active_options else "⬜"
            options_text.append(f"{status} {info['emoji']} **{info['title']}**")

        embed.add_field(
            name="Available Options",
            value="\n".join(options_text),
            inline=False
        )

        embed.set_footer(text=f"Selected: {len(active_options)}/3")

        await ctx.send(embed=embed, view=view)

    @tradecommission.command(name="setoption")
    async def tc_setoption(
        self,
        ctx: commands.Context,
        option_number: int,
        title: str,
        *,
        description: str
    ):
        """
        Configure an option's information.

        **Arguments:**
        - `option_number`: Option number (1, 2, or 3)
        - `title`: Title for this option
        - `description`: Description/information to show when this option is selected

        **Example:**
        - `[p]tc setoption 1 "Silk Road" This week's trade route is the Silk Road with 20% bonus on silk items.`
        """
        if option_number not in [1, 2, 3]:
            await ctx.send("❌ Option number must be 1, 2, or 3!")
            return

        option_key = f"option{option_number}"
        async with self.config.guild(ctx.guild).trade_info() as trade_info:
            trade_info[option_key]["title"] = title
            trade_info[option_key]["description"] = description

        await ctx.send(
            f"✅ Option {option_number} configured!\n"
            f"**Title:** {title}\n"
            f"**Description:** {description[:100]}{'...' if len(description) > 100 else ''}"
        )

    @tradecommission.command(name="info")
    async def tc_info(self, ctx: commands.Context):
        """Show current Trade Commission configuration."""
        config = await self.config.guild(ctx.guild).all()

        embed = discord.Embed(
            title="📊 Trade Commission Configuration",
            color=discord.Color.blue(),
        )

        # Schedule info
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        channel = ctx.guild.get_channel(config["channel_id"]) if config["channel_id"] else None

        schedule_text = (
            f"**Status:** {'✅ Enabled' if config['enabled'] else '❌ Disabled'}\n"
            f"**Channel:** {channel.mention if channel else 'Not set'}\n"
            f"**Schedule:** {days[config['schedule_day']]} at {config['schedule_hour']:02d}:{config['schedule_minute']:02d}\n"
            f"**Timezone:** {config['timezone']}"
        )
        embed.add_field(name="Schedule", value=schedule_text, inline=False)

        # Options info
        options_text = []
        for key, info in config["trade_info"].items():
            options_text.append(
                f"{info['emoji']} **{info['title']}**\n"
                f"└ {info['description'][:80]}{'...' if len(info['description']) > 80 else ''}"
            )

        embed.add_field(
            name="Configured Options",
            value="\n\n".join(options_text) if options_text else "No options configured",
            inline=False
        )

        # Current week info
        if config["current_message_id"]:
            current_ch = ctx.guild.get_channel(config["current_channel_id"])
            active_options = config["active_options"]
            current_text = (
                f"**Channel:** {current_ch.mention if current_ch else 'Unknown'}\n"
                f"**Message ID:** {config['current_message_id']}\n"
                f"**Active Options:** {len(active_options)}/3"
            )
            embed.add_field(name="Current Week", value=current_text, inline=False)

        await ctx.send(embed=embed)

    @tradecommission.command(name="testnow")
    @commands.is_owner()
    async def tc_testnow(self, ctx: commands.Context):
        """[Owner only] Test sending the weekly message immediately."""
        channel_id = await self.config.guild(ctx.guild).channel_id()
        if not channel_id:
            await ctx.send("❌ No channel configured!")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Channel not found!")
            return

        await self._send_weekly_message(ctx.guild, channel)
        await ctx.send(f"✅ Test message sent to {channel.mention}")

    async def update_commission_message(self, guild: discord.Guild):
        """Update the current Trade Commission message with active options."""
        config = await self.config.guild(guild).all()

        current_msg_id = config["current_message_id"]
        current_ch_id = config["current_channel_id"]

        if not current_msg_id or not current_ch_id:
            return

        channel = guild.get_channel(current_ch_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(current_msg_id)
        except discord.NotFound:
            return

        # Build embed with active options
        embed = discord.Embed(
            title="📊 Weekly Trade Commission - Where Winds Meet",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow(),
        )

        active_options = config["active_options"]
        trade_info = config["trade_info"]

        if active_options:
            description_parts = ["This week's Trade Commission information:\n"]
            for option_key in active_options:
                info = trade_info[option_key]
                description_parts.append(f"\n{info['emoji']} **{info['title']}**\n{info['description']}")

            embed.description = "\n".join(description_parts)
        else:
            embed.description = "This week's Trade Commission information will be added soon!\n\nCheck back later for updates."

        embed.set_footer(text="Where Winds Meet | Trade Commission")

        try:
            await message.edit(embed=embed)
        except discord.Forbidden:
            pass
