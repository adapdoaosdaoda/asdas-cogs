"""Scheduling subcommand groups for Trade Commission cog."""
import discord
import logging
from typing import Optional
from redbot.core import commands

log = logging.getLogger("red.tradecommission")


class CommandsScheduleMixin:
    """Mixin containing scheduling subcommand groups for Trade Commission."""

    async def tc_sunday(self, ctx: commands.Context):
        """Configure Sunday pre-shop restock notifications."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tc_sunday.command(name="enable")
    async def sunday_enable(self, ctx: commands.Context):
        """Enable Sunday pre-shop restock notifications."""
        await self.config.guild(ctx.guild).sunday_enabled.set(True)
        await ctx.send("✅ Sunday pre-shop restock notifications enabled!")

    @tc_sunday.command(name="disable")
    async def sunday_disable(self, ctx: commands.Context):
        """Disable Sunday pre-shop restock notifications."""
        await self.config.guild(ctx.guild).sunday_enabled.set(False)
        await ctx.send("✅ Sunday pre-shop restock notifications disabled.")

    @tc_sunday.command(name="time")
    async def sunday_time(self, ctx: commands.Context, hour: int, minute: int = 0):
        """Set the time for Sunday notifications.

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23)
        - `minute` - Minute (0-59), defaults to 0

        **Example:**
        - `[p]tradecommission sunday time 19 0` - Set to 19:00
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

    @tc_sunday.command(name="message")
    async def sunday_message(self, ctx: commands.Context, *, message: str):
        """Set the message for Sunday notifications.

        **Arguments:**
        - `message` - The message to send

        **Example:**
        - `[p]tradecommission sunday message Pre-shop restock happening soon!`
        """
        await self.config.guild(ctx.guild).sunday_message.set(message)
        await ctx.send("✅ Sunday notification message updated!")

    @tc_sunday.command(name="pingrole")
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

    @tc_sunday.command(name="test")
    async def sunday_test(self, ctx: commands.Context):
        """Test the Sunday notification by sending it immediately."""
        guild_config = await self.config.guild(ctx.guild).all()

        channel_id = guild_config["channel_id"]
        if not channel_id:
            await ctx.send("❌ No channel configured. Use `[p]tradecommission schedule` first.")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Configured channel not found.")
            return

        await self._send_scheduled_notification(
            channel,
            guild_config["sunday_message"],
            guild_config["sunday_ping_role_id"],
            ctx.guild
        )
        await ctx.send(f"✅ Test Sunday notification sent to {channel.mention}")

    async def tc_wednesday(self, ctx: commands.Context):
        """Configure Wednesday sell recommendation notifications."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tc_wednesday.command(name="enable")
    async def wednesday_enable(self, ctx: commands.Context):
        """Enable Wednesday sell recommendation notifications."""
        await self.config.guild(ctx.guild).wednesday_enabled.set(True)
        await ctx.send("✅ Wednesday sell recommendation notifications enabled!")

    @tc_wednesday.command(name="disable")
    async def wednesday_disable(self, ctx: commands.Context):
        """Disable Wednesday sell recommendation notifications."""
        await self.config.guild(ctx.guild).wednesday_enabled.set(False)
        await ctx.send("✅ Wednesday sell recommendation notifications disabled.")

    @tc_wednesday.command(name="time")
    async def wednesday_time(self, ctx: commands.Context, hour: int, minute: int = 0):
        """Set the time for Wednesday notifications.

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23)
        - `minute` - Minute (0-59), defaults to 0

        **Example:**
        - `[p]tradecommission wednesday time 19 0` - Set to 19:00
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

    @tc_wednesday.command(name="message")
    async def wednesday_message(self, ctx: commands.Context, *, message: str):
        """Set the message for Wednesday notifications.

        **Arguments:**
        - `message` - The message to send

        **Example:**
        - `[p]tradecommission wednesday message Time to sell! Check your prices!`
        """
        await self.config.guild(ctx.guild).wednesday_message.set(message)
        await ctx.send("✅ Wednesday notification message updated!")

    @tc_wednesday.command(name="pingrole")
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

    @tc_wednesday.command(name="test")
    async def wednesday_test(self, ctx: commands.Context):
        """Test the Wednesday notification by sending it immediately."""
        guild_config = await self.config.guild(ctx.guild).all()

        channel_id = guild_config["channel_id"]
        if not channel_id:
            await ctx.send("❌ No channel configured. Use `[p]tradecommission schedule` first.")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Configured channel not found.")
            return

        await self._send_scheduled_notification(
            channel,
            guild_config["wednesday_message"],
            guild_config["wednesday_ping_role_id"],
            ctx.guild
        )
        await ctx.send(f"✅ Test Wednesday notification sent to {channel.mention}")
