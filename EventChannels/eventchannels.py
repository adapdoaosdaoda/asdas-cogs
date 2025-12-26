import asyncio
from datetime import datetime, timedelta, timezone
import logging

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.eventchannels")


class EventChannels(commands.Cog):
    """Creates text & voice channels from Discord Scheduled Events and cleans them up."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817263540)
        self.config.register_guild(
            event_channels={},
            category_id=None,
            timezone="UTC",  # Default timezone
            role_format="{name} {day_abbrev} {day}. {month_abbrev} {time}",  # Default role format
            channel_format="{name}᲼{type}",  # Default channel name format
            creation_minutes=15,  # Default creation time in minutes before event
            deletion_hours=4,  # Default deletion time in hours
            announcement_message="{role} The event is starting soon!",  # Default announcement
            divider_enabled=True,  # Enable divider channel by default
            divider_name="━━━━━━ EVENT CHANNELS ━━━━━━",  # Default divider name
            divider_channel_id=None,  # Stores the divider channel ID
            divider_roles=[],  # Track role IDs that have access to the divider
        )
        self.active_tasks = {}  # Store tasks by event_id for cancellation
        self.bot.loop.create_task(self._startup_scan())

    # ---------- Setup Commands ----------

    @commands.guild_only()
    @commands.command()
    async def eventchannels(self, ctx):
        """Display all EventChannels commands with explanations."""
        prefix = ctx.clean_prefix

        embed = discord.Embed(
            title="EventChannels Commands",
            description="Automatically creates text & voice channels from Discord Scheduled Events and manages cleanup.",
            color=discord.Color.blue()
        )

        # Configuration Commands
        config_commands = (
            f"`{prefix}seteventcategory <category>` - Set where event channels will be created\n"
            f"`{prefix}seteventtimezone <timezone>` - Set timezone for event role matching (e.g., Europe/Amsterdam)\n"
            f"`{prefix}seteventcreationtime <minutes>` - Set when channels are created before event start (default: 15)\n"
            f"`{prefix}seteventdeletion <hours>` - Set when channels are deleted after event start (default: 4)\n"
            f"`{prefix}seteventroleformat <format>` - Customize role name format pattern\n"
            f"`{prefix}seteventchannelformat <format>` - Customize channel name format pattern\n"
            f"`{prefix}seteventannouncement <message>` - Set announcement message in event channels\n"
        )
        embed.add_field(name="Configuration", value=config_commands, inline=False)

        # Divider Commands
        divider_commands = (
            f"`{prefix}seteventdivider <true/false> [name]` - Enable/disable divider channel\n"
            f"`{prefix}deletedivider` - Delete the divider channel\n"
        )
        embed.add_field(name="Divider Channel", value=divider_commands, inline=False)

        # View Settings
        view_commands = f"`{prefix}vieweventsettings` - View current configuration settings"
        embed.add_field(name="View Settings", value=view_commands, inline=False)

        embed.set_footer(text="Most commands require Manage Guild permission")

        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            # Fallback to plain text if bot lacks embed permissions
            message = (
                f"**EventChannels Commands**\n\n"
                f"**Configuration:**\n{config_commands}\n\n"
                f"**Divider Channel:**\n{divider_commands}\n\n"
                f"**View Settings:**\n{view_commands}\n\n"
                f"Most commands require Manage Guild permission"
            )
            await ctx.send(message)

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
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        
        try:
            # Validate the timezone
            ZoneInfo(tz)
            await self.config.guild(ctx.guild).timezone.set(tz)
            await ctx.send(f"✅ Event timezone set to **{tz}**.")
        except ZoneInfoNotFoundError:
            await ctx.send(f"❌ Invalid timezone: **{tz}**. Use a timezone like `Europe/Amsterdam` or `America/New_York`.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventdeletion(self, ctx, hours: int):
        """Set how many hours after event start channels are deleted (default: 4)."""
        if hours < 0:
            await ctx.send("❌ Hours must be a positive number.")
            return
        await self.config.guild(ctx.guild).deletion_hours.set(hours)
        await ctx.send(f"✅ Event channels will be deleted **{hours} hours** after event start.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventcreationtime(self, ctx, minutes: int):
        """Set how many minutes before event start channels are created (default: 15)."""
        if minutes < 0:
            await ctx.send("❌ Minutes must be a positive number.")
            return
        if minutes > 1440:  # 24 hours
            await ctx.send("❌ Creation time cannot exceed 1440 minutes (24 hours).")
            return
        await self.config.guild(ctx.guild).creation_minutes.set(minutes)
        await ctx.send(f"✅ Event channels will be created **{minutes} minutes** before event start.")

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
        # Validate the format string has valid placeholders
        valid_placeholders = {'{name}', '{day_abbrev}', '{day}', '{month_abbrev}', '{time}'}
        
        # Check if format contains at least one valid placeholder
        has_valid = any(placeholder in format_string for placeholder in valid_placeholders)
        if not has_valid:
            await ctx.send(f"❌ Format must contain at least one valid placeholder: {', '.join(valid_placeholders)}")
            return
        
        await self.config.guild(ctx.guild).role_format.set(format_string)
        await ctx.send(f"✅ Event role format set to: `{format_string}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventchannelformat(self, ctx, *, format_string: str):
        """Set the channel name format pattern.

        Available placeholders:
        - {name} - Event name (lowercase, spaces replaced)
        - {type} - Channel type ("text" or "voice")

        Examples:
        - `{name}᲼{type}` → "raid᲼night᲼text" (default)
        - `{name}-{type}` → "raid-night-text"
        - `event-{name}-{type}` → "event-raid-night-text"
        """
        # Validate the format string has valid placeholders
        valid_placeholders = {'{name}', '{type}'}

        # Check if format contains both required placeholders
        if '{name}' not in format_string:
            await ctx.send(f"❌ Format must contain `{{name}}` placeholder.")
            return
        if '{type}' not in format_string:
            await ctx.send(f"❌ Format must contain `{{type}}` placeholder.")
            return

        await self.config.guild(ctx.guild).channel_format.set(format_string)
        await ctx.send(f"✅ Event channel format set to: `{format_string}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventannouncement(self, ctx, *, message: str):
        """Set the announcement message posted in event text channels.

        Available placeholders:
        - {role} - Mentions the event role
        - {event} - Event name
        - {time} - Event start time (relative format: "in 5 minutes", "in 2 hours")

        Examples:
        - `{role} The event is starting soon!` (default)
        - `{role} {event} begins {time}!` → "@Role Raid Night begins in 15 minutes!"
        - `{role} Get ready, event starts {time}!`

        To disable announcements, use: `none`
        """
        if message.lower() == "none":
            await self.config.guild(ctx.guild).announcement_message.set("")
            await ctx.send("✅ Event announcements disabled.")
        else:
            await self.config.guild(ctx.guild).announcement_message.set(message)
            await ctx.send(f"✅ Event announcement set to: `{message}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventdivider(self, ctx, enabled: bool, *, divider_name: str = None):
        """Enable/disable divider channel and optionally set its name.

        Examples:
        - `[p]seteventdivider True` - Enable divider with default name
        - `[p]seteventdivider True ━━━━━━ EVENT CHANNELS ━━━━━━` - Enable with custom name
        - `[p]seteventdivider False` - Disable divider channel

        The divider channel is created before the first event channels and persists
        across multiple events to provide visual separation in the channel list.
        """
        await self.config.guild(ctx.guild).divider_enabled.set(enabled)

        if divider_name:
            await self.config.guild(ctx.guild).divider_name.set(divider_name)
            await ctx.send(f"✅ Divider channel {'enabled' if enabled else 'disabled'} with name: `{divider_name}`")
        else:
            await ctx.send(f"✅ Divider channel {'enabled' if enabled else 'disabled'}.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def deletedivider(self, ctx):
        """Delete the divider channel.

        The divider will be recreated automatically when the next event channels are created.
        This is useful if you want to reset the divider or if it's in the wrong category.
        """
        divider_channel_id = await self.config.guild(ctx.guild).divider_channel_id()

        if not divider_channel_id:
            await ctx.send("❌ No divider channel exists.")
            return

        divider_channel = ctx.guild.get_channel(divider_channel_id)

        if not divider_channel:
            await ctx.send("❌ The stored divider channel no longer exists.")
            await self.config.guild(ctx.guild).divider_channel_id.set(None)
            await self.config.guild(ctx.guild).divider_roles.set([])
            return

        try:
            await divider_channel.delete(reason=f"Divider deleted by {ctx.author}")
            await self.config.guild(ctx.guild).divider_channel_id.set(None)
            await self.config.guild(ctx.guild).divider_roles.set([])
            await ctx.send("✅ Divider channel deleted. It will be recreated when the next event channels are created.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete the divider channel.")
        except Exception as e:
            await ctx.send(f"❌ Failed to delete divider channel: {e}")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def vieweventsettings(self, ctx):
        """View current event channel settings."""
        category_id = await self.config.guild(ctx.guild).category_id()
        timezone = await self.config.guild(ctx.guild).timezone()
        creation_minutes = await self.config.guild(ctx.guild).creation_minutes()
        deletion_hours = await self.config.guild(ctx.guild).deletion_hours()
        role_format = await self.config.guild(ctx.guild).role_format()
        channel_format = await self.config.guild(ctx.guild).channel_format()
        announcement_message = await self.config.guild(ctx.guild).announcement_message()
        divider_enabled = await self.config.guild(ctx.guild).divider_enabled()
        divider_name = await self.config.guild(ctx.guild).divider_name()

        category = ctx.guild.get_channel(category_id) if category_id else None
        category_name = category.name if category else "Not set"
        announcement_display = f"`{announcement_message}`" if announcement_message else "Disabled"
        divider_display = f"Enabled (`{divider_name}`)" if divider_enabled else "Disabled"

        embed = discord.Embed(title="Event Channels Settings", color=discord.Color.blue())
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="Timezone", value=timezone, inline=False)
        embed.add_field(name="Creation Time", value=f"{creation_minutes} minutes before start", inline=False)
        embed.add_field(name="Deletion Time", value=f"{deletion_hours} hours after start", inline=False)
        embed.add_field(name="Role Format", value=f"`{role_format}`", inline=False)
        embed.add_field(name="Channel Format", value=f"`{channel_format}`", inline=False)
        embed.add_field(name="Announcement", value=announcement_display, inline=False)
        embed.add_field(name="Divider Channel", value=divider_display, inline=False)

        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            # Fallback to plain text if bot lacks embed permissions
            message = (
                f"**Event Channels Settings**\n"
                f"**Category:** {category_name}\n"
                f"**Timezone:** {timezone}\n"
                f"**Creation Time:** {creation_minutes} minutes before start\n"
                f"**Deletion Time:** {deletion_hours} hours after start\n"
                f"**Role Format:** `{role_format}`\n"
                f"**Channel Format:** `{channel_format}`\n"
                f"**Announcement:** {announcement_display}\n"
                f"**Divider Channel:** {divider_display}"
            )
            await ctx.send(message)

    # ---------- Startup ----------

    async def _startup_scan(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._schedule_existing_events(guild)

    async def _schedule_existing_events(self, guild: discord.Guild):
        try:
            events = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            return

        for event in events:
            if event.start_time and event.status == discord.EventStatus.scheduled:
                task = self.bot.loop.create_task(self._handle_event(guild, event))
                self.active_tasks[event.id] = task

    # ---------- Core Logic ----------

    async def _update_divider_permissions(self, guild: discord.Guild, role: discord.Role, add: bool = True):
        """Update divider channel permissions to add or remove a role.

        Args:
            guild: The Discord guild
            role: The role to add or remove
            add: True to add the role, False to remove it
        """
        divider_enabled = await self.config.guild(guild).divider_enabled()
        if not divider_enabled:
            log.info(f"Divider not enabled, skipping permission update for role '{role.name}'")
            return

        divider_channel_id = await self.config.guild(guild).divider_channel_id()
        if not divider_channel_id:
            log.warning(f"No divider channel ID found when trying to update permissions for role '{role.name}'")
            return

        divider_channel = guild.get_channel(divider_channel_id)
        if not divider_channel:
            log.warning(f"Divider channel {divider_channel_id} not found when trying to update permissions for role '{role.name}'")
            return

        divider_roles = await self.config.guild(guild).divider_roles()
        log.info(f"Updating divider permissions: add={add}, role='{role.name}', current_roles={divider_roles}")

        try:
            if add and role.id not in divider_roles:
                # Add role to divider permissions - can see but not send messages
                overwrite = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False
                )
                log.info(f"Adding permission overwrite for role '{role.name}' (ID: {role.id}) to divider channel '{divider_channel.name}'")
                await divider_channel.set_permissions(
                    role,
                    overwrite=overwrite,
                    reason=f"Adding event role '{role.name}' to divider channel"
                )
                divider_roles.append(role.id)
                await self.config.guild(guild).divider_roles.set(divider_roles)
                log.info(f"✅ Successfully added role '{role.name}' to divider channel permissions - can view but not send messages")
            elif not add and role.id in divider_roles:
                # Remove role from divider permissions
                log.info(f"Removing permission overwrite for role '{role.name}' from divider channel")
                await divider_channel.set_permissions(
                    role,
                    overwrite=None,  # Remove the overwrite
                    reason=f"Removing event role '{role.name}' from divider channel"
                )
                divider_roles.remove(role.id)
                await self.config.guild(guild).divider_roles.set(divider_roles)
                log.info(f"✅ Removed role '{role.name}' from divider channel permissions")
            else:
                log.info(f"Skipping divider permission update for role '{role.name}' - add={add}, already_tracked={role.id in divider_roles}")
        except discord.Forbidden as e:
            log.error(f"❌ Permission error while updating divider permissions for role '{role.name}': {e}")
        except Exception as e:
            log.error(f"❌ Failed to update divider permissions for role '{role.name}': {e}")

    async def _ensure_divider_channel(self, guild: discord.Guild, category: discord.CategoryChannel = None):
        """Ensure the divider channel exists in the specified category.

        Returns the divider channel if it exists or was created, otherwise None.
        """
        divider_enabled = await self.config.guild(guild).divider_enabled()
        if not divider_enabled:
            return None

        divider_name = await self.config.guild(guild).divider_name()
        divider_channel_id = await self.config.guild(guild).divider_channel_id()

        # Check if we have a stored divider channel ID
        if divider_channel_id:
            divider_channel = guild.get_channel(divider_channel_id)
            if divider_channel and divider_channel.category == category:
                # Divider exists and is in the right category
                log.info(f"Found existing divider channel: {divider_channel.name}")
                return divider_channel
            else:
                # Stored divider doesn't exist or is in wrong category, clear the stored ID
                await self.config.guild(guild).divider_channel_id.set(None)

        # Check if a divider channel with the correct name already exists in the category
        if category:
            for channel in category.channels:
                if channel.name == divider_name and isinstance(channel, discord.TextChannel):
                    # Found an existing divider channel, store its ID
                    log.info(f"Found existing divider channel by name: {channel.name}")
                    await self.config.guild(guild).divider_channel_id.set(channel.id)
                    return channel

        # No divider exists, create one
        try:
            # Create divider channel without overwrites first
            divider_channel = await guild.create_text_channel(
                name=divider_name,
                category=category,
                reason="Creating divider channel for event channels",
            )
            log.info(f"Created new divider channel: {divider_channel.name}")

            # Now apply permission overwrites in a separate step
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,  # Hidden by default
                    send_messages=False,
                    add_reactions=False,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    manage_channels=True,
                ),
            }

            # Add permissions for tracked roles
            divider_roles = await self.config.guild(guild).divider_roles()
            for role_id in divider_roles:
                role = guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        add_reactions=False,
                    )

            # Apply the overwrites
            await divider_channel.edit(overwrites=overwrites)
            log.info(f"Successfully applied permissions to divider channel")

            # Store the divider channel ID
            await self.config.guild(guild).divider_channel_id.set(divider_channel.id)
            log.info(f"Stored divider channel ID: {divider_channel.id} (name: '{divider_channel.name}')")
            return divider_channel

        except discord.Forbidden as e:
            log.error(f"Permission error while creating divider channel in guild '{guild.name}': {e}")
            # Clean up the channel if it was created but permissions failed
            if 'divider_channel' in locals():
                try:
                    await divider_channel.delete(reason="Failed to apply permissions")
                except:
                    pass
            return None
        except Exception as e:
            log.error(f"Failed to create divider channel in guild '{guild.name}': {e}")
            # Clean up the channel if it was created
            if 'divider_channel' in locals():
                try:
                    await divider_channel.delete(reason="Creation failed")
                except:
                    pass
            return None

    async def _handle_event(self, guild: discord.Guild, event: discord.ScheduledEvent):
        try:
            start_time = event.start_time.astimezone(timezone.utc)
            creation_minutes = await self.config.guild(guild).creation_minutes()
            create_time = start_time - timedelta(minutes=creation_minutes)
            deletion_hours = await self.config.guild(guild).deletion_hours()
            delete_time = start_time + timedelta(hours=deletion_hours)
            now = datetime.now(timezone.utc)

            # If event starts in less than configured minutes, create channels immediately
            if now >= create_time:
                # Already past the create time, do it now
                pass
            else:
                # Wait until configured minutes before start
                await asyncio.sleep((create_time - now).total_seconds())

            stored = await self.config.guild(guild).event_channels()
            if str(event.id) in stored:
                return

            category_id = await self.config.guild(guild).category_id()
            category = guild.get_channel(category_id) if category_id else None

            # Get server timezone and convert event time
            from zoneinfo import ZoneInfo
            tz_name = await self.config.guild(guild).timezone()
            server_tz = ZoneInfo(tz_name)
            event_local_time = event.start_time.astimezone(server_tz)
            
            # Build the expected role name using the configured format
            role_format = await self.config.guild(guild).role_format()
            
            day_abbrev = event_local_time.strftime("%a")  # Sun, Mon, etc.
            day = event_local_time.strftime("%d").lstrip("0")  # 28 (no leading zero)
            month_abbrev = event_local_time.strftime("%b")  # Dec, Jan, etc.
            time_str = event_local_time.strftime("%H:%M")  # 21:00
            
            expected_role_name = role_format.format(
                name=event.name,
                day_abbrev=day_abbrev,
                day=day,
                month_abbrev=month_abbrev,
                time=time_str
            )
            
            # Check for role with exponential backoff
            role = discord.utils.get(guild.roles, name=expected_role_name)
            if not role:
                # Try with exponential backoff: 5s, 10s, 20s, 40s... up to 60s total
                delay = 5
                total_waited = 0
                while not role and total_waited < 60:
                    await asyncio.sleep(delay)
                    total_waited += delay
                    role = discord.utils.get(guild.roles, name=expected_role_name)
                    if not role:
                        delay *= 2  # Double the delay each time
                
                # If still no role and event is starting soon/now, wait up to 1 minute after start time
                if not role:
                    now = datetime.now(timezone.utc)
                    time_until_start = (start_time - now).total_seconds()
                    
                    # If event starts within 15 seconds or already started (up to 1 min ago)
                    if -60 <= time_until_start <= 15:
                        log.info(f"Event '{event.name}' is starting imminently. Waiting up to 1 minute after start for role...")
                        
                        # Wait until 1 minute after event start using exponential backoff
                        one_min_after_start = start_time + timedelta(minutes=1)
                        deadline = one_min_after_start.timestamp()
                        
                        delay = 5
                        total_waited = 0
                        while not role and datetime.now(timezone.utc).timestamp() < deadline:
                            remaining_time = deadline - datetime.now(timezone.utc).timestamp()
                            sleep_time = min(delay, remaining_time)
                            
                            if sleep_time > 0:
                                await asyncio.sleep(sleep_time)
                                total_waited += sleep_time
                                role = discord.utils.get(guild.roles, name=expected_role_name)
                                if not role:
                                    delay *= 2  # Double the delay each time
                
                if not role:
                    log.warning(f"No matching role found for event '{event.name}'. Expected role: '{expected_role_name}'")
                    return  # Still no matching role → no channels created
            
            log.info(f"Found matching role '{expected_role_name}' for event '{event.name}'")

            # Check bot permissions
            bot_perms = guild.me.guild_permissions
            log.info(f"Bot permissions - manage_channels: {bot_perms.manage_channels}, administrator: {bot_perms.administrator}")
            
            if category:
                cat_perms = category.permissions_for(guild.me)
                log.info(f"Bot permissions in category '{category.name}' - manage_channels: {cat_perms.manage_channels}, manage_permissions: {cat_perms.manage_permissions}")

            # Check if bot's role is higher than the event role
            bot_top_role = guild.me.top_role
            log.info(f"Bot's top role: {bot_top_role.name} (position: {bot_top_role.position}), Event role: {role.name} (position: {role.position})")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                ),
                role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                ),
            }

            # Get channel format and prepare channel names
            channel_format = await self.config.guild(guild).channel_format()
            base_name = event.name.lower().replace(" ", "᲼")

            text_channel_name = channel_format.format(name=base_name, type="text")
            voice_channel_name = channel_format.format(name=base_name, type="voice")

            text_channel = None
            voice_channel = None

            # Ensure divider channel exists before creating event channels
            await self._ensure_divider_channel(guild, category)

            try:
                # Create channels without overwrites first
                text_channel = await guild.create_text_channel(
                    name=text_channel_name,
                    category=category,
                    reason=f"Scheduled event '{event.name}' starting soon",
                )
                log.info(f"Created text channel: {text_channel.name}")

                voice_channel = await guild.create_voice_channel(
                    name=voice_channel_name,
                    category=category,
                    reason=f"Scheduled event '{event.name}' starting soon",
                )
                log.info(f"Created voice channel: {voice_channel.name}")

                # Now apply permission overwrites
                await text_channel.edit(overwrites=overwrites)
                await voice_channel.edit(overwrites=overwrites)
                log.info(f"Successfully applied permissions to both channels for event '{event.name}'")

                # Add role to divider permissions
                await self._update_divider_permissions(guild, role, add=True)

                # Send announcement message if configured
                announcement_template = await self.config.guild(guild).announcement_message()
                if announcement_template:
                    # Format event time as Discord relative timestamp
                    unix_timestamp = int(event.start_time.timestamp())
                    discord_timestamp = f"<t:{unix_timestamp}:R>"

                    # Format the announcement message
                    announcement = announcement_template.format(
                        role=role.mention,
                        event=event.name,
                        time=discord_timestamp
                    )

                    try:
                        await text_channel.send(announcement, allowed_mentions=discord.AllowedMentions(roles=True))
                        log.info(f"Sent announcement to {text_channel.name}")
                    except discord.Forbidden:
                        log.warning(f"Could not send announcement to {text_channel.name} - missing permissions")

            except discord.Forbidden as e:
                log.error(f"Permission error while creating/configuring channels for event '{event.name}': {e}")
                # Clean up any created channels
                if text_channel:
                    try:
                        await text_channel.delete(reason="Failed to apply permissions")
                    except:
                        pass
                if voice_channel:
                    try:
                        await voice_channel.delete(reason="Failed to apply permissions")
                    except:
                        pass
                return
            except Exception as e:
                log.error(f"Failed to create channels for event '{event.name}': {e}")
                # Clean up any created channels
                if text_channel:
                    try:
                        await text_channel.delete(reason="Creation failed")
                    except:
                        pass
                if voice_channel:
                    try:
                        await voice_channel.delete(reason="Creation failed")
                    except:
                        pass
                return

            stored[str(event.id)] = {
                "text": text_channel.id,
                "voice": voice_channel.id,
                "role": role.id,
            }
            await self.config.guild(guild).event_channels.set(stored)

            # ---------- Cleanup ----------

            await asyncio.sleep(max(0, (delete_time - datetime.now(timezone.utc)).total_seconds()))

            data = stored.get(str(event.id))
            if not data:
                return

            for channel_id in (data["text"], data["voice"]):
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="Scheduled event ended")
                    except discord.NotFound:
                        pass

            role = guild.get_role(data["role"])
            if role:
                # Remove role from divider permissions before deleting it
                await self._update_divider_permissions(guild, role, add=False)
                try:
                    await role.delete(reason="Scheduled event ended")
                except discord.Forbidden:
                    pass

            stored.pop(str(event.id), None)
            await self.config.guild(guild).event_channels.set(stored)
        except asyncio.CancelledError:
            # Task was cancelled - clean up if channels were created
            stored = await self.config.guild(guild).event_channels()
            data = stored.get(str(event.id))
            if data:
                for channel_id in (data["text"], data["voice"]):
                    channel = guild.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.delete(reason="Scheduled event cancelled")
                        except (discord.NotFound, discord.Forbidden):
                            pass
                # Remove role from divider permissions
                role = guild.get_role(data["role"])
                if role:
                    await self._update_divider_permissions(guild, role, add=False)
                stored.pop(str(event.id), None)
                await self.config.guild(guild).event_channels.set(stored)
            raise 
        finally:
            # Clean up task reference
            self.active_tasks.pop(event.id, None)

    # ---------- Event Listeners ----------

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        if event.guild and event.status == discord.EventStatus.scheduled:
            task = self.bot.loop.create_task(self._handle_event(event.guild, event))
            self.active_tasks[event.id] = task

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        """Cancel task and clean up channels when event is deleted."""
        task = self.active_tasks.get(event.id)
        if task and not task.done():
            task.cancel()

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        """Cancel task and clean up if event is cancelled or start time changes significantly."""
        if after.status == discord.EventStatus.cancelled:
            task = self.active_tasks.get(after.id)
            if task and not task.done():
                task.cancel()
        elif before.start_time != after.start_time and after.status == discord.EventStatus.scheduled:
            # Start time changed - cancel old task and create new one
            task = self.active_tasks.get(after.id)
            if task and not task.done():
                task.cancel()
            # Give a moment for cancellation to complete
            await asyncio.sleep(0.1)
            new_task = self.bot.loop.create_task(self._handle_event(after.guild, after))
            self.active_tasks[after.id] = new_task
    
    def cog_unload(self):
        """Cancel all active tasks when cog is unloaded."""
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()