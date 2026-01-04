import asyncio
import discord
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional
import pytz


class TC(commands.Cog):
    """Turnip Calculator - Scheduled notifications for Animal Crossing turnip market."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890123, force_registration=True)

        default_guild = {
            "channel_id": None,
            "enabled": False,
            "timezone": "Europe/Amsterdam",

            # Sunday pre-shop restock notification
            "sunday_enabled": True,
            "sunday_hour": 19,
            "sunday_minute": 0,
            "sunday_message": "🔔 **Turnip Pre-Shop Restock Reminder!**\n\nDaisy Mae will be selling turnips tomorrow morning! Get ready to buy your turnips! 🌱",
            "sunday_ping_role_id": None,

            # Wednesday sell recommendation notification
            "wednesday_enabled": True,
            "wednesday_hour": 19,
            "wednesday_minute": 0,
            "wednesday_message": "📈 **Mid-Week Turnip Check!**\n\nIt's Wednesday! Check your turnip prices - this is a good time to sell if you have a good price! 💰",
            "wednesday_ping_role_id": None,
        }

        self.config.register_guild(**default_guild)
        self.check_task = None

    async def cog_load(self):
        """Start the background task when the cog loads."""
        self.check_task = asyncio.create_task(self._check_schedule_loop())

    async def cog_unload(self):
        """Cancel the background task when the cog unloads."""
        if self.check_task:
            self.check_task.cancel()

    async def _check_schedule_loop(self):
        """Background loop to check for scheduled notifications."""
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
                print(f"Error in TC schedule loop: {e}")
                await asyncio.sleep(3600)

    async def _check_guild_schedule(self, guild: discord.Guild):
        """Check if it's time to send a scheduled notification for a guild."""
        guild_config = await self.config.guild(guild).all()

        if not guild_config["enabled"]:
            return

        channel_id = guild_config["channel_id"]
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Get current time in the configured timezone
        tz = pytz.timezone(guild_config["timezone"])
        now = datetime.now(tz)
        current_weekday = now.weekday()  # 0=Monday, 6=Sunday
        current_hour = now.hour
        current_minute = now.minute

        # Check Sunday notification (weekday 6 = Sunday)
        if (guild_config["sunday_enabled"] and
            current_weekday == 6 and
            current_hour == guild_config["sunday_hour"] and
            current_minute == guild_config["sunday_minute"]):
            await self._send_notification(
                channel,
                guild_config["sunday_message"],
                guild_config["sunday_ping_role_id"],
                guild
            )

        # Check Wednesday notification (weekday 2 = Wednesday)
        if (guild_config["wednesday_enabled"] and
            current_weekday == 2 and
            current_hour == guild_config["wednesday_hour"] and
            current_minute == guild_config["wednesday_minute"]):
            await self._send_notification(
                channel,
                guild_config["wednesday_message"],
                guild_config["wednesday_ping_role_id"],
                guild
            )

    async def _send_notification(
        self,
        channel: discord.TextChannel,
        message: str,
        ping_role_id: Optional[int],
        guild: discord.Guild
    ):
        """Send a notification message to the channel."""
        try:
            content = message

            # Add role ping if configured
            if ping_role_id:
                role = guild.get_role(ping_role_id)
                if role:
                    content = f"{role.mention}\n\n{content}"

            await channel.send(content)
        except discord.Forbidden:
            print(f"Missing permissions to send notification in {channel.name}")
        except discord.HTTPException as e:
            print(f"Error sending notification: {e}")

    @commands.group(name="tc")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_group(self, ctx: commands.Context):
        """Turnip Calculator notification settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tc_group.command(name="channel")
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel for turnip notifications.

        **Arguments:**
        - `channel` - The channel where notifications will be sent
        """
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ Turnip notifications will be sent to {channel.mention}")

    @tc_group.command(name="timezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone for scheduled notifications.

        **Arguments:**
        - `timezone` - Timezone string (e.g., 'Europe/Amsterdam', 'America/New_York')

        **Example:**
        - `[p]tc timezone Europe/Amsterdam`
        """
        try:
            pytz.timezone(timezone)  # Validate timezone
            await self.config.guild(ctx.guild).timezone.set(timezone)
            await ctx.send(f"✅ Timezone set to {timezone}")
        except pytz.exceptions.UnknownTimeZoneError:
            await ctx.send(f"❌ Invalid timezone: {timezone}\nPlease use a valid timezone from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")

    @tc_group.command(name="enable")
    async def enable(self, ctx: commands.Context):
        """Enable turnip notifications."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Turnip notifications enabled!")

    @tc_group.command(name="disable")
    async def disable(self, ctx: commands.Context):
        """Disable turnip notifications."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("✅ Turnip notifications disabled.")

    @tc_group.group(name="sunday")
    async def sunday_group(self, ctx: commands.Context):
        """Configure Sunday pre-shop restock notifications."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @sunday_group.command(name="enable")
    async def sunday_enable(self, ctx: commands.Context):
        """Enable Sunday notifications."""
        await self.config.guild(ctx.guild).sunday_enabled.set(True)
        await ctx.send("✅ Sunday pre-shop notifications enabled!")

    @sunday_group.command(name="disable")
    async def sunday_disable(self, ctx: commands.Context):
        """Disable Sunday notifications."""
        await self.config.guild(ctx.guild).sunday_enabled.set(False)
        await ctx.send("✅ Sunday pre-shop notifications disabled.")

    @sunday_group.command(name="time")
    async def sunday_time(self, ctx: commands.Context, hour: int, minute: int = 0):
        """Set the time for Sunday notifications.

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23)
        - `minute` - Minute (0-59), defaults to 0

        **Example:**
        - `[p]tc sunday time 19 0` - Set to 19:00
        """
        if not 0 <= hour <= 23:
            await ctx.send("❌ Hour must be between 0 and 23")
            return
        if not 0 <= minute <= 59:
            await ctx.send("❌ Minute must be between 0 and 59")
            return

        await self.config.guild(ctx.guild).sunday_hour.set(hour)
        await self.config.guild(ctx.guild).sunday_minute.set(minute)
        await ctx.send(f"✅ Sunday notification time set to {hour:02d}:{minute:02d}")

    @sunday_group.command(name="message")
    async def sunday_message(self, ctx: commands.Context, *, message: str):
        """Set the message for Sunday notifications.

        **Arguments:**
        - `message` - The message to send

        **Example:**
        - `[p]tc sunday message Turnips available tomorrow! Get ready!`
        """
        await self.config.guild(ctx.guild).sunday_message.set(message)
        await ctx.send("✅ Sunday notification message updated!")

    @sunday_group.command(name="pingrole")
    async def sunday_pingrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set a role to ping with Sunday notifications.

        **Arguments:**
        - `role` - The role to ping (leave empty to remove)
        """
        if role:
            await self.config.guild(ctx.guild).sunday_ping_role_id.set(role.id)
            await ctx.send(f"✅ Sunday notifications will ping {role.mention}")
        else:
            await self.config.guild(ctx.guild).sunday_ping_role_id.set(None)
            await ctx.send("✅ Sunday notifications will not ping any role")

    @tc_group.group(name="wednesday")
    async def wednesday_group(self, ctx: commands.Context):
        """Configure Wednesday sell recommendation notifications."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @wednesday_group.command(name="enable")
    async def wednesday_enable(self, ctx: commands.Context):
        """Enable Wednesday notifications."""
        await self.config.guild(ctx.guild).wednesday_enabled.set(True)
        await ctx.send("✅ Wednesday sell notifications enabled!")

    @wednesday_group.command(name="disable")
    async def wednesday_disable(self, ctx: commands.Context):
        """Disable Wednesday notifications."""
        await self.config.guild(ctx.guild).wednesday_enabled.set(False)
        await ctx.send("✅ Wednesday sell notifications disabled.")

    @wednesday_group.command(name="time")
    async def wednesday_time(self, ctx: commands.Context, hour: int, minute: int = 0):
        """Set the time for Wednesday notifications.

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23)
        - `minute` - Minute (0-59), defaults to 0

        **Example:**
        - `[p]tc wednesday time 19 0` - Set to 19:00
        """
        if not 0 <= hour <= 23:
            await ctx.send("❌ Hour must be between 0 and 23")
            return
        if not 0 <= minute <= 59:
            await ctx.send("❌ Minute must be between 0 and 59")
            return

        await self.config.guild(ctx.guild).wednesday_hour.set(hour)
        await self.config.guild(ctx.guild).wednesday_minute.set(minute)
        await ctx.send(f"✅ Wednesday notification time set to {hour:02d}:{minute:02d}")

    @wednesday_group.command(name="message")
    async def wednesday_message(self, ctx: commands.Context, *, message: str):
        """Set the message for Wednesday notifications.

        **Arguments:**
        - `message` - The message to send

        **Example:**
        - `[p]tc wednesday message Check your turnip prices! Time to sell!`
        """
        await self.config.guild(ctx.guild).wednesday_message.set(message)
        await ctx.send("✅ Wednesday notification message updated!")

    @wednesday_group.command(name="pingrole")
    async def wednesday_pingrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set a role to ping with Wednesday notifications.

        **Arguments:**
        - `role` - The role to ping (leave empty to remove)
        """
        if role:
            await self.config.guild(ctx.guild).wednesday_ping_role_id.set(role.id)
            await ctx.send(f"✅ Wednesday notifications will ping {role.mention}")
        else:
            await self.config.guild(ctx.guild).wednesday_ping_role_id.set(None)
            await ctx.send("✅ Wednesday notifications will not ping any role")

    @tc_group.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current turnip notification settings."""
        guild_config = await self.config.guild(ctx.guild).all()

        channel = ctx.guild.get_channel(guild_config["channel_id"]) if guild_config["channel_id"] else None
        channel_text = channel.mention if channel else "Not set"

        sunday_role = ctx.guild.get_role(guild_config["sunday_ping_role_id"]) if guild_config["sunday_ping_role_id"] else None
        sunday_role_text = sunday_role.mention if sunday_role else "None"

        wednesday_role = ctx.guild.get_role(guild_config["wednesday_ping_role_id"]) if guild_config["wednesday_ping_role_id"] else None
        wednesday_role_text = wednesday_role.mention if wednesday_role else "None"

        embed = discord.Embed(
            title="🌱 Turnip Calculator Settings",
            color=discord.Color.green() if guild_config["enabled"] else discord.Color.red()
        )

        embed.add_field(
            name="General Settings",
            value=f"**Status:** {'✅ Enabled' if guild_config['enabled'] else '❌ Disabled'}\n"
                  f"**Channel:** {channel_text}\n"
                  f"**Timezone:** {guild_config['timezone']}",
            inline=False
        )

        embed.add_field(
            name="📅 Sunday Pre-Shop Restock",
            value=f"**Enabled:** {'✅ Yes' if guild_config['sunday_enabled'] else '❌ No'}\n"
                  f"**Time:** {guild_config['sunday_hour']:02d}:{guild_config['sunday_minute']:02d}\n"
                  f"**Ping Role:** {sunday_role_text}\n"
                  f"**Message:** {guild_config['sunday_message'][:100]}{'...' if len(guild_config['sunday_message']) > 100 else ''}",
            inline=False
        )

        embed.add_field(
            name="📅 Wednesday Sell Recommendation",
            value=f"**Enabled:** {'✅ Yes' if guild_config['wednesday_enabled'] else '❌ No'}\n"
                  f"**Time:** {guild_config['wednesday_hour']:02d}:{guild_config['wednesday_minute']:02d}\n"
                  f"**Ping Role:** {wednesday_role_text}\n"
                  f"**Message:** {guild_config['wednesday_message'][:100]}{'...' if len(guild_config['wednesday_message']) > 100 else ''}",
            inline=False
        )

        await ctx.send(embed=embed)

    @tc_group.command(name="test")
    async def test_notification(self, ctx: commands.Context, notification_type: str):
        """Test a notification by sending it immediately.

        **Arguments:**
        - `notification_type` - Either 'sunday' or 'wednesday'

        **Example:**
        - `[p]tc test sunday`
        """
        notification_type = notification_type.lower()

        if notification_type not in ["sunday", "wednesday"]:
            await ctx.send("❌ Notification type must be 'sunday' or 'wednesday'")
            return

        guild_config = await self.config.guild(ctx.guild).all()

        channel_id = guild_config["channel_id"]
        if not channel_id:
            await ctx.send("❌ No channel configured. Use `[p]tc channel` first.")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Configured channel not found.")
            return

        if notification_type == "sunday":
            message = guild_config["sunday_message"]
            ping_role_id = guild_config["sunday_ping_role_id"]
        else:
            message = guild_config["wednesday_message"]
            ping_role_id = guild_config["wednesday_ping_role_id"]

        await self._send_notification(channel, message, ping_role_id, ctx.guild)
        await ctx.send(f"✅ Test {notification_type} notification sent to {channel.mention}")
