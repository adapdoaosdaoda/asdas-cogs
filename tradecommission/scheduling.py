"""Scheduling methods for Trade Commission cog."""
import discord
import asyncio
import logging
from datetime import datetime
from typing import Optional
import pytz

log = logging.getLogger("red.tradecommission")


class SchedulingMixin:
    """Mixin containing scheduling methods for Trade Commission."""

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
        """Check if it's time to send the weekly message or scheduled notifications for a guild."""
        config = await self.config.guild(guild).all()

        if not config["channel_id"]:
            return

        channel = guild.get_channel(config["channel_id"])
        if not channel:
            return

        # Get timezone
        tz = pytz.timezone(config["timezone"])
        now = datetime.now(tz)

        # Check weekly message (only if enabled)
        if config["enabled"]:
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
                        pass  # Don't return, check other notifications
                    else:
                        # Send the weekly message
                        await self._send_weekly_message(guild, channel)
                        await self.config.guild(guild).last_sent.set(now.isoformat())
                else:
                    # Send the weekly message
                    await self._send_weekly_message(guild, channel)
                    await self.config.guild(guild).last_sent.set(now.isoformat())

        # Check Sunday pre-shop restock notification (weekday 6 = Sunday)
        if (config["sunday_enabled"] and
            now.weekday() == 6 and
            now.hour == config["sunday_hour"] and
            now.minute >= config["sunday_minute"] and
            now.minute < config["sunday_minute"] + 60):

            # Check if we already sent this notification today
            last_sunday = await self.config.guild(guild).get_raw("last_sunday_notification", default=None)
            if last_sunday:
                last_sunday_dt = datetime.fromisoformat(last_sunday)
                if (now - last_sunday_dt).days < 1:
                    pass  # Already sent today
                else:
                    await self._send_scheduled_notification(
                        channel,
                        config["sunday_message"],
                        config["sunday_ping_role_id"],
                        guild
                    )
                    await self.config.guild(guild).last_sunday_notification.set(now.isoformat())
            else:
                await self._send_scheduled_notification(
                    channel,
                    config["sunday_message"],
                    config["sunday_ping_role_id"],
                    guild
                )
                await self.config.guild(guild).last_sunday_notification.set(now.isoformat())

        # Check Wednesday sell recommendation notification (weekday 2 = Wednesday)
        if (config["wednesday_enabled"] and
            now.weekday() == 2 and
            now.hour == config["wednesday_hour"] and
            now.minute >= config["wednesday_minute"] and
            now.minute < config["wednesday_minute"] + 60):

            # Check if we already sent this notification today
            last_wednesday = await self.config.guild(guild).get_raw("last_wednesday_notification", default=None)
            if last_wednesday:
                last_wednesday_dt = datetime.fromisoformat(last_wednesday)
                if (now - last_wednesday_dt).days < 1:
                    pass  # Already sent today
                else:
                    await self._send_scheduled_notification(
                        channel,
                        config["wednesday_message"],
                        config["wednesday_ping_role_id"],
                        guild
                    )
                    await self.config.guild(guild).last_wednesday_notification.set(now.isoformat())
            else:
                await self._send_scheduled_notification(
                    channel,
                    config["wednesday_message"],
                    config["wednesday_ping_role_id"],
                    guild
                )
                await self.config.guild(guild).last_wednesday_notification.set(now.isoformat())

    async def _send_weekly_message(self, guild: discord.Guild, channel: discord.TextChannel):
        """Send the weekly Trade Commission message."""
        # Clear active options for new week
        await self.config.guild(guild).active_options.clear()

        config = await self.config.guild(guild).all()

        # Delete previous week's message if it exists
        if config["previous_message_id"]:
            try:
                prev_channel = guild.get_channel(config["current_channel_id"]) or channel
                prev_message = await prev_channel.fetch_message(config["previous_message_id"])
                await prev_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or no permission

        # Determine embed color from ping role or default
        embed_color = discord.Color.blue()
        if config["ping_role_id"]:
            ping_role = guild.get_role(config["ping_role_id"])
            if ping_role and ping_role.color != discord.Color.default():
                embed_color = ping_role.color

        embed = discord.Embed(
            title=config["message_title"],
            description=config["initial_description"],
            color=embed_color,
        )

        # Add configured image if available
        image_url = await self.config.image_url()
        if image_url:
            embed.set_image(url=image_url)

        # Prepare content with ping if role is configured
        content = None
        if config["ping_role_id"]:
            role = guild.get_role(config["ping_role_id"])
            if role:
                content = role.mention

        try:
            message = await channel.send(content=content, embed=embed)
            # Store current message as previous for next week
            await self.config.guild(guild).previous_message_id.set(config["current_message_id"])
            # Set new current message
            await self.config.guild(guild).current_message_id.set(message.id)
            await self.config.guild(guild).current_channel_id.set(channel.id)
        except discord.Forbidden:
            pass

    async def _send_scheduled_notification(
        self,
        channel: discord.TextChannel,
        message: str,
        ping_role_id: Optional[int],
        guild: discord.Guild
    ):
        """Send a scheduled notification message to the channel."""
        try:
            content = message

            # Add role ping if configured
            if ping_role_id:
                role = guild.get_role(ping_role_id)
                if role:
                    content = f"{role.mention}\n\n{content}"

            notification_msg = await channel.send(content)

            # Schedule deletion after 3 hours
            asyncio.create_task(
                self._delete_notification_after_delay(
                    guild, channel, notification_msg.id, 3
                )
            )
        except discord.Forbidden:
            print(f"Missing permissions to send notification in {channel.name}")
        except discord.HTTPException as e:
            print(f"Error sending notification: {e}")
