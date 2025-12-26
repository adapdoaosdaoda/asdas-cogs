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
            space_replacer="᲼",  # Character to replace spaces in channel names
            creation_minutes=15,  # Default creation time in minutes before event
            deletion_hours=4,  # Default deletion time in hours
            announcement_message="{role} The event is starting soon!",  # Default announcement
            event_start_message="{role} The event is starting now!",  # Message sent at event start
            deletion_warning_message="⚠️ These channels will be deleted in 15 minutes.",  # Warning before deletion
            divider_enabled=True,  # Enable divider channel by default
            divider_name="━━━━━━ EVENT CHANNELS ━━━━━━",  # Default divider name
            divider_channel_id=None,  # Stores the divider channel ID
            divider_roles=[],  # Track role IDs that have access to the divider
            channel_name_limit=100,  # Character limit for channel names (Discord max is 100)
            channel_name_limit_char="",  # Character to limit name at (empty = use numeric limit)
            voice_multipliers={},  # Dictionary of keyword:multiplier pairs for dynamic voice channel creation
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
            f"`{prefix}seteventstartmessage <message>` - Set message posted when event starts\n"
            f"`{prefix}setdeletionwarning <message>` - Set warning message before channel deletion\n"
            f"`{prefix}setchannelnamelimit <limit>` - Set maximum character limit for channel names (default: 100)\n"
        )
        embed.add_field(name="Configuration", value=config_commands, inline=False)

        # Voice Multiplier Commands
        voice_commands = (
            f"`{prefix}setvoicemultiplier <keyword> <count>` - Add/update voice multiplier for a keyword\n"
            f"`{prefix}listvoicemultipliers` - List all configured voice multipliers\n"
            f"`{prefix}removevoicemultiplier <keyword>` - Remove a specific voice multiplier\n"
            f"`{prefix}disablevoicemultiplier` - Disable all voice multipliers\n"
        )
        embed.add_field(name="Voice Channel Multiplier", value=voice_commands, inline=False)

        # Divider Commands
        divider_commands = (
            f"`{prefix}seteventdivider <true/false> [name]` - Enable/disable divider channel\n"
        )
        embed.add_field(name="Divider Channel", value=divider_commands, inline=False)

        # View Settings
        view_commands = f"`{prefix}vieweventsettings` - View current configuration settings"
        embed.add_field(name="View Settings", value=view_commands, inline=False)

        # Testing
        test_commands = (
            f"`{prefix}testchannellock` - Test channel locking permissions\n"
            f"`{prefix}stresstest` - Comprehensive stress test of all features\n"
        )
        embed.add_field(name="Testing", value=test_commands, inline=False)

        embed.set_footer(text="Most commands require Manage Guild permission")

        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            # Fallback to plain text if bot lacks embed permissions
            message = (
                f"**EventChannels Commands**\n\n"
                f"**Configuration:**\n{config_commands}\n\n"
                f"**Voice Channel Multiplier:**\n{voice_commands}\n\n"
                f"**Divider Channel:**\n{divider_commands}\n\n"
                f"**View Settings:**\n{view_commands}\n\n"
                f"**Testing:**\n{test_commands}\n\n"
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
    async def seteventchannelformat(self, ctx, format_string: str, space_replacer: str = None):
        """Set the channel name format pattern and optionally the space replacer.

        Available placeholders:
        - {name} - Event name (lowercase, spaces replaced)
        - {type} - Channel type ("text" or "voice")

        Examples:
        - `{name}᲼{type}` → "raid᲼night᲼text" (default)
        - `{name}-{type} -` → "raid-night-text" (spaces replaced with -)
        - `{name}_{type} _` → "raid_night_text" (spaces replaced with _)
        - `event-{name}-{type}` → "event-raid-night-text"

        The second parameter is the character to replace spaces with (default: ᲼)
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

        if space_replacer is not None:
            await self.config.guild(ctx.guild).space_replacer.set(space_replacer)
        else:
            space_replacer = await self.config.guild(ctx.guild).space_replacer()

        # Rename existing event channels
        stored = await self.config.guild(ctx.guild).event_channels()
        renamed_count = 0

        for event_id, data in stored.items():
            try:
                # Fetch the event to get its name
                event = await ctx.guild.fetch_scheduled_event(int(event_id))
                if not event:
                    continue

                # Generate new channel names
                base_name = event.name.lower().replace(" ", space_replacer)
                new_text_name = format_string.format(name=base_name, type="text")
                new_voice_name = format_string.format(name=base_name, type="voice")

                # Rename text channel
                text_channel = ctx.guild.get_channel(data.get("text"))
                if text_channel and text_channel.name != new_text_name:
                    try:
                        await text_channel.edit(name=new_text_name, reason=f"Channel format updated by {ctx.author}")
                        renamed_count += 1
                        log.info(f"Renamed text channel to '{new_text_name}'")
                    except discord.Forbidden:
                        pass
                    except Exception as e:
                        log.error(f"Failed to rename text channel: {e}")

                # Rename voice channel(s)
                voice_channel_ids = data.get("voice", [])
                # Handle both old format (single ID) and new format (list of IDs)
                if isinstance(voice_channel_ids, int):
                    voice_channel_ids = [voice_channel_ids]

                voice_count = len(voice_channel_ids)
                for i, vc_id in enumerate(voice_channel_ids):
                    voice_channel = ctx.guild.get_channel(vc_id)
                    if voice_channel:
                        # Generate new name based on count
                        if voice_count > 1:
                            new_vc_name = f"{new_voice_name} {i + 1}"
                        else:
                            new_vc_name = new_voice_name

                        if voice_channel.name != new_vc_name:
                            try:
                                await voice_channel.edit(name=new_vc_name, reason=f"Channel format updated by {ctx.author}")
                                renamed_count += 1
                                log.info(f"Renamed voice channel to '{new_vc_name}'")
                            except discord.Forbidden:
                                pass
                            except Exception as e:
                                log.error(f"Failed to rename voice channel: {e}")

            except discord.NotFound:
                # Event no longer exists
                continue
            except Exception as e:
                log.error(f"Failed to process event {event_id}: {e}")
                continue

        if space_replacer is not None:
            if renamed_count > 0:
                await ctx.send(f"✅ Event channel format set to: `{format_string}` with space replacer: `{space_replacer}`. Renamed {renamed_count} existing channel(s).")
            else:
                await ctx.send(f"✅ Event channel format set to: `{format_string}` with space replacer: `{space_replacer}`")
        else:
            if renamed_count > 0:
                await ctx.send(f"✅ Event channel format set to: `{format_string}`. Renamed {renamed_count} existing channel(s).")
            else:
                await ctx.send(f"✅ Event channel format set to: `{format_string}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def setchannelnamelimit(self, ctx, limit: str):
        """Set the maximum character limit for channel names.

        You can either specify a number or a character to truncate at.

        **Numeric Limit:**
        - Truncates the event name to a specific number of characters
        - Discord's maximum is 100 characters

        **Character-Based Limit:**
        - Truncates at the first occurrence of a specific character (inclusive)
        - Useful for cutting at specific separators

        Examples:
        - `[p]setchannelnamelimit 50` - Limit to 50 characters
        - `[p]setchannelnamelimit ﹕` - Truncate at first "﹕" (including it)
        - `[p]setchannelnamelimit :` - Truncate at first ":" (including it)
        - `[p]setchannelnamelimit 100` - Use Discord's maximum (default)
        """
        # Try to parse as integer first
        try:
            numeric_limit = int(limit)
            if numeric_limit < 1:
                await ctx.send("❌ Character limit must be at least 1.")
                return
            if numeric_limit > 100:
                await ctx.send("❌ Character limit cannot exceed 100 (Discord's maximum).")
                return

            # It's a valid number, use numeric limiting
            await self.config.guild(ctx.guild).channel_name_limit.set(numeric_limit)
            await self.config.guild(ctx.guild).channel_name_limit_char.set("")
            await ctx.send(f"✅ Channel name limit set to **{numeric_limit} characters**.")
        except ValueError:
            # It's not a number, treat it as a character-based limit
            if len(limit) > 5:
                await ctx.send("❌ Character limit string too long. Use a single character or short separator (max 5 characters).")
                return

            # Set character-based limiting
            await self.config.guild(ctx.guild).channel_name_limit_char.set(limit)
            await self.config.guild(ctx.guild).channel_name_limit.set(100)  # Reset to max as fallback
            await ctx.send(f"✅ Channel name limit set to truncate at first occurrence of **'{limit}'** (inclusive).")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def setvoicemultiplier(self, ctx, keyword: str, multiplier: int):
        """Set up dynamic voice channel creation based on role member count.

        When an event name contains the specified keyword, the bot will create voice
        channels dynamically based on the number of people in the event role.

        You can configure multiple keywords, each with their own multiplier.
        If an event name matches multiple keywords, the first matching keyword will be used.

        **How it works:**
        - Multiplier = channel capacity minus 1
        - Channels created = floor(role_members / multiplier), minimum 1
        - Each channel has a user limit set to (multiplier + 1)

        **Parameters:**
        - keyword: The keyword to detect in event names (case-insensitive)
        - multiplier: Divisor for calculating channels (1-99)

        **Examples:**
        - `[p]setvoicemultiplier hero 9`
          - 10 role members → 1 channel (limit: 10 users)
          - 18 role members → 2 channels (limit: 10 users each)
          - 27 role members → 3 channels (limit: 10 users each)

        - `[p]setvoicemultiplier sword 4`
          - 5 role members → 1 channel (limit: 5 users)
          - 12 role members → 3 channels (limit: 5 users each)
          - 20 role members → 5 channels (limit: 5 users each)

        To remove a keyword, use `[p]removevoicemultiplier <keyword>`
        To see all configured multipliers, use `[p]listvoicemultipliers`
        To disable all multipliers, use `[p]disablevoicemultiplier`
        """
        if multiplier < 1:
            await ctx.send("❌ Multiplier must be at least 1.")
            return
        if multiplier > 99:
            await ctx.send("❌ Multiplier cannot exceed 99.")
            return

        # Get current multipliers dictionary
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()

        # Add or update the keyword
        keyword_lower = keyword.lower()
        voice_multipliers[keyword_lower] = multiplier

        # Save back to config
        await self.config.guild(ctx.guild).voice_multipliers.set(voice_multipliers)

        await ctx.send(
            f"✅ Voice multiplier set for keyword **'{keyword}'**:\n"
            f"• Multiplier: **{multiplier}**\n"
            f"• User limit per channel: **{multiplier + 1}**\n"
            f"• Channels will be created dynamically based on role member count\n"
            f"• Formula: `channels = floor(members / {multiplier}), minimum 1`\n\n"
            f"Use `{ctx.clean_prefix}listvoicemultipliers` to see all configured multipliers."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def disablevoicemultiplier(self, ctx):
        """Disable all voice multipliers.

        This will clear all configured keyword-multiplier pairs and restore the default
        behavior of creating only one voice channel per event.
        """
        await self.config.guild(ctx.guild).voice_multipliers.set({})
        await ctx.send("✅ All voice multipliers disabled. All events will create a single voice channel.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def listvoicemultipliers(self, ctx):
        """List all configured voice multipliers.

        Shows all keywords and their associated multipliers.
        """
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()

        if not voice_multipliers:
            await ctx.send(f"❌ No voice multipliers configured. Use `{ctx.clean_prefix}setvoicemultiplier <keyword> <multiplier>` to add one.")
            return

        # Build the list
        multiplier_list = []
        for keyword, multiplier in sorted(voice_multipliers.items()):
            multiplier_list.append(
                f"• **{keyword}**: multiplier={multiplier}, limit={multiplier + 1} users/channel"
            )

        await ctx.send(
            f"**Configured Voice Multipliers:**\n" + "\n".join(multiplier_list) + "\n\n"
            f"Use `{ctx.clean_prefix}removevoicemultiplier <keyword>` to remove a multiplier."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def removevoicemultiplier(self, ctx, keyword: str):
        """Remove a specific voice multiplier keyword.

        **Parameters:**
        - keyword: The keyword to remove (case-insensitive)

        **Example:**
        - `[p]removevoicemultiplier hero`
        """
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()
        keyword_lower = keyword.lower()

        if keyword_lower not in voice_multipliers:
            await ctx.send(f"❌ Keyword **'{keyword}'** is not configured.")
            return

        # Remove the keyword
        del voice_multipliers[keyword_lower]

        # Save back to config
        await self.config.guild(ctx.guild).voice_multipliers.set(voice_multipliers)

        await ctx.send(f"✅ Removed voice multiplier for keyword **'{keyword}'**.")

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
    async def seteventstartmessage(self, ctx, *, message: str):
        """Set the message posted when the event starts.

        Available placeholders:
        - {role} - Mentions the event role
        - {event} - Event name

        Examples:
        - `{role} The event is starting now!` (default)
        - `{role} {event} has begun!`
        - `{role} Time to join!`

        To disable event start messages, use: `none`
        """
        if message.lower() == "none":
            await self.config.guild(ctx.guild).event_start_message.set("")
            await ctx.send("✅ Event start messages disabled.")
        else:
            await self.config.guild(ctx.guild).event_start_message.set(message)
            await ctx.send(f"✅ Event start message set to: `{message}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def setdeletionwarning(self, ctx, *, message: str):
        """Set the warning message posted 15 minutes before channel deletion.

        Available placeholders:
        - {role} - Mentions the event role
        - {event} - Event name

        Examples:
        - `⚠️ These channels will be deleted in 15 minutes.` (default)
        - `{role} Event channels closing in 15 minutes!`
        - `⚠️ {event} channels will be removed shortly.`

        To disable deletion warnings, use: `none`
        """
        if message.lower() == "none":
            await self.config.guild(ctx.guild).deletion_warning_message.set("")
            await ctx.send("✅ Deletion warnings disabled.")
        else:
            await self.config.guild(ctx.guild).deletion_warning_message.set(message)
            await ctx.send(f"✅ Deletion warning message set to: `{message}`")

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

        # If a new divider name is provided, update it and rename existing divider
        if divider_name:
            await self.config.guild(ctx.guild).divider_name.set(divider_name)

            # Rename existing divider channel if it exists
            divider_channel_id = await self.config.guild(ctx.guild).divider_channel_id()
            if divider_channel_id:
                divider_channel = ctx.guild.get_channel(divider_channel_id)
                if divider_channel:
                    try:
                        await divider_channel.edit(name=divider_name, reason=f"Divider name updated by {ctx.author}")
                        log.info(f"Renamed divider channel to '{divider_name}'")
                    except discord.Forbidden:
                        await ctx.send("⚠️ Settings updated but couldn't rename existing divider - missing permissions.")
                        return
                    except Exception as e:
                        await ctx.send(f"⚠️ Settings updated but failed to rename existing divider: {e}")
                        return

            await ctx.send(f"✅ Divider channel {'enabled' if enabled else 'disabled'} with name: `{divider_name}`")
        else:
            await ctx.send(f"✅ Divider channel {'enabled' if enabled else 'disabled'}.")

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
        space_replacer = await self.config.guild(ctx.guild).space_replacer()
        announcement_message = await self.config.guild(ctx.guild).announcement_message()
        event_start_message = await self.config.guild(ctx.guild).event_start_message()
        deletion_warning_message = await self.config.guild(ctx.guild).deletion_warning_message()
        divider_enabled = await self.config.guild(ctx.guild).divider_enabled()
        divider_name = await self.config.guild(ctx.guild).divider_name()
        channel_name_limit = await self.config.guild(ctx.guild).channel_name_limit()
        channel_name_limit_char = await self.config.guild(ctx.guild).channel_name_limit_char()
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()

        category = ctx.guild.get_channel(category_id) if category_id else None
        category_name = category.name if category else "Not set"
        announcement_display = f"`{announcement_message}`" if announcement_message else "Disabled"
        event_start_display = f"`{event_start_message}`" if event_start_message else "Disabled"
        deletion_warning_display = f"`{deletion_warning_message}`" if deletion_warning_message else "Disabled"
        divider_display = f"Enabled (`{divider_name}`)" if divider_enabled else "Disabled"

        # Format voice multipliers display
        if voice_multipliers:
            multiplier_list = []
            for keyword, multiplier in sorted(voice_multipliers.items()):
                multiplier_list.append(f"`{keyword}`: {multiplier} (limit: {multiplier + 1})")
            voice_multiplier_display = ", ".join(multiplier_list)
        else:
            voice_multiplier_display = "Disabled"

        # Display channel name limit setting
        if channel_name_limit_char:
            name_limit_display = f"Truncate at `{channel_name_limit_char}` (character-based)"
        else:
            name_limit_display = f"{channel_name_limit} characters (numeric)"

        embed = discord.Embed(title="Event Channels Settings", color=discord.Color.blue())
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="Timezone", value=timezone, inline=False)
        embed.add_field(name="Creation Time", value=f"{creation_minutes} minutes before start", inline=False)
        embed.add_field(name="Deletion Time", value=f"{deletion_hours} hours after start", inline=False)
        embed.add_field(name="Role Format", value=f"`{role_format}`", inline=False)
        embed.add_field(name="Channel Format", value=f"`{channel_format}`", inline=False)
        embed.add_field(name="Space Replacer", value=f"`{space_replacer}`", inline=False)
        embed.add_field(name="Channel Name Limit", value=name_limit_display, inline=False)
        embed.add_field(name="Voice Multiplier", value=voice_multiplier_display, inline=False)
        embed.add_field(name="Announcement", value=announcement_display, inline=False)
        embed.add_field(name="Event Start Message", value=event_start_display, inline=False)
        embed.add_field(name="Deletion Warning", value=deletion_warning_display, inline=False)
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
                f"**Space Replacer:** `{space_replacer}`\n"
                f"**Channel Name Limit:** {name_limit_display}\n"
                f"**Voice Multiplier:** {voice_multiplier_display}\n"
                f"**Announcement:** {announcement_display}\n"
                f"**Event Start Message:** {event_start_display}\n"
                f"**Deletion Warning:** {deletion_warning_display}\n"
                f"**Divider Channel:** {divider_display}"
            )
            await ctx.send(message)

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.command()
    async def testchannellock(self, ctx):
        """Test the channel locking mechanism to verify bot permissions."""
        guild = ctx.guild
        category_id = await self.config.guild(guild).category_id()
        category = guild.get_channel(category_id) if category_id else None

        if not category:
            await ctx.send("❌ No event category configured. Use `seteventcategory` first.")
            return

        await ctx.send("🔄 Starting channel lock test...")

        test_role = None
        test_text_channel = None
        test_voice_channel = None

        try:
            # Create a test role
            test_role = await guild.create_role(
                name="🧪 Test Event Role",
                reason="Testing channel lock mechanism"
            )
            await ctx.send(f"✅ Created test role: {test_role.mention}")

            # Create test channels with permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                ),
                test_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                ),
            }

            # Create text channel without overwrites first
            test_text_channel = await guild.create_text_channel(
                name="🧪-test-event-text",
                category=category,
                reason="Testing channel lock mechanism"
            )
            await ctx.send(f"✅ Created test text channel: {test_text_channel.mention}")

            # Create voice channel without overwrites first
            test_voice_channel = await guild.create_voice_channel(
                name="🧪 Test Event Voice",
                category=category,
                reason="Testing channel lock mechanism"
            )
            await ctx.send(f"✅ Created test voice channel: `{test_voice_channel.name}`")

            # Now apply permission overwrites
            await test_text_channel.edit(overwrites=overwrites)
            await test_voice_channel.edit(overwrites=overwrites)
            await ctx.send(f"✅ Applied permission overwrites to channels")

            # Now attempt to lock the channels using the same logic as the actual deletion process
            await ctx.send("🔒 Attempting to lock channels...")

            locked_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                ),
                test_role: discord.PermissionOverwrite(
                    send_messages=False,  # Locked
                    speak=False,  # Locked in voice
                ),
            }

            await test_text_channel.edit(overwrites=locked_overwrites, reason="Testing channel lock")
            await test_voice_channel.edit(overwrites=locked_overwrites, reason="Testing channel lock")

            await ctx.send("✅ **SUCCESS**: Channels locked successfully!")
            await ctx.send("✅ Bot has correct permissions to lock channels before deletion.")

        except discord.Forbidden as e:
            await ctx.send(f"❌ **FAILED**: Missing permissions to lock channels.\n```{e}```")
        except Exception as e:
            await ctx.send(f"❌ **ERROR**: {type(e).__name__}: {e}")
        finally:
            # Cleanup
            await ctx.send("🧹 Cleaning up test channels and role...")
            if test_text_channel:
                try:
                    await test_text_channel.delete(reason="Channel lock test completed")
                except:
                    pass
            if test_voice_channel:
                try:
                    await test_voice_channel.delete(reason="Channel lock test completed")
                except:
                    pass
            if test_role:
                try:
                    await test_role.delete(reason="Channel lock test completed")
                except:
                    pass
            await ctx.send("✅ Test complete and cleanup finished.")

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.command()
    async def stresstest(self, ctx):
        """Comprehensive stress test of all EventChannels features including end-to-end event automation."""
        guild = ctx.guild
        category_id = await self.config.guild(guild).category_id()
        category = guild.get_channel(category_id) if category_id else None

        if not category:
            await ctx.send("❌ No event category configured. Use `seteventcategory` first.")
            return

        await ctx.send("🚀 **Starting comprehensive EventChannels stress test...**")
        await ctx.send("This will test: channel creation, permissions, voice multipliers, divider, locking, event automation, and cleanup.")

        # Track all created resources for cleanup
        test_roles = []
        test_channels = []
        test_events = []
        original_divider_roles = await self.config.guild(guild).divider_roles()
        test_results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }

        async def report_success(test_name: str):
            test_results["passed"] += 1
            await ctx.send(f"✅ **{test_name}**: PASSED")

        async def report_failure(test_name: str, error: str):
            test_results["failed"] += 1
            test_results["errors"].append(f"{test_name}: {error}")
            await ctx.send(f"❌ **{test_name}**: FAILED - {error}")

        try:
            # ========== TEST 1: End-to-End Event Creation ==========
            await ctx.send("\n**TEST 1: End-to-End Event Creation with Matching Role**")
            try:
                from zoneinfo import ZoneInfo

                # Get the server's configured timezone and role format
                tz_name = await self.config.guild(guild).timezone()
                server_tz = ZoneInfo(tz_name)
                role_format = await self.config.guild(guild).role_format()

                # Create a scheduled event that starts in 2 minutes
                event_start = datetime.now(timezone.utc) + timedelta(minutes=2)
                event_local_time = event_start.astimezone(server_tz)

                # Format the expected role name
                day_abbrev = event_local_time.strftime("%a")
                day = event_local_time.strftime("%d").lstrip("0")
                month_abbrev = event_local_time.strftime("%b")
                time_str = event_local_time.strftime("%H:%M")

                event_name = "🧪 E2E Test Event"
                expected_role_name = role_format.format(
                    name=event_name,
                    day_abbrev=day_abbrev,
                    day=day,
                    month_abbrev=month_abbrev,
                    time=time_str
                )

                # Create the matching role BEFORE creating the event
                e2e_role = await guild.create_role(
                    name=expected_role_name,
                    reason="E2E stress test - matching role for scheduled event"
                )
                test_roles.append(e2e_role)
                await ctx.send(f"✅ Created matching role: `{expected_role_name}`")

                # Create the scheduled event
                test_event = await guild.create_scheduled_event(
                    name=event_name,
                    start_time=event_start,
                    entity_type=discord.EntityType.voice,
                    privacy_level=discord.PrivacyLevel.guild_only,
                    location="🧪 Test Location",
                    reason="E2E stress test"
                )
                test_events.append(test_event)
                await ctx.send(f"✅ Created scheduled event: `{event_name}` (starts in 2 minutes)")

                # Wait for the bot to process the event (should create channels in 2 mins - 15 mins = immediately)
                creation_minutes = await self.config.guild(guild).creation_minutes()
                if creation_minutes >= 2:
                    # Channels should be created immediately
                    await ctx.send(f"⏳ Waiting for bot to process event (creation time: {creation_minutes} mins before start)...")
                    await asyncio.sleep(10)  # Wait 10 seconds for bot to create channels

                    # Check if channels were created
                    stored = await self.config.guild(guild).event_channels()
                    event_data = stored.get(str(test_event.id))

                    if event_data:
                        text_ch = guild.get_channel(event_data.get("text"))
                        voice_ch_ids = event_data.get("voice", [])
                        if isinstance(voice_ch_ids, int):
                            voice_ch_ids = [voice_ch_ids]

                        if text_ch and voice_ch_ids:
                            await ctx.send(f"✅ Bot automatically created channels: {text_ch.mention}")
                            # Track channels for cleanup
                            test_channels.append(text_ch)
                            for vc_id in voice_ch_ids:
                                vc = guild.get_channel(vc_id)
                                if vc:
                                    test_channels.append(vc)
                            await report_success("End-to-End Event Creation")
                        else:
                            await report_failure("End-to-End Event Creation", "Channels not found after creation")
                    else:
                        await report_failure("End-to-End Event Creation", "Event data not stored in config")
                else:
                    await ctx.send(f"⏭️ Skipping channel verification (creation time is {creation_minutes} mins, event starts in 2 mins)")
                    await report_success("End-to-End Event Creation (event created, channels scheduled)")

            except Exception as e:
                await report_failure("End-to-End Event Creation", str(e))

            # ========== TEST 2: Basic Channel Creation ==========
            await ctx.send("\n**TEST 2: Basic Channel Creation**")
            try:
                role1 = await guild.create_role(name="🧪 Stress Test Role 1", reason="Stress testing")
                test_roles.append(role1)

                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                    role1: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        connect=True,
                        speak=True,
                    ),
                }

                # Create channels without overwrites first
                text_ch1 = await guild.create_text_channel(
                    name="🧪-stress-test-1",
                    category=category,
                    reason="Stress testing"
                )
                test_channels.append(text_ch1)

                voice_ch1 = await guild.create_voice_channel(
                    name="🧪 Stress Test Voice 1",
                    category=category,
                    reason="Stress testing"
                )
                test_channels.append(voice_ch1)

                # Now apply permission overwrites
                await text_ch1.edit(overwrites=overwrites)
                await voice_ch1.edit(overwrites=overwrites)

                await report_success("Basic Channel Creation")
            except Exception as e:
                await report_failure("Basic Channel Creation", str(e))

            # ========== TEST 3: Permission Verification ==========
            await ctx.send("\n**TEST 3: Permission Verification**")
            try:
                # Verify bot can see and manage channels
                if text_ch1.permissions_for(guild.me).view_channel and \
                   text_ch1.permissions_for(guild.me).manage_channels and \
                   text_ch1.permissions_for(guild.me).send_messages:
                    await report_success("Bot Permission Verification")
                else:
                    await report_failure("Bot Permission Verification", "Bot missing expected permissions")

                # Verify role can see channels
                if text_ch1.permissions_for(role1).view_channel and \
                   text_ch1.permissions_for(role1).send_messages:
                    await report_success("Role Permission Verification")
                else:
                    await report_failure("Role Permission Verification", "Role missing expected permissions")

                # Verify default role cannot see
                if not text_ch1.permissions_for(guild.default_role).view_channel:
                    await report_success("Default Role Hidden Verification")
                else:
                    await report_failure("Default Role Hidden Verification", "Default role can see channel")
            except Exception as e:
                await report_failure("Permission Verification", str(e))

            # ========== TEST 4: Multiple Voice Channels (Voice Multiplier Simulation) ==========
            await ctx.send("\n**TEST 4: Multiple Voice Channels**")
            try:
                role2 = await guild.create_role(name="🧪 Stress Test Role 2", reason="Stress testing")
                test_roles.append(role2)

                # Create 3 voice channels to simulate voice multiplier
                for i in range(3):
                    voice_ch = await guild.create_voice_channel(
                        name=f"🧪 Multi Voice {i+1}",
                        category=category,
                        user_limit=5,
                        reason="Stress testing voice multiplier"
                    )
                    test_channels.append(voice_ch)

                await report_success("Multiple Voice Channels Creation")
            except Exception as e:
                await report_failure("Multiple Voice Channels Creation", str(e))

            # ========== TEST 5: Divider Channel Updates ==========
            await ctx.send("\n**TEST 5: Divider Channel Updates**")
            try:
                # Test adding roles to divider
                await self._update_divider_permissions(guild, role1, add=True)
                await asyncio.sleep(0.5)  # Brief delay for operation
                await self._update_divider_permissions(guild, role2, add=True)
                await asyncio.sleep(0.5)

                divider_channel_id = await self.config.guild(guild).divider_channel_id()
                if divider_channel_id:
                    divider = guild.get_channel(divider_channel_id)
                    if divider:
                        # Verify roles have access
                        if divider.permissions_for(role1).view_channel and \
                           divider.permissions_for(role2).view_channel:
                            await report_success("Divider Role Permissions")
                        else:
                            await report_failure("Divider Role Permissions", "Roles don't have view access")
                    else:
                        await report_failure("Divider Channel Updates", "Divider channel not found")
                else:
                    await report_failure("Divider Channel Updates", "No divider channel ID stored")
            except Exception as e:
                await report_failure("Divider Channel Updates", str(e))

            # ========== TEST 6: Message Sending ==========
            await ctx.send("\n**TEST 6: Message Sending**")
            try:
                test_msg = await text_ch1.send("🧪 Stress test message")
                await asyncio.sleep(0.5)
                await test_msg.delete()
                await report_success("Message Sending and Deletion")
            except Exception as e:
                await report_failure("Message Sending", str(e))

            # ========== TEST 7: Channel Locking ==========
            await ctx.send("\n**TEST 7: Channel Locking Mechanism**")
            try:
                locked_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                    role1: discord.PermissionOverwrite(
                        send_messages=False,
                        speak=False,
                    ),
                }

                await text_ch1.edit(overwrites=locked_overwrites, reason="Stress test lock")
                await voice_ch1.edit(overwrites=locked_overwrites, reason="Stress test lock")

                # Verify lock worked
                if not text_ch1.permissions_for(role1).send_messages and \
                   not voice_ch1.permissions_for(role1).speak:
                    await report_success("Channel Locking")
                else:
                    await report_failure("Channel Locking", "Permissions not properly locked")
            except Exception as e:
                await report_failure("Channel Locking", str(e))

            # ========== TEST 8: Concurrent Operations ==========
            await ctx.send("\n**TEST 8: Concurrent Channel Operations**")
            try:
                # Create multiple channels concurrently
                role3 = await guild.create_role(name="🧪 Concurrent Test Role", reason="Stress testing")
                test_roles.append(role3)

                tasks = []
                for i in range(3):
                    task = guild.create_text_channel(
                        name=f"🧪-concurrent-{i}",
                        category=category,
                        reason="Concurrent stress test"
                    )
                    tasks.append(task)

                concurrent_channels = await asyncio.gather(*tasks)
                test_channels.extend(concurrent_channels)

                if len(concurrent_channels) == 3:
                    await report_success("Concurrent Channel Creation")
                else:
                    await report_failure("Concurrent Channel Creation", f"Expected 3 channels, got {len(concurrent_channels)}")
            except Exception as e:
                await report_failure("Concurrent Channel Creation", str(e))

            # ========== TEST 9: Channel Name Formatting ==========
            await ctx.send("\n**TEST 9: Channel Name Formatting**")
            try:
                space_replacer = await self.config.guild(guild).space_replacer()
                test_name = "Test Event Name"
                formatted_name = test_name.lower().replace(" ", space_replacer)

                format_test_ch = await guild.create_text_channel(
                    name=f"🧪-{formatted_name}",
                    category=category,
                    reason="Testing name formatting"
                )
                test_channels.append(format_test_ch)

                if space_replacer in format_test_ch.name:
                    await report_success("Channel Name Formatting")
                else:
                    await report_failure("Channel Name Formatting", "Space replacer not applied correctly")
            except Exception as e:
                await report_failure("Channel Name Formatting", str(e))

            # ========== TEST 10: Rapid Create/Delete Cycle ==========
            await ctx.send("\n**TEST 10: Rapid Create/Delete Cycle**")
            try:
                temp_channels = []
                # Create 5 channels
                for i in range(5):
                    temp_ch = await guild.create_text_channel(
                        name=f"🧪-temp-{i}",
                        category=category,
                        reason="Rapid cycle test"
                    )
                    temp_channels.append(temp_ch)

                await asyncio.sleep(1)

                # Delete them all
                for ch in temp_channels:
                    await ch.delete(reason="Rapid cycle test cleanup")

                await report_success("Rapid Create/Delete Cycle")
            except Exception as e:
                await report_failure("Rapid Create/Delete Cycle", str(e))

            # ========== TEST 11: Permission Overwrite Updates ==========
            await ctx.send("\n**TEST 11: Permission Overwrite Updates**")
            try:
                # Update permissions on existing channel
                new_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                    role3: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    ),
                }

                await concurrent_channels[0].edit(overwrites=new_overwrites, reason="Permission update test")

                if concurrent_channels[0].permissions_for(role3).view_channel:
                    await report_success("Permission Overwrite Updates")
                else:
                    await report_failure("Permission Overwrite Updates", "Updated permissions not applied")
            except Exception as e:
                await report_failure("Permission Overwrite Updates", str(e))

        except Exception as e:
            await ctx.send(f"💥 **CRITICAL ERROR**: {type(e).__name__}: {e}")
            test_results["errors"].append(f"Critical: {e}")

        finally:
            # ========== CLEANUP ==========
            await ctx.send("\n**🧹 CLEANUP: Removing all test resources...**")

            # Remove test roles from divider
            try:
                for role in test_roles:
                    await self._update_divider_permissions(guild, role, add=False)
            except Exception as e:
                await ctx.send(f"⚠️ Warning during divider cleanup: {e}")

            # Delete all test channels
            deleted_channels = 0
            for channel in test_channels:
                try:
                    await channel.delete(reason="Stress test cleanup")
                    deleted_channels += 1
                except:
                    pass

            # Delete all test roles
            deleted_roles = 0
            for role in test_roles:
                try:
                    await role.delete(reason="Stress test cleanup")
                    deleted_roles += 1
                except:
                    pass

            # Delete all test events
            deleted_events = 0
            for event in test_events:
                try:
                    await event.delete(reason="Stress test cleanup")
                    deleted_events += 1
                except:
                    pass

            if deleted_events > 0:
                await ctx.send(f"✅ Cleanup complete: {deleted_channels} channels, {deleted_roles} roles, {deleted_events} events removed")
            else:
                await ctx.send(f"✅ Cleanup complete: {deleted_channels} channels, {deleted_roles} roles removed")

            # ========== FINAL REPORT ==========
            await ctx.send("\n" + "="*50)
            await ctx.send("**📊 STRESS TEST RESULTS**")
            await ctx.send("="*50)

            total_tests = test_results["passed"] + test_results["failed"]
            pass_rate = (test_results["passed"] / total_tests * 100) if total_tests > 0 else 0

            embed = discord.Embed(
                title="EventChannels Stress Test Results",
                color=discord.Color.green() if test_results["failed"] == 0 else discord.Color.orange()
            )
            embed.add_field(name="Total Tests", value=str(total_tests), inline=True)
            embed.add_field(name="Passed ✅", value=str(test_results["passed"]), inline=True)
            embed.add_field(name="Failed ❌", value=str(test_results["failed"]), inline=True)
            embed.add_field(name="Pass Rate", value=f"{pass_rate:.1f}%", inline=False)

            if test_results["errors"]:
                error_text = "\n".join([f"• {err}" for err in test_results["errors"][:10]])  # Limit to 10 errors
                embed.add_field(name="Errors", value=error_text, inline=False)

            try:
                await ctx.send(embed=embed)
            except:
                # Fallback to text
                await ctx.send(
                    f"**Total Tests**: {total_tests}\n"
                    f"**Passed**: {test_results['passed']} ✅\n"
                    f"**Failed**: {test_results['failed']} ❌\n"
                    f"**Pass Rate**: {pass_rate:.1f}%"
                )

            if test_results["failed"] == 0:
                await ctx.send("🎉 **ALL TESTS PASSED!** EventChannels cog is functioning correctly.")
            else:
                await ctx.send("⚠️ **SOME TESTS FAILED** - Review errors above for details.")

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

    async def _cleanup_divider_if_empty(self, guild: discord.Guild):
        """Delete the divider channel if no event channels remain."""
        # Check if there are any active event channels
        stored = await self.config.guild(guild).event_channels()

        # Check if any events still have active channels
        has_active_channels = False
        for event_id, data in stored.items():
            text_channel = guild.get_channel(data.get("text"))

            # Handle both old format (single ID) and new format (list of IDs)
            voice_channel_ids = data.get("voice", [])
            if isinstance(voice_channel_ids, int):
                voice_channel_ids = [voice_channel_ids]

            has_voice_channels = any(guild.get_channel(vc_id) for vc_id in voice_channel_ids)

            if text_channel or has_voice_channels:
                has_active_channels = True
                break

        # Only delete divider if no event channels remain
        if not has_active_channels:
            divider_channel_id = await self.config.guild(guild).divider_channel_id()
            if divider_channel_id:
                divider_channel = guild.get_channel(divider_channel_id)
                if divider_channel:
                    try:
                        await divider_channel.delete(reason="No event channels remain - cleaning up divider channel")
                        log.info(f"Deleted divider channel in '{guild.name}' - no event channels remain")
                    except (discord.Forbidden, discord.NotFound):
                        pass

                # Clear the stored divider data
                await self.config.guild(guild).divider_channel_id.set(None)
                await self.config.guild(guild).divider_roles.set([])

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

        # Check if bot's role is high enough to manage this role's permissions
        bot_top_role = guild.me.top_role
        if role.position >= bot_top_role.position:
            log.warning(f"⚠️ Cannot manage permissions for role '{role.name}' (position: {role.position}) - bot's top role '{bot_top_role.name}' (position: {bot_top_role.position}) is not high enough. Skipping divider permissions update.")
            return

        divider_roles = await self.config.guild(guild).divider_roles()
        log.info(f"Updating divider permissions: add={add}, role='{role.name}', current_roles={divider_roles}")

        try:
            if add and role.id not in divider_roles:
                # Build complete overwrites dictionary including the new role
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=False,
                        send_messages=False,
                        add_reactions=False,
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        manage_channels=True,
                    ),
                }

                # Add all existing tracked roles
                for existing_role_id in divider_roles:
                    existing_role = guild.get_role(existing_role_id)
                    if existing_role:
                        overwrites[existing_role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            add_reactions=False,
                        )

                # Add the new role
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False,
                )

                log.info(f"Adding permission overwrite for role '{role.name}' (ID: {role.id}) to divider channel '{divider_channel.name}'")

                # Apply all overwrites at once using edit() - bypasses role hierarchy check
                await divider_channel.edit(
                    overwrites=overwrites,
                    reason=f"Adding event role '{role.name}' to divider channel"
                )

                divider_roles.append(role.id)
                await self.config.guild(guild).divider_roles.set(divider_roles)
                log.info(f"✅ Successfully added role '{role.name}' to divider channel permissions - can view but not send messages")
            elif not add and role.id in divider_roles:
                # Build complete overwrites dictionary without the removed role
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=False,
                        send_messages=False,
                        add_reactions=False,
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        manage_channels=True,
                    ),
                }

                # Add remaining tracked roles (excluding the one being removed)
                for existing_role_id in divider_roles:
                    if existing_role_id != role.id:
                        existing_role = guild.get_role(existing_role_id)
                        if existing_role:
                            overwrites[existing_role] = discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=False,
                                add_reactions=False,
                            )

                log.info(f"Removing permission overwrite for role '{role.name}' from divider channel")

                # Apply all overwrites at once using edit() - bypasses role hierarchy check
                await divider_channel.edit(
                    overwrites=overwrites,
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
            space_replacer = await self.config.guild(guild).space_replacer()
            channel_name_limit = await self.config.guild(guild).channel_name_limit()
            channel_name_limit_char = await self.config.guild(guild).channel_name_limit_char()
            base_name = event.name.lower().replace(" ", space_replacer)

            # Apply character limit to base name only (not the full channel name)
            if channel_name_limit_char:
                # Character-based limiting: truncate at first occurrence (inclusive)
                char_index = base_name.find(channel_name_limit_char)
                if char_index != -1:
                    # Found the character, truncate up to and including it
                    base_name = base_name[:char_index + len(channel_name_limit_char)]
                # If character not found, keep full name (or fall back to numeric limit)
                elif len(base_name) > channel_name_limit:
                    base_name = base_name[:channel_name_limit]
            elif len(base_name) > channel_name_limit:
                # Numeric limiting
                base_name = base_name[:channel_name_limit]

            # Now format with the limited base name
            text_channel_name = channel_format.format(name=base_name, type="text")

            # Check for voice multipliers
            voice_multipliers = await self.config.guild(guild).voice_multipliers()

            # Find the first matching keyword in the event name
            matched_keyword = None
            voice_multiplier_capacity = None
            event_name_lower = event.name.lower()

            for keyword, multiplier in voice_multipliers.items():
                if keyword in event_name_lower:
                    matched_keyword = keyword
                    voice_multiplier_capacity = multiplier
                    break

            # Calculate number of voice channels based on role member count
            if matched_keyword and voice_multiplier_capacity and role:
                role_member_count = len(role.members)
                # Formula: max(1, floor(members / multiplier))
                voice_count = max(1, role_member_count // voice_multiplier_capacity)
                # User limit is multiplier + 1
                user_limit = voice_multiplier_capacity + 1
                log.info(f"Voice multiplier active for keyword '{matched_keyword}': {role_member_count} members / {voice_multiplier_capacity} = {voice_count} channel(s) with limit {user_limit}")
            else:
                voice_count = 1
                user_limit = 0  # 0 = unlimited

            text_channel = None
            voice_channels = []

            # Ensure divider channel exists before creating event channels
            await self._ensure_divider_channel(guild, category)

            try:
                # Create text channel
                text_channel = await guild.create_text_channel(
                    name=text_channel_name,
                    category=category,
                    reason=f"Scheduled event '{event.name}' starting soon",
                )
                log.info(f"Created text channel: {text_channel.name}")

                # Create voice channel(s)
                for i in range(voice_count):
                    # Generate voice channel name (base_name is already limited)
                    if voice_count > 1:
                        # Multiple channels: append number (e.g., "voice 1", "voice 2")
                        voice_channel_name = channel_format.format(name=base_name, type="voice")
                        voice_channel_name = f"{voice_channel_name} {i + 1}"
                    else:
                        # Single channel: use base name
                        voice_channel_name = channel_format.format(name=base_name, type="voice")

                    voice_channel = await guild.create_voice_channel(
                        name=voice_channel_name,
                        category=category,
                        user_limit=user_limit,  # Set user limit (0 = unlimited)
                        reason=f"Scheduled event '{event.name}' starting soon",
                    )
                    voice_channels.append(voice_channel)
                    log.info(f"Created voice channel: {voice_channel.name} (user limit: {user_limit if user_limit > 0 else 'unlimited'})")

                # Now apply permission overwrites
                await text_channel.edit(overwrites=overwrites)
                for voice_channel in voice_channels:
                    await voice_channel.edit(overwrites=overwrites)
                log.info(f"Successfully applied permissions to {len(voice_channels) + 1} channel(s) for event '{event.name}'")

                # Add role to divider permissions
                await self._update_divider_permissions(guild, role, add=True)

                # Send announcement message if configured
                announcement_template = await self.config.guild(guild).announcement_message()
                if announcement_template:
                    # Format event time as Discord relative timestamp
                    unix_timestamp = int(event.start_time.timestamp())
                    discord_timestamp = f"<t:{unix_timestamp}:R>"

                    # Format the announcement message
                    try:
                        announcement = announcement_template.format(
                            role=role.mention,
                            event=event.name,
                            time=discord_timestamp
                        )
                    except KeyError as e:
                        log.error(f"Invalid placeholder {e} in announcement message template. Valid placeholders: {{role}}, {{event}}, {{time}}")
                        announcement = None

                    if announcement:
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
                for voice_channel in voice_channels:
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
                for voice_channel in voice_channels:
                    try:
                        await voice_channel.delete(reason="Creation failed")
                    except:
                        pass
                return

            stored[str(event.id)] = {
                "text": text_channel.id,
                "voice": [vc.id for vc in voice_channels],  # Store list of voice channel IDs
                "role": role.id,
            }
            await self.config.guild(guild).event_channels.set(stored)

            # ---------- Event Start ----------

            # Wait until event starts
            await asyncio.sleep(max(0, (start_time - datetime.now(timezone.utc)).total_seconds()))

            # Send event start message if configured
            event_start_template = await self.config.guild(guild).event_start_message()
            if event_start_template:
                try:
                    event_start_msg = event_start_template.format(
                        role=role.mention,
                        event=event.name
                    )
                except KeyError as e:
                    log.error(f"Invalid placeholder {e} in event start message template. Valid placeholders: {{role}}, {{event}}")
                    event_start_msg = None

                if event_start_msg:
                    try:
                        await text_channel.send(event_start_msg, allowed_mentions=discord.AllowedMentions(roles=True))
                        log.info(f"Sent event start message to {text_channel.name}")
                    except discord.Forbidden:
                        log.warning(f"Could not send event start message to {text_channel.name} - missing permissions")

            # ---------- Deletion Warning ----------

            # Calculate when to send deletion warning (15 minutes before deletion)
            warning_time = delete_time - timedelta(minutes=15)
            await asyncio.sleep(max(0, (warning_time - datetime.now(timezone.utc)).total_seconds()))

            # Send deletion warning and lock channels
            deletion_warning_template = await self.config.guild(guild).deletion_warning_message()
            if deletion_warning_template:
                try:
                    deletion_warning_msg = deletion_warning_template.format(
                        role=role.mention,
                        event=event.name
                    )
                except KeyError as e:
                    log.error(f"Invalid placeholder {e} in deletion warning message template. Valid placeholders: {{role}}, {{event}}")
                    deletion_warning_msg = None

                if deletion_warning_msg:
                    try:
                        await text_channel.send(deletion_warning_msg, allowed_mentions=discord.AllowedMentions(roles=True))
                        log.info(f"Sent deletion warning to {text_channel.name}")
                    except discord.Forbidden:
                        log.warning(f"Could not send deletion warning to {text_channel.name} - missing permissions")

            # Lock channels - remove send_messages permission for the role
            # Refetch channels and role to ensure we have current objects
            stored_data = await self.config.guild(guild).event_channels()
            event_data = stored_data.get(str(event.id))
            if event_data:
                text_channel = guild.get_channel(event_data.get("text"))
                voice_channel_ids = event_data.get("voice", [])
                # Handle both old format (single ID) and new format (list of IDs)
                if isinstance(voice_channel_ids, int):
                    voice_channel_ids = [voice_channel_ids]
                voice_channels = [guild.get_channel(vc_id) for vc_id in voice_channel_ids if guild.get_channel(vc_id)]
                role = guild.get_role(event_data.get("role"))

                if text_channel and voice_channels and role:
                    try:
                        locked_overwrites = {
                            guild.default_role: discord.PermissionOverwrite(view_channel=False),
                            guild.me: discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=True,
                                manage_channels=True,
                            ),
                            role: discord.PermissionOverwrite(
                                send_messages=False,  # Locked
                                speak=False,  # Locked in voice
                            ),
                        }
                        await text_channel.edit(overwrites=locked_overwrites, reason="Locking channel before deletion")
                        for voice_channel in voice_channels:
                            await voice_channel.edit(overwrites=locked_overwrites, reason="Locking channel before deletion")
                        log.info(f"Locked {len(voice_channels) + 1} channel(s) for event '{event.name}'")
                    except discord.Forbidden:
                        log.warning(f"Could not lock channels for event '{event.name}' - missing permissions")
                    except Exception as e:
                        log.error(f"Failed to lock channels for event '{event.name}': {e}")
                else:
                    log.warning(f"Could not lock channels for event '{event.name}' - channels not found")
            else:
                log.warning(f"Could not lock channels for event '{event.name}' - event data not found")

            # ---------- Cleanup ----------

            # Wait the remaining 15 minutes before deletion
            await asyncio.sleep(max(0, (delete_time - datetime.now(timezone.utc)).total_seconds()))

            # Refetch stored data to ensure we have current state
            stored = await self.config.guild(guild).event_channels()
            data = stored.get(str(event.id))
            if not data:
                return

            # Delete text channel
            text_channel = guild.get_channel(data.get("text"))
            if text_channel:
                try:
                    await text_channel.delete(reason="Scheduled event ended")
                except discord.NotFound:
                    pass

            # Delete all voice channels
            voice_channel_ids = data.get("voice", [])
            # Handle both old format (single ID) and new format (list of IDs)
            if isinstance(voice_channel_ids, int):
                voice_channel_ids = [voice_channel_ids]

            for vc_id in voice_channel_ids:
                voice_channel = guild.get_channel(vc_id)
                if voice_channel:
                    try:
                        await voice_channel.delete(reason="Scheduled event ended")
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

            # Check if divider should be deleted (no more event roles)
            await self._cleanup_divider_if_empty(guild)
        except asyncio.CancelledError:
            # Task was cancelled - clean up if channels were created
            stored = await self.config.guild(guild).event_channels()
            data = stored.get(str(event.id))
            if data:
                # Delete text channel
                text_channel = guild.get_channel(data.get("text"))
                if text_channel:
                    try:
                        await text_channel.delete(reason="Scheduled event cancelled")
                    except (discord.NotFound, discord.Forbidden):
                        pass

                # Delete all voice channels
                voice_channel_ids = data.get("voice", [])
                # Handle both old format (single ID) and new format (list of IDs)
                if isinstance(voice_channel_ids, int):
                    voice_channel_ids = [voice_channel_ids]

                for vc_id in voice_channel_ids:
                    voice_channel = guild.get_channel(vc_id)
                    if voice_channel:
                        try:
                            await voice_channel.delete(reason="Scheduled event cancelled")
                        except (discord.NotFound, discord.Forbidden):
                            pass

                # Remove role from divider permissions
                role = guild.get_role(data["role"])
                if role:
                    await self._update_divider_permissions(guild, role, add=False)
                stored.pop(str(event.id), None)
                await self.config.guild(guild).event_channels.set(stored)

                # Check if divider should be deleted (no more event roles)
                await self._cleanup_divider_if_empty(guild)
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

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Clean up event channels when an event role is deleted externally."""
        guild = role.guild
        stored = await self.config.guild(guild).event_channels()

        # Find events associated with this role
        events_to_remove = []
        for event_id, data in stored.items():
            if data.get("role") == role.id:
                events_to_remove.append(event_id)
                log.info(f"Event role '{role.name}' was deleted externally - cleaning up channels for event {event_id}")

                # Delete text channel
                text_channel_id = data.get("text")
                if text_channel_id:
                    text_channel = guild.get_channel(text_channel_id)
                    if text_channel:
                        try:
                            await text_channel.delete(reason=f"Event role '{role.name}' was deleted")
                            log.info(f"Deleted channel {text_channel.name} - associated role was deleted")
                        except (discord.NotFound, discord.Forbidden) as e:
                            log.warning(f"Could not delete channel {text_channel_id}: {e}")

                # Delete all voice channels
                voice_channel_ids = data.get("voice", [])
                # Handle both old format (single ID) and new format (list of IDs)
                if isinstance(voice_channel_ids, int):
                    voice_channel_ids = [voice_channel_ids]

                for vc_id in voice_channel_ids:
                    voice_channel = guild.get_channel(vc_id)
                    if voice_channel:
                        try:
                            await voice_channel.delete(reason=f"Event role '{role.name}' was deleted")
                            log.info(f"Deleted channel {voice_channel.name} - associated role was deleted")
                        except (discord.NotFound, discord.Forbidden) as e:
                            log.warning(f"Could not delete channel {vc_id}: {e}")

                # Cancel any active task for this event
                task = self.active_tasks.get(int(event_id))
                if task and not task.done():
                    task.cancel()
                    self.active_tasks.pop(int(event_id), None)

        # Remove events from storage
        for event_id in events_to_remove:
            stored.pop(event_id, None)

        if events_to_remove:
            await self.config.guild(guild).event_channels.set(stored)

            # Remove role from divider permissions tracking
            divider_roles = await self.config.guild(guild).divider_roles()
            if role.id in divider_roles:
                divider_roles.remove(role.id)
                await self.config.guild(guild).divider_roles.set(divider_roles)
                log.info(f"Removed deleted role '{role.name}' from divider permissions tracking")

            # Check if divider should be deleted (no more event roles)
            await self._cleanup_divider_if_empty(guild)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Clean up stored data when event channels are deleted externally."""
        guild = channel.guild
        stored = await self.config.guild(guild).event_channels()

        # Check if this is a divider channel
        divider_channel_id = await self.config.guild(guild).divider_channel_id()
        if divider_channel_id == channel.id:
            log.info(f"Divider channel '{channel.name}' was deleted externally - clearing stored data")
            await self.config.guild(guild).divider_channel_id.set(None)
            return

        # Check if this is an event channel
        event_to_remove = None
        for event_id, data in stored.items():
            # Check if it's the text channel
            is_text_channel = channel.id == data.get("text")

            # Check if it's a voice channel
            voice_channel_ids = data.get("voice", [])
            # Handle both old format (single ID) and new format (list of IDs)
            if isinstance(voice_channel_ids, int):
                voice_channel_ids = [voice_channel_ids]
            is_voice_channel = channel.id in voice_channel_ids

            if is_text_channel or is_voice_channel:
                log.info(f"Event channel '{channel.name}' was deleted externally - checking if cleanup is needed")

                # Check if all channels are gone
                text_channel = guild.get_channel(data.get("text")) if data.get("text") else None
                voice_channels_exist = any(guild.get_channel(vc_id) for vc_id in voice_channel_ids)

                if not text_channel and not voice_channels_exist:
                    # All channels are gone, clean up completely
                    log.info(f"All event channels are gone for event {event_id} - cleaning up completely")
                    event_to_remove = event_id

                    # Delete the role if it exists
                    role_id = data.get("role")
                    if role_id:
                        role = guild.get_role(role_id)
                        if role:
                            # Remove from divider first
                            await self._update_divider_permissions(guild, role, add=False)
                            try:
                                await role.delete(reason="Event channels were deleted")
                                log.info(f"Deleted role for event {event_id} - channels were deleted externally")
                            except discord.Forbidden:
                                log.warning(f"Could not delete role for event {event_id}")

                    # Cancel any active task
                    task = self.active_tasks.get(int(event_id))
                    if task and not task.done():
                        task.cancel()
                        self.active_tasks.pop(int(event_id), None)

                break

        # Remove event from storage
        if event_to_remove:
            stored.pop(event_to_remove, None)
            await self.config.guild(guild).event_channels.set(stored)

            # Check if divider should be deleted (no more event roles)
            await self._cleanup_divider_if_empty(guild)

    def cog_unload(self):
        """Cancel all active tasks when cog is unloaded."""
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()