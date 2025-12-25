import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.eventchannels")

# Constants
CHANNEL_CREATE_ADVANCE_MINUTES = 15  # Default, configurable per guild
ROLE_WAIT_TIMEOUT_SECONDS = 60
INITIAL_ROLE_RETRY_DELAY = 5
IMMINENT_EVENT_THRESHOLD = 15  # seconds
POST_START_ROLE_WAIT = 60  # seconds
RATE_LIMIT_DELAY = 1.5  # seconds between channel operations


class EventChannels(commands.Cog):
    """Creates text & voice channels from Discord Scheduled Events and cleans them up."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817263540)
        self.config.register_guild(
            event_channels={},
            category_id=None,
            timezone="UTC",
            role_format="{name} {day_abbrev} {day}. {month_abbrev} {time}",
            deletion_hours=4,
            creation_minutes=15,  # How many minutes before event to create channels
            announcement_message="{role} Your event **{name}** is starting soon!",  # {role}, {name}, {time}, {description}
            announcement_enabled=True,
            deletion_enabled=True,  # Allow disabling automatic deletion
            notification_channel_id=None,  # NEW: Channel for error notifications
        )
        self.active_tasks: Dict[int, asyncio.Task] = {}
        self._startup_complete = False
        self._pending_events = []  # Buffer for events during startup
        self.bot.loop.create_task(self._startup_scan())

    # ---------- Setup Commands ----------

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventcategory(self, ctx, category: discord.CategoryChannel):
        """Set the category where event channels will be created."""
        await self.config.guild(ctx.guild).category_id.set(category.id)
        await ctx.send(f"✅ Event channels will be created in **{category.name}**.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventtimezone(self, ctx, tz: str):
        """Set the timezone for event role matching (e.g., Europe/Amsterdam, America/New_York)."""
        try:
            ZoneInfo(tz)
            await self.config.guild(ctx.guild).timezone.set(tz)
            await ctx.send(f"✅ Event timezone set to **{tz}**.")
        except ZoneInfoNotFoundError:
            await ctx.send(f"❌ Invalid timezone: **{tz}**. Use a timezone like `Europe/Amsterdam` or `America/New_York`.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventdeletion(self, ctx, hours: int):
        """Set how many hours after event start channels are deleted (default: 4).
        
        Set to 0 to disable automatic deletion entirely.
        """
        if hours < 0:
            await ctx.send("❌ Hours must be 0 or a positive number. Use 0 to disable automatic deletion.")
            return
        
        if hours == 0:
            await self.config.guild(ctx.guild).deletion_enabled.set(False)
            await ctx.send("✅ Automatic channel deletion **disabled**. Channels will remain until manually cleaned up.")
        else:
            await self.config.guild(ctx.guild).deletion_enabled.set(True)
            await self.config.guild(ctx.guild).deletion_hours.set(hours)
            await ctx.send(f"✅ Event channels will be deleted **{hours} hours** after event start.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventcreation(self, ctx, minutes: int):
        """Set how many minutes before event start to create channels (default: 15).
        
        Minimum: 1 minute, Maximum: 1440 minutes (24 hours)
        """
        if minutes < 1 or minutes > 1440:
            await ctx.send("❌ Minutes must be between 1 and 1440 (24 hours).")
            return
        
        await self.config.guild(ctx.guild).creation_minutes.set(minutes)
        await ctx.send(f"✅ Event channels will be created **{minutes} minutes** before event start.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventnotifications(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Set a channel to receive error notifications for event creation issues.
        
        Use without arguments to disable notifications.
        """
        if channel is None:
            await self.config.guild(ctx.guild).notification_channel_id.set(None)
            await ctx.send("✅ Event error notifications **disabled**.")
        else:
            await self.config.guild(ctx.guild).notification_channel_id.set(channel.id)
            await ctx.send(f"✅ Event errors will be posted to {channel.mention}.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventroleformat(self, ctx, *, format_string: str):
        """Set the role name format pattern.
        
        Available placeholders:
        - {name} - Event name
        - {day_abbrev} - Day abbreviation (Mon, Tue, etc.)
        - {day} - Day number (1-31)
        - {month_abbrev} - Month abbreviation (Jan, Feb, etc.)
        - {time} - Time in HH:MM format
        
        Example: `{name} {day_abbrev} {day}. {month_abbrev} {time}`
        """
        valid_placeholders = {'{name}', '{day_abbrev}', '{day}', '{month_abbrev}', '{time}'}
        
        has_valid = any(placeholder in format_string for placeholder in valid_placeholders)
        if not has_valid:
            await ctx.send(f"❌ Format must contain at least one valid placeholder: {', '.join(valid_placeholders)}")
            return
        
        # Test format length (Discord role name limit is 100 chars)
        test_name = format_string.format(
            name="X" * 50,
            day_abbrev="Wed",
            day="25",
            month_abbrev="Dec",
            time="23:59"
        )
        if len(test_name) > 100:
            await ctx.send(f"⚠️ Warning: Format may exceed Discord's 100 character role name limit. Current test length: {len(test_name)}")
        
        await self.config.guild(ctx.guild).role_format.set(format_string)
        await ctx.send(f"✅ Event role format set to: `{format_string}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventannouncement(self, ctx, *, message: Optional[str] = None):
        """Set or disable the announcement message posted in new event channels.
        
        Available placeholders:
        - {role} - Mentions the event role
        - {name} - Event name
        - {time} - Event start time
        - {description} - Event description
        
        Use without arguments to disable announcements.
        
        Example: `{role} Your event **{name}** starts at {time}!`
        """
        if message is None:
            await self.config.guild(ctx.guild).announcement_enabled.set(False)
            await ctx.send("✅ Event announcements **disabled**.")
        else:
            # Validate message length (Discord message limit is 2000 chars)
            test_msg = message.format(
                role="@Role",
                name="Test Event Name",
                time="2024-12-25 20:00",
                description="Test description"
            )
            if len(test_msg) > 2000:
                await ctx.send(f"❌ Message too long. Maximum length after placeholder expansion: 2000 characters. Current: {len(test_msg)}")
                return
            
            await self.config.guild(ctx.guild).announcement_message.set(message)
            await self.config.guild(ctx.guild).announcement_enabled.set(True)
            await ctx.send(f"✅ Event announcement message set to:\n```{message}```")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def vieweventsettings(self, ctx):
        """View current event channel settings."""
        category_id = await self.config.guild(ctx.guild).category_id()
        timezone = await self.config.guild(ctx.guild).timezone()
        deletion_hours = await self.config.guild(ctx.guild).deletion_hours()
        deletion_enabled = await self.config.guild(ctx.guild).deletion_enabled()
        creation_minutes = await self.config.guild(ctx.guild).creation_minutes()
        role_format = await self.config.guild(ctx.guild).role_format()
        announcement_enabled = await self.config.guild(ctx.guild).announcement_enabled()
        announcement_message = await self.config.guild(ctx.guild).announcement_message()
        notification_channel_id = await self.config.guild(ctx.guild).notification_channel_id()
        
        category = ctx.guild.get_channel(category_id) if category_id else None
        category_name = category.name if category else "Not set"
        
        notification_channel = ctx.guild.get_channel(notification_channel_id) if notification_channel_id else None
        notification_text = notification_channel.mention if notification_channel else "Disabled"
        
        deletion_text = f"{deletion_hours} hours after start" if deletion_enabled else "Disabled"
        announcement_text = f"Enabled\n```{announcement_message}```" if announcement_enabled else "Disabled"
        
        embed = discord.Embed(title="Event Channels Settings", color=discord.Color.blue())
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="Timezone", value=timezone, inline=False)
        embed.add_field(name="Creation Time", value=f"{creation_minutes} minutes before start", inline=False)
        embed.add_field(name="Deletion Time", value=deletion_text, inline=False)
        embed.add_field(name="Role Format", value=f"`{role_format}`", inline=False)
        embed.add_field(name="Announcement", value=announcement_text, inline=False)
        embed.add_field(name="Error Notifications", value=notification_text, inline=False)
        
        await ctx.send(embed=embed)

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def listeventchannels(self, ctx):
        """Show currently active event channels."""
        stored = await self.config.guild(ctx.guild).event_channels()
        
        if not stored:
            await ctx.send("No active event channels.")
            return
        
        embed = discord.Embed(title="Active Event Channels", color=discord.Color.green())
        
        for event_id, data in stored.items():
            text_channel = ctx.guild.get_channel(data.get("text"))
            voice_channel = ctx.guild.get_channel(data.get("voice"))
            role = ctx.guild.get_role(data.get("role"))
            
            text_mention = text_channel.mention if text_channel else "❌ Deleted"
            voice_mention = voice_channel.mention if voice_channel else "❌ Deleted"
            role_mention = role.mention if role else "❌ Deleted"
            
            embed.add_field(
                name=f"Event ID: {event_id}",
                value=f"**Text:** {text_mention}\n**Voice:** {voice_mention}\n**Role:** {role_mention}",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def cleanupevent(self, ctx, event_id: str):
        """Manually trigger cleanup for a specific event by event ID."""
        stored = await self.config.guild(ctx.guild).event_channels()
        
        data = stored.get(event_id)
        if not data:
            await ctx.send(f"❌ No active channels found for event ID: `{event_id}`")
            return
        
        # Cancel any active task
        task = self.active_tasks.get(int(event_id))
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        deleted_items = []
        
        # Delete text channel
        text_channel = ctx.guild.get_channel(data.get("text"))
        if text_channel:
            try:
                await text_channel.delete(reason=f"Manual cleanup by {ctx.author}")
                deleted_items.append("✅ text channel")
            except discord.Forbidden:
                deleted_items.append("❌ text channel (no permission)")
            except discord.NotFound:
                deleted_items.append("⚠️ text channel (already deleted)")
        
        # Delete voice channel
        voice_channel = ctx.guild.get_channel(data.get("voice"))
        if voice_channel:
            try:
                await asyncio.sleep(RATE_LIMIT_DELAY)  # Rate limit protection
                await voice_channel.delete(reason=f"Manual cleanup by {ctx.author}")
                deleted_items.append("✅ voice channel")
            except discord.Forbidden:
                deleted_items.append("❌ voice channel (no permission)")
            except discord.NotFound:
                deleted_items.append("⚠️ voice channel (already deleted)")
        
        # Delete role
        role = ctx.guild.get_role(data.get("role"))
        if role:
            try:
                await asyncio.sleep(RATE_LIMIT_DELAY)  # Rate limit protection
                await role.delete(reason=f"Manual cleanup by {ctx.author}")
                deleted_items.append("✅ role")
            except discord.Forbidden:
                deleted_items.append("❌ role (no permission)")
            except discord.NotFound:
                deleted_items.append("⚠️ role (already deleted)")
        
        # Remove from config
        stored.pop(event_id, None)
        await self.config.guild(ctx.guild).event_channels.set(stored)
        
        result = "\n".join(deleted_items)
        await ctx.send(f"**Cleanup for event {event_id}:**\n{result}")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def testeventrole(self, ctx, event_id: str):
        """Test what role name would be generated for a Discord scheduled event.
        
        Use the event ID from Discord (right-click event → Copy ID with Developer Mode enabled).
        """
        try:
            events = await ctx.guild.fetch_scheduled_events()
            event = discord.utils.get(events, id=int(event_id))
            
            if not event:
                await ctx.send(f"❌ No scheduled event found with ID: `{event_id}`")
                return
            
            if not event.start_time:
                await ctx.send(f"❌ Event `{event.name}` has no start time.")
                return
            
            tz_name = await self.config.guild(ctx.guild).timezone()
            server_tz = ZoneInfo(tz_name)
            event_local_time = event.start_time.astimezone(server_tz)
            
            role_format = await self.config.guild(ctx.guild).role_format()
            expected_role_name = self._build_role_name(event.name, event_local_time, role_format)
            
            role = discord.utils.get(ctx.guild.roles, name=expected_role_name)
            
            embed = discord.Embed(title="Event Role Name Test", color=discord.Color.blue())
            embed.add_field(name="Event Name", value=event.name, inline=False)
            embed.add_field(name="Start Time (UTC)", value=event.start_time.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            embed.add_field(name=f"Start Time ({tz_name})", value=event_local_time.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            embed.add_field(name="Expected Role Name", value=f"`{expected_role_name}`", inline=False)
            embed.add_field(name="Role Exists?", value="✅ Yes" if role else "❌ No", inline=False)
            
            if role:
                embed.add_field(name="Role Mention", value=role.mention, inline=False)
                
                # Check role hierarchy
                if ctx.guild.me.top_role.position <= role.position:
                    embed.add_field(
                        name="⚠️ Warning",
                        value=f"Bot's role position ({ctx.guild.me.top_role.position}) is not higher than event role ({role.position}). The bot won't be able to delete this role.",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="💡 Tip",
                    value=f"Role not found. Check:\n• Role format setting: `{role_format}`\n• Timezone setting: `{tz_name}`\n• Make sure Raid-Helper has created the role",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except ValueError:
            await ctx.send(f"❌ Invalid event ID format: `{event_id}`. Must be a number.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to fetch scheduled events.")
        except Exception as e:
            log.error(f"Error in testeventrole: {e}", exc_info=True)
            await ctx.send(f"❌ Error: {str(e)}")

    # ---------- Helper Methods ----------

    def _build_role_name(self, event_name: str, event_time: datetime, role_format: str) -> str:
        """Build the expected role name from format string."""
        day_abbrev = event_time.strftime("%a")
        day = event_time.strftime("%d").lstrip("0")
        month_abbrev = event_time.strftime("%b")
        time_str = event_time.strftime("%H:%M")
        
        return role_format.format(
            name=event_name,
            day_abbrev=day_abbrev,
            day=day,
            month_abbrev=month_abbrev,
            time=time_str
        )

    async def _verify_permissions(self, guild: discord.Guild, category: Optional[discord.CategoryChannel], role: discord.Role) -> list[str]:
        """Verify bot has necessary permissions. Returns list of issues."""
        issues = []
        
        if not guild.me.guild_permissions.manage_channels:
            issues.append("Missing server-level 'Manage Channels' permission")
        
        if not guild.me.guild_permissions.manage_roles:
            issues.append("Missing server-level 'Manage Roles' permission")
        
        if category:
            cat_perms = category.permissions_for(guild.me)
            if not cat_perms.manage_channels:
                issues.append(f"Cannot manage channels in category '{category.name}'")
            if not cat_perms.manage_permissions:
                issues.append(f"Cannot manage permissions in category '{category.name}'")
        
        if role and guild.me.top_role.position <= role.position:
            issues.append(f"Bot role (position {guild.me.top_role.position}) must be higher than event role '{role.name}' (position {role.position})")
        
        return issues

    async def _wait_for_role(self, guild: discord.Guild, expected_role_name: str, event_start: datetime) -> Optional[discord.Role]:
        """Wait for role to appear with exponential backoff."""
        role = discord.utils.get(guild.roles, name=expected_role_name)
        if role:
            return role
        
        # Initial waiting with exponential backoff
        delay = INITIAL_ROLE_RETRY_DELAY
        total_waited = 0
        while not role and total_waited < ROLE_WAIT_TIMEOUT_SECONDS:
            await asyncio.sleep(delay)
            total_waited += delay
            role = discord.utils.get(guild.roles, name=expected_role_name)
            if not role:
                delay = min(delay * 2, 30)  # Cap at 30 seconds
        
        if role:
            return role
        
        # If event is imminent, wait longer
        now = datetime.now(timezone.utc)
        time_until_start = (event_start - now).total_seconds()
        
        if -POST_START_ROLE_WAIT <= time_until_start <= IMMINENT_EVENT_THRESHOLD:
            log.info(f"Event starting imminently. Waiting up to {POST_START_ROLE_WAIT}s after start for role '{expected_role_name}'")
            
            one_min_after_start = event_start + timedelta(seconds=POST_START_ROLE_WAIT)
            deadline = one_min_after_start.timestamp()
            
            delay = INITIAL_ROLE_RETRY_DELAY
            while not role and datetime.now(timezone.utc).timestamp() < deadline:
                remaining_time = deadline - datetime.now(timezone.utc).timestamp()
                sleep_time = min(delay, remaining_time)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    role = discord.utils.get(guild.roles, name=expected_role_name)
                    if not role:
                        delay = min(delay * 2, 30)
        
        return role

    async def _send_error_notification(self, guild: discord.Guild, error_message: str, event_name: str = None):
        """Send error notification to configured channel."""
        notification_channel_id = await self.config.guild(guild).notification_channel_id()
        if not notification_channel_id:
            return
        
        channel = guild.get_channel(notification_channel_id)
        if not channel:
            return
        
        try:
            embed = discord.Embed(
                title="⚠️ Event Channel Creation Failed",
                description=error_message,
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            if event_name:
                embed.add_field(name="Event", value=event_name, inline=False)
            
            await channel.send(embed=embed)
        except Exception as e:
            log.error(f"Failed to send error notification: {e}", exc_info=True)

    # ---------- Startup ----------

    async def _startup_scan(self):
        """Scan for existing events on startup."""
        await self.bot.wait_until_ready()
        
        for guild in self.bot.guilds:
            await self._schedule_existing_events(guild)
        
        # Mark startup complete and process any buffered events
        self._startup_complete = True
        
        if self._pending_events:
            log.info(f"Processing {len(self._pending_events)} events buffered during startup")
            for guild, event in self._pending_events:
                if event.status == discord.EventStatus.scheduled:
                    task = self.bot.loop.create_task(self._handle_event(guild, event))
                    self.active_tasks[event.id] = task
            self._pending_events.clear()

    async def _schedule_existing_events(self, guild: discord.Guild):
        """Schedule tasks for existing events."""
        try:
            events = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            log.warning(f"No permission to fetch events in {guild.name}")
            return

        for event in events:
            if event.start_time and event.status == discord.EventStatus.scheduled:
                # Check if channels already exist for this event
                stored = await self.config.guild(guild).event_channels()
                if str(event.id) not in stored:
                    task = self.bot.loop.create_task(self._handle_event(guild, event))
                    self.active_tasks[event.id] = task
                else:
                    log.info(f"Channels already exist for event '{event.name}' (ID: {event.id})")

    # ---------- Core Logic ----------

    async def _handle_event(self, guild: discord.Guild, event: discord.ScheduledEvent):
        """Main event handling logic."""
        text_channel = None
        voice_channel = None
        
        try:
            creation_minutes = await self.config.guild(guild).creation_minutes()
            start_time = event.start_time.astimezone(timezone.utc)
            create_time = start_time - timedelta(minutes=creation_minutes)
            now = datetime.now(timezone.utc)

            # Wait until creation time
            if now < create_time:
                await asyncio.sleep((create_time - now).total_seconds())

            # Check if channels already exist
            stored = await self.config.guild(guild).event_channels()
            if str(event.id) in stored:
                log.info(f"Channels already exist for event '{event.name}', skipping creation")
                return

            # Get configuration
            category_id = await self.config.guild(guild).category_id()
            
            # CRITICAL CHECK: Category must be set
            if not category_id:
                error_msg = "❌ **No category set!** Use `seteventcategory` command to configure where event channels should be created."
                log.error(f"Cannot create channels for event '{event.name}': {error_msg}")
                await self._send_error_notification(guild, error_msg, event.name)
                return
            
            category = guild.get_channel(category_id)
            if not category:
                error_msg = f"❌ **Configured category not found!** The category (ID: {category_id}) no longer exists. Please reconfigure with `seteventcategory`."
                log.error(f"Cannot create channels for event '{event.name}': {error_msg}")
                await self._send_error_notification(guild, error_msg, event.name)
                return
            
            tz_name = await self.config.guild(guild).timezone()
            server_tz = ZoneInfo(tz_name)
            event_local_time = event.start_time.astimezone(server_tz)
            
            # Build expected role name
            role_format = await self.config.guild(guild).role_format()
            expected_role_name = self._build_role_name(event.name, event_local_time, role_format)
            
            # Wait for role to appear
            role = await self._wait_for_role(guild, expected_role_name, start_time)
            
            if not role:
                error_msg = (
                    f"❌ **No matching role found!**\n"
                    f"**Expected role name:** `{expected_role_name}`\n"
                    f"**Event:** {event.name}\n"
                    f"**Start time:** {event_local_time.strftime('%Y-%m-%d %H:%M')} {tz_name}\n\n"
                    f"**Possible causes:**\n"
                    f"• Role hasn't been created yet (check Raid-Helper or create manually)\n"
                    f"• Role format mismatch (current: `{role_format}`)\n"
                    f"• Timezone mismatch (current: `{tz_name}`)\n"
                    f"• Role name doesn't match exactly\n\n"
                    f"Use `testeventrole {event.id}` to debug this issue."
                )
                log.warning(f"No matching role found for event '{event.name}'. Expected: '{expected_role_name}'")
                await self._send_error_notification(guild, error_msg, event.name)
                return

            log.info(f"Found matching role '{expected_role_name}' for event '{event.name}'")

            # Verify permissions
            perm_issues = await self._verify_permissions(guild, category, role)
            if perm_issues:
                error_msg = (
                    f"❌ **Permission issues detected:**\n" +
                    "\n".join(f"• {issue}" for issue in perm_issues) +
                    f"\n\nPlease grant the necessary permissions to the bot."
                )
                log.error(f"Permission issues for event '{event.name}': {', '.join(perm_issues)}")
                await self._send_error_notification(guild, error_msg, event.name)
                return

            # Create channels with permissions
            base_name = event.name.lower().replace(" ", "-")
            
            # Build channel topic
            topic = f"Event: {event.name}"
            if event.start_time:
                topic += f" | Starts: {event_local_time.strftime('%Y-%m-%d %H:%M')} {tz_name}"
            if event.description:
                topic += f" | {event.description[:100]}"  # Limit description length
            topic = topic[:1024]  # Discord limit

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True,
                ),
                role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                ),
            }

            # Create text channel
            try:
                text_channel = await guild.create_text_channel(
                    name=f"📅-{base_name}",
                    category=category,
                    topic=topic,
                    overwrites=overwrites,
                    reason=f"Event: {event.name}"
                )
                log.info(f"Created text channel '{text_channel.name}' for event '{event.name}'")
            except discord.Forbidden as e:
                error_msg = f"❌ **Failed to create text channel:** Missing permissions - {e}"
                log.error(f"Permission error creating text channel: {e}", exc_info=True)
                await self._send_error_notification(guild, error_msg, event.name)
                return
            except Exception as e:
                error_msg = f"❌ **Failed to create text channel:** {str(e)}"
                log.error(f"Error creating text channel: {e}", exc_info=True)
                await self._send_error_notification(guild, error_msg, event.name)
                return

            # Rate limit protection
            await asyncio.sleep(RATE_LIMIT_DELAY)

            # Create voice channel
            try:
                voice_channel = await guild.create_voice_channel(
                    name=f"🔊 {event.name}",
                    category=category,
                    overwrites=overwrites,
                    reason=f"Event: {event.name}"
                )
                log.info(f"Created voice channel '{voice_channel.name}' for event '{event.name}'")
            except discord.Forbidden as e:
                error_msg = f"❌ **Failed to create voice channel:** Missing permissions - {e}"
                log.error(f"Permission error creating voice channel: {e}", exc_info=True)
                await self._send_error_notification(guild, error_msg, event.name)
                # Cleanup text channel
                if text_channel:
                    try:
                        await text_channel.delete(reason="Cleanup after error")
                    except Exception:
                        pass
                return
            except Exception as e:
                error_msg = f"❌ **Failed to create voice channel:** {str(e)}"
                log.error(f"Error creating voice channel: {e}", exc_info=True)
                await self._send_error_notification(guild, error_msg, event.name)
                # Cleanup text channel
                if text_channel:
                    try:
                        await text_channel.delete(reason="Cleanup after error")
                    except Exception:
                        pass
                return

            # Post announcement if enabled
            announcement_enabled = await self.config.guild(guild).announcement_enabled()
            if announcement_enabled and text_channel:
                try:
                    announcement_msg = await self.config.guild(guild).announcement_message()
                    
                    formatted_msg = announcement_msg.format(
                        role=role.mention,
                        name=event.name,
                        time=event_local_time.strftime('%Y-%m-%d %H:%M'),
                        description=event.description or "No description"
                    )
                    
                    await text_channel.send(formatted_msg)
                    log.info(f"Posted announcement in {text_channel.name}")
                except Exception as e:
                    log.error(f"Error posting announcement: {e}", exc_info=True)

            # Save to config
            stored[str(event.id)] = {
                "text": text_channel.id,
                "voice": voice_channel.id,
                "role": role.id,
            }
            await self.config.guild(guild).event_channels.set(stored)
            
            # Send success notification
            notification_channel_id = await self.config.guild(guild).notification_channel_id()
            if notification_channel_id:
                channel = guild.get_channel(notification_channel_id)
                if channel:
                    try:
                        embed = discord.Embed(
                            title="✅ Event Channels Created",
                            description=f"Channels created for **{event.name}**",
                            color=discord.Color.green(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        embed.add_field(name="Text Channel", value=text_channel.mention, inline=True)
                        embed.add_field(name="Voice Channel", value=voice_channel.mention, inline=True)
                        embed.add_field(name="Role", value=role.mention, inline=True)
                        await channel.send(embed=embed)
                    except Exception:
                        pass

            # ---------- Cleanup ----------
            deletion_enabled = await self.config.guild(guild).deletion_enabled()
            if not deletion_enabled:
                log.info(f"Automatic deletion disabled for event '{event.name}'")
                return

            deletion_hours = await self.config.guild(guild).deletion_hours()
            delete_time = start_time + timedelta(hours=deletion_hours)
            
            sleep_seconds = (delete_time - datetime.now(timezone.utc)).total_seconds()
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)

            # Perform cleanup
            data = stored.get(str(event.id))
            if not data:
                return

            # Delete text channel
            text_ch = guild.get_channel(data["text"])
            if text_ch:
                try:
                    await text_ch.delete(reason="Scheduled event ended")
                    log.info(f"Deleted text channel for event '{event.name}'")
                except (discord.NotFound, discord.Forbidden) as e:
                    log.warning(f"Could not delete text channel: {e}")
            
            # Rate limit protection
            await asyncio.sleep(RATE_LIMIT_DELAY)
            
            # Delete voice channel
            voice_ch = guild.get_channel(data["voice"])
            if voice_ch:
                try:
                    await voice_ch.delete(reason="Scheduled event ended")
                    log.info(f"Deleted voice channel for event '{event.name}'")
                except (discord.NotFound, discord.Forbidden) as e:
                    log.warning(f"Could not delete voice channel: {e}")
            
            # Rate limit protection
            await asyncio.sleep(RATE_LIMIT_DELAY)
            
            # Delete role
            evt_role = guild.get_role(data["role"])
            if evt_role:
                try:
                    await evt_role.delete(reason="Scheduled event ended")
                    log.info(f"Deleted role for event '{event.name}'")
                except (discord.NotFound, discord.Forbidden) as e:
                    log.warning(f"Could not delete role: {e}")

            stored.pop(str(event.id), None)
            await self.config.guild(guild).event_channels.set(stored)
            
        except asyncio.CancelledError:
            log.info(f"Task cancelled for event '{event.name}'")
            # Clean up any created channels
            stored = await self.config.guild(guild).event_channels()
            data = stored.get(str(event.id))
            if data:
                for channel_id in (data.get("text"), data.get("voice")):
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            try:
                                await channel.delete(reason="Event cancelled")
                                await asyncio.sleep(RATE_LIMIT_DELAY)
                            except (discord.NotFound, discord.Forbidden):
                                pass
                stored.pop(str(event.id), None)
                await self.config.guild(guild).event_channels.set(stored)
            raise
        except Exception as e:
            error_msg = f"❌ **Unhandled error:** {str(e)}\n\nCheck bot logs for details."
            log.error(f"Unhandled error in event handler for '{event.name}': {e}", exc_info=True)
            await self._send_error_notification(guild, error_msg, event.name)
        finally:
            # Clean up task reference
            self.active_tasks.pop(event.id, None)

    # ---------- Event Listeners ----------

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        """Handle new scheduled event creation."""
        if not event.guild or event.status != discord.EventStatus.scheduled:
            return
        
        # If startup isn't complete, buffer the event
        if not self._startup_complete:
            self._pending_events.append((event.guild, event))
            log.info(f"Buffered event '{event.name}' during startup")
            return
        
        # Check if task already exists
        if event.id in self.active_tasks:
            log.info(f"Task already exists for event '{event.name}'")
            return
        
        task = self.bot.loop.create_task(self._handle_event(event.guild, event))
        self.active_tasks[event.id] = task

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        """Cancel task and clean up channels when event is deleted."""
        task = self.active_tasks.get(event.id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        """Handle event updates - cancellation or time changes."""
        if after.status == discord.EventStatus.cancelled:
            task = self.active_tasks.get(after.id)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        elif before.start_time != after.start_time and after.status == discord.EventStatus.scheduled:
            # Start time changed - cancel old task and create new one
            task = self.active_tasks.get(after.id)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Small delay to ensure cleanup is complete
            await asyncio.sleep(0.5)
            
            new_task = self.bot.loop.create_task(self._handle_event(after.guild, after))
            self.active_tasks[after.id] = new_task
    
    def cog_unload(self):
        """Cancel all active tasks when cog is unloaded."""
        log.info(f"Unloading cog, cancelling {len(self.active_tasks)} active tasks")
        for event_id, task in self.active_tasks.items():
            if not task.done():
                task.cancel()