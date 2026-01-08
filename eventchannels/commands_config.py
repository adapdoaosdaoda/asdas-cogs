import logging

import discord
from redbot.core import commands

log = logging.getLogger("red.eventchannels")


class CommandsConfigMixin:
    """Mixin class containing configuration setter commands for EventChannels cog."""

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def seteventcategory(self, ctx, category: discord.CategoryChannel):
        """Set the category where event channels will be created."""
        await self.config.guild(ctx.guild).category_id.set(category.id)
        await ctx.send(f"✅ Event channels will be created in **{category.name}**.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
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
    async def seteventdeletion(self, ctx, hours: int):
        """Set how many hours after event start channels are deleted (default: 4)."""
        if hours < 0:
            await ctx.send("❌ Hours must be a positive number.")
            return
        await self.config.guild(ctx.guild).deletion_hours.set(hours)
        await ctx.send(f"✅ Event channels will be deleted **{hours} hours** after event start.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
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

                # Apply channel name limit
                channel_name_limit = await self.config.guild(ctx.guild).channel_name_limit()
                channel_name_limit_char = await self.config.guild(ctx.guild).channel_name_limit_char()

                if channel_name_limit_char:
                    # Character-based limiting: truncate before first occurrence (exclusive)
                    char_index = base_name.find(channel_name_limit_char)
                    if char_index != -1:
                        # Found the character, truncate before it
                        base_name = base_name[:char_index]
                    # If character not found, keep full name (or fall back to numeric limit)
                    elif len(base_name) > channel_name_limit:
                        base_name = base_name[:channel_name_limit]
                elif len(base_name) > channel_name_limit:
                    # Numeric limiting
                    base_name = base_name[:channel_name_limit]

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
    async def setchannelnamelimit(self, ctx, limit: str):
        """Set the maximum character limit for channel names.

        You can either specify a number or a character to truncate at.

        **Numeric Limit:**
        - Truncates the event name to a specific number of characters
        - Discord's maximum is 100 characters

        **Character-Based Limit:**
        - Truncates before the first occurrence of a specific character (exclusive)
        - Useful for cutting at specific separators

        Examples:
        - `[p]eventchannels setchannelnamelimit 50` - Limit to 50 characters
        - `[p]eventchannels setchannelnamelimit ﹕` - Truncate before first "﹕" (excluding it)
        - `[p]eventchannels setchannelnamelimit :` - Truncate before first ":" (excluding it)
        - `[p]eventchannels setchannelnamelimit 100` - Use Discord's maximum (default)
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
            await ctx.send(f"✅ Channel name limit set to truncate before first occurrence of **'{limit}'** (exclusive).")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
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
        - `[p]eventchannels setvoicemultiplier hero 9`
          - 10 role members → 1 channel (limit: 10 users)
          - 18 role members → 2 channels (limit: 10 users each)
          - 27 role members → 3 channels (limit: 10 users each)

        - `[p]eventchannels setvoicemultiplier sword 4`
          - 5 role members → 1 channel (limit: 5 users)
          - 12 role members → 3 channels (limit: 5 users each)
          - 20 role members → 5 channels (limit: 5 users each)

        To remove a keyword, use `[p]eventchannels removevoicemultiplier <keyword>`
        To see all configured multipliers, use `[p]eventchannels listvoicemultipliers`
        To disable all multipliers, use `[p]eventchannels disablevoicemultiplier`
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
    async def disablevoicemultiplier(self, ctx):
        """Disable all voice multipliers.

        This will clear all configured keyword-multiplier pairs and restore the default
        behavior of creating only one voice channel per event.
        """
        await self.config.guild(ctx.guild).voice_multipliers.set({})
        await ctx.send("✅ All voice multipliers disabled. All events will create a single voice channel.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def removevoicemultiplier(self, ctx, keyword: str):
        """Remove a specific voice multiplier keyword.

        **Parameters:**
        - keyword: The keyword to remove (case-insensitive)

        **Example:**
        - `[p]eventchannels removevoicemultiplier hero`
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
    async def setminimumroles(self, ctx, keyword: str, minimum: int):
        """Set minimum role members required for a keyword to create channels.

        When an event name contains the specified keyword, channels will ONLY be created
        if the event role has at least this many members. If the minimum is not met,
        NO channels will be created at all.

        This works in conjunction with voice multipliers. If both are configured for
        the same keyword, the minimum role check happens first.

        **Parameters:**
        - keyword: The keyword to enforce minimum on (case-insensitive, must match a configured multiplier)
        - minimum: Minimum number of role members required (1-999)

        **Examples:**
        - `[p]eventchannels setminimumroles hero 10`
          - If "Hero Raid" event has fewer than 10 role members, no channels are created
          - If it has 10 or more members, channels are created according to the multiplier

        - `[p]eventchannels setminimumroles sword 5`
          - Events with "sword" in the name need at least 5 role members to create channels

        To remove a minimum requirement, use `[p]eventchannels removeminimumroles <keyword>`
        To see all configured minimums, use `[p]eventchannels listminimumroles`
        """
        if minimum < 1:
            await ctx.send("❌ Minimum must be at least 1.")
            return
        if minimum > 999:
            await ctx.send("❌ Minimum cannot exceed 999.")
            return

        # Check if the keyword has a multiplier configured
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()
        keyword_lower = keyword.lower()

        if keyword_lower not in voice_multipliers:
            await ctx.send(
                f"⚠️ Warning: Keyword **'{keyword}'** does not have a voice multiplier configured.\n"
                f"The minimum role requirement will have no effect until you set a multiplier.\n"
                f"Use `{ctx.clean_prefix}eventchannels setvoicemultiplier {keyword} <multiplier>` first."
            )

        # Get current minimums dictionary
        voice_minimum_roles = await self.config.guild(ctx.guild).voice_minimum_roles()

        # Add or update the keyword
        voice_minimum_roles[keyword_lower] = minimum

        # Save back to config
        await self.config.guild(ctx.guild).voice_minimum_roles.set(voice_minimum_roles)

        await ctx.send(
            f"✅ Minimum role requirement set for keyword **'{keyword}'**:\n"
            f"• Minimum members required: **{minimum}**\n"
            f"• If the event role has fewer than {minimum} members, NO channels will be created\n"
            f"• If the event role has {minimum} or more members, channels will be created normally\n\n"
            f"Use `{ctx.clean_prefix}listminimumroles` to see all configured minimums."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def removeminimumroles(self, ctx, keyword: str):
        """Remove a specific minimum role requirement.

        **Parameters:**
        - keyword: The keyword to remove the minimum requirement from (case-insensitive)

        **Example:**
        - `[p]eventchannels removeminimumroles hero`
        """
        voice_minimum_roles = await self.config.guild(ctx.guild).voice_minimum_roles()
        keyword_lower = keyword.lower()

        if keyword_lower not in voice_minimum_roles:
            await ctx.send(f"❌ Keyword **'{keyword}'** does not have a minimum role requirement configured.")
            return

        # Remove the keyword
        del voice_minimum_roles[keyword_lower]

        # Save back to config
        await self.config.guild(ctx.guild).voice_minimum_roles.set(voice_minimum_roles)

        await ctx.send(f"✅ Removed minimum role requirement for keyword **'{keyword}'**.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def addwhitelistedrole(self, ctx, role: discord.Role):
        """Add a role to the whitelist for automatic channel permissions.

        Whitelisted roles will automatically receive view, read, connect, and speak
        permissions in all created event channels.

        **Parameters:**
        - role: The role to whitelist (mention or role ID)

        **Example:**
        - `[p]eventchannels addwhitelistedrole @Staff`
        - `[p]eventchannels addwhitelistedrole 123456789012345678`
        """
        whitelisted_roles = await self.config.guild(ctx.guild).whitelisted_roles()

        if role.id in whitelisted_roles:
            await ctx.send(f"❌ Role **{role.name}** is already whitelisted.")
            return

        # Add the role ID to the whitelist
        whitelisted_roles.append(role.id)

        # Save back to config
        await self.config.guild(ctx.guild).whitelisted_roles.set(whitelisted_roles)

        await ctx.send(
            f"✅ Added **{role.name}** to the whitelist.\n"
            f"This role will now automatically receive view, read, connect, and speak permissions in all event channels."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def removewhitelistedrole(self, ctx, role: discord.Role):
        """Remove a role from the whitelist.

        **Parameters:**
        - role: The role to remove from whitelist (mention or role ID)

        **Example:**
        - `[p]eventchannels removewhitelistedrole @Staff`
        - `[p]eventchannels removewhitelistedrole 123456789012345678`
        """
        whitelisted_roles = await self.config.guild(ctx.guild).whitelisted_roles()

        if role.id not in whitelisted_roles:
            await ctx.send(f"❌ Role **{role.name}** is not whitelisted.")
            return

        # Remove the role ID from the whitelist
        whitelisted_roles.remove(role.id)

        # Save back to config
        await self.config.guild(ctx.guild).whitelisted_roles.set(whitelisted_roles)

        await ctx.send(f"✅ Removed **{role.name}** from the whitelist.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
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
    async def seteventdivider(self, ctx, enabled: bool, *, divider_name: str = None):
        """Enable/disable divider channel and optionally set its name.

        Examples:
        - `[p]eventchannels setdivider True` - Enable divider with default name
        - `[p]eventchannels setdivider True ━━━━━━ EVENT CHANNELS ━━━━━━` - Enable with custom name
        - `[p]eventchannels setdivider False` - Disable divider channel

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
    async def linkthreadtoevent(self, ctx, thread: discord.Thread, event_id: str):
        """Manually link a forum thread to a scheduled event.

        This command bypasses the automatic name-matching system and allows you to
        manually link any forum thread to any scheduled event.

        **Parameters:**
        - thread: The forum thread (link, mention, or ID)
        - event_id: The ID of the scheduled event

        **Examples:**
        - `[p]eventchannels linkthreadtoevent <thread_link> 1234567890`
        - `[p]eventchannels linkthreadtoevent 9876543210 1234567890`

        **How to get an event ID:**
        1. Right-click on the event in Discord
        2. Click "Copy Event ID" (you need Developer Mode enabled)
        """
        # Verify it's a forum thread
        if not isinstance(thread.parent, discord.ForumChannel):
            await ctx.send("❌ The provided channel is not a forum thread.")
            return

        # Try to find the scheduled event
        try:
            event_id_int = int(event_id)
        except ValueError:
            await ctx.send(f"❌ Invalid event ID: `{event_id}`. Event IDs must be numeric.")
            return

        # Find the event
        event = None
        for scheduled_event in ctx.guild.scheduled_events:
            if scheduled_event.id == event_id_int:
                event = scheduled_event
                break

        if not event:
            await ctx.send(f"❌ No scheduled event found with ID: `{event_id}`")
            return

        event_id_str = str(event_id_int)

        # Link the thread to the event
        async with self._config_lock:
            # Store in thread_event_links (always, regardless of whether channels exist)
            thread_links = await self.config.guild(ctx.guild).thread_event_links()

            # Check if thread is already linked to a different event
            old_event_id = thread_links.get(str(thread.id))
            if old_event_id and old_event_id != event_id_str:
                await ctx.send(
                    f"⚠️ Warning: Thread **'{thread.name}'** was already linked to event ID {old_event_id}. "
                    f"Relinking to **'{event.name}'** (ID: {event_id})."
                )

            thread_links[str(thread.id)] = event_id_str
            await self.config.guild(ctx.guild).thread_event_links.set(thread_links)

            # Also add to event_channels if channels exist
            event_channels = await self.config.guild(ctx.guild).event_channels()
            role_id = None
            role = None

            if event_id_str in event_channels:
                event_channels[event_id_str]["forum_thread"] = thread.id
                await self.config.guild(ctx.guild).event_channels.set(event_channels)
                role_id = event_channels[event_id_str].get("role")
                role = ctx.guild.get_role(role_id) if role_id else None
                log.info(f"Manually linked forum thread '{thread.name}' (ID: {thread.id}) to event '{event.name}' (ID: {event_id}) with existing channels by {ctx.author}")

                await ctx.send(
                    f"✅ Successfully linked forum thread **'{thread.name}'** to event **'{event.name}'** (ID: {event_id})\n"
                    f"Event role: {role.mention if role else 'Not found'}\n"
                    f"Thread: {thread.mention}\n\n"
                    f"Event channels exist. You can now use `[p]forumthreadmessage addbutton {thread.id}` to add the role button."
                )
            else:
                log.info(f"Manually linked forum thread '{thread.name}' (ID: {thread.id}) to event '{event.name}' (ID: {event_id}) (channels will be created later) by {ctx.author}")

                await ctx.send(
                    f"✅ Successfully linked forum thread **'{thread.name}'** to event **'{event.name}'** (ID: {event_id})\n"
                    f"Thread: {thread.mention}\n"
                    f"Event start time: <t:{int(event.start_time.timestamp())}:F>\n\n"
                    f"Event channels will be created {await self.config.guild(ctx.guild).creation_minutes()} minutes before the event starts.\n"
                    f"The role button will be added automatically when channels are created."
                )

