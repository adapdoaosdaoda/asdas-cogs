import asyncio
from datetime import datetime, timedelta, timezone
import logging

import discord

log = logging.getLogger("red.eventchannels")


class HandlersMixin:
    """Mixin class containing event handling methods for EventChannels cog."""

    async def _handle_event(self, guild: discord.Guild, event: discord.ScheduledEvent, retry_count: int = 0):
        try:
            start_time = event.start_time.astimezone(timezone.utc)
            creation_minutes = await self.config.guild(guild).creation_minutes()
            create_time = start_time - timedelta(minutes=creation_minutes)
            deletion_hours = await self.config.guild(guild).deletion_hours()
            delete_time = start_time + timedelta(hours=deletion_hours)
            now = datetime.now(timezone.utc)

            # If this is a retry, adjust the create_time based on retry intervals
            if retry_count > 0:
                retry_intervals = await self.config.guild(guild).minimum_retry_intervals()
                if retry_count <= len(retry_intervals):
                    # Use the retry interval for this attempt
                    retry_minutes = retry_intervals[retry_count - 1]
                    create_time = start_time - timedelta(minutes=retry_minutes)
                    log.info(f"Retry attempt {retry_count} for event '{event.name}': checking at T-{retry_minutes} minutes")

            # If event starts in less than configured minutes, create channels immediately
            if now >= create_time:
                # Already past the create time, do it now
                pass
            else:
                # Wait until configured minutes before start
                await asyncio.sleep((create_time - now).total_seconds())

            # Check if event already has channels (with lock to prevent race)
            async with self._config_lock:
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

            # Add whitelisted roles to overwrites
            whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
            for whitelisted_role_id in whitelisted_role_ids:
                whitelisted_role = guild.get_role(whitelisted_role_id)
                if whitelisted_role:
                    overwrites[whitelisted_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        connect=True,
                        speak=True,
                    )

            # Get channel format and prepare channel names
            channel_format = await self.config.guild(guild).channel_format()
            space_replacer = await self.config.guild(guild).space_replacer()
            channel_name_limit = await self.config.guild(guild).channel_name_limit()
            channel_name_limit_char = await self.config.guild(guild).channel_name_limit_char()
            base_name = event.name.lower().replace(" ", space_replacer)

            # Apply character limit to base name only (not the full channel name)
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

            # Now format with the limited base name
            text_channel_name = channel_format.format(name=base_name, type="text")

            # Check for voice multipliers and minimum role requirements
            voice_multipliers = await self.config.guild(guild).voice_multipliers()
            voice_minimum_roles = await self.config.guild(guild).voice_minimum_roles()

            # Find the first matching keyword in the event name (check both configs)
            matched_keyword = None
            voice_multiplier_capacity = None
            event_name_lower = event.name.lower()

            # First check voice_multipliers
            for keyword, multiplier in voice_multipliers.items():
                if keyword in event_name_lower:
                    matched_keyword = keyword
                    voice_multiplier_capacity = multiplier
                    break

            # If no multiplier matched, check voice_minimum_roles for a matching keyword
            if not matched_keyword:
                for keyword in voice_minimum_roles.keys():
                    if keyword in event_name_lower:
                        matched_keyword = keyword
                        break

            # Check if matched keyword has a minimum role requirement
            minimum_required = None
            if matched_keyword and role:
                minimum_required = voice_minimum_roles.get(matched_keyword)

                if minimum_required:
                    role_member_count, count_is_reliable = await self._get_role_member_count(guild, role, event.name)

                    # Log warning if count may be unreliable
                    if not count_is_reliable:
                        log.warning(
                            f"Event '{event.name}': Checking minimum role requirement with potentially incomplete count. "
                            f"Current count: {role_member_count}, Required: {minimum_required}. "
                            f"Enable GUILD_MEMBERS intent for accurate counting."
                        )

                    if role_member_count < minimum_required:
                        # Check if we should retry
                        retry_intervals = await self.config.guild(guild).minimum_retry_intervals()

                        if retry_count < len(retry_intervals):
                            # Schedule a retry attempt
                            next_retry = retry_count + 1
                            retry_minutes = retry_intervals[retry_count]
                            retry_time = start_time - timedelta(minutes=retry_minutes)
                            time_until_retry = (retry_time - datetime.now(timezone.utc)).total_seconds()

                            # Only schedule retry if we haven't passed the retry time yet
                            if time_until_retry > 0:
                                log.info(
                                    f"Event '{event.name}': minimum not met ({role_member_count}/{minimum_required} members). "
                                    f"Scheduling retry attempt {next_retry} at T-{retry_minutes} minutes "
                                    f"(in {int(time_until_retry/60)} minutes)"
                                )
                                # Schedule the retry task
                                retry_task = self.bot.loop.create_task(
                                    self._handle_event(guild, event, retry_count=next_retry)
                                )
                                # Store with a unique key to avoid overwriting the main task
                                self.active_tasks[f"{event.id}_retry_{next_retry}"] = retry_task
                                return
                            else:
                                log.info(
                                    f"Event '{event.name}': minimum not met ({role_member_count}/{minimum_required} members) "
                                    f"and retry time T-{retry_minutes}min already passed. No more retries."
                                )
                                return
                        else:
                            log.info(
                                f"Event '{event.name}': minimum not met ({role_member_count}/{minimum_required} members) "
                                f"and all retry attempts exhausted. Skipping channel creation."
                            )
                            return
                    else:
                        # Minimum is met, log success
                        if retry_count > 0:
                            log.info(
                                f"Event '{event.name}': minimum requirement met on retry attempt {retry_count} "
                                f"({role_member_count}/{minimum_required} members). Proceeding with channel creation."
                            )
                        else:
                            log.info(
                                f"Event '{event.name}': minimum requirement met "
                                f"({role_member_count}/{minimum_required} members). Proceeding with channel creation."
                            )

            # Calculate number of voice channels based on role member count
            if matched_keyword and voice_multiplier_capacity and role:
                role_member_count, count_is_reliable = await self._get_role_member_count(guild, role, event.name)

                # Log warning if count may be unreliable
                if not count_is_reliable:
                    log.warning(
                        f"Event '{event.name}': Calculating voice channels with potentially incomplete count. "
                        f"Current count: {role_member_count}. Enable GUILD_MEMBERS intent for accurate counting."
                    )

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

            # Store channel data (with lock to prevent race)
            async with self._config_lock:
                stored = await self.config.guild(guild).event_channels()

                # Check if there's a thread linked to this event
                thread_links = await self.config.guild(guild).thread_event_links()
                linked_thread_id = None
                for thread_id, event_id in thread_links.items():
                    if event_id == str(event.id):
                        linked_thread_id = int(thread_id)
                        log.info(f"Found pre-linked thread {thread_id} for event '{event.name}' (ID: {event.id})")
                        break

                # Create event channel entry
                stored[str(event.id)] = {
                    "text": text_channel.id,
                    "voice": [vc.id for vc in voice_channels],  # Store list of voice channel IDs
                    "role": role.id,
                }

                # Add thread link if it exists
                if linked_thread_id:
                    stored[str(event.id)]["forum_thread"] = linked_thread_id
                    log.info(f"Added forum_thread {linked_thread_id} to event channels for event '{event.name}'")

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

            # Send deletion warning and lock channels (always if there are user messages)
            deletion_warning_template = await self.config.guild(guild).deletion_warning_message()
            if deletion_warning_template:
                # Check if there are any user messages (for archiving and extension)
                try:
                    has_user_messages = await self._has_user_messages(text_channel)

                    if has_user_messages:
                        log.info(f"User messages found in {text_channel.name} - sending deletion warning with extend option")
                    else:
                        log.info(f"No user messages found in {text_channel.name} - skipping deletion warning")

                    if has_user_messages:
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
                                warning_message = await text_channel.send(deletion_warning_msg, allowed_mentions=discord.AllowedMentions(roles=True))
                                log.info(f"Sent deletion warning to {text_channel.name}")

                                # Add extend reaction (⏰ clock emoji)
                                try:
                                    await warning_message.add_reaction("⏰")
                                    log.info(f"Added extend reaction to deletion warning in {text_channel.name}")

                                    # Store deletion warning info for extend functionality
                                    async with self._config_lock:
                                        deletion_extensions = await self.config.guild(guild).deletion_extensions()
                                        deletion_extensions[str(event.id)] = {
                                            "delete_time": delete_time.timestamp(),
                                            "warning_message_id": warning_message.id,
                                            "text_channel_id": text_channel.id,
                                        }
                                        await self.config.guild(guild).deletion_extensions.set(deletion_extensions)
                                except discord.Forbidden:
                                    log.warning(f"Could not add reaction to deletion warning - missing permissions")
                            except discord.Forbidden:
                                log.warning(f"Could not send deletion warning to {text_channel.name} - missing permissions")
                except Exception as e:
                    log.error(f"Error checking message history for deletion warning in {text_channel.name}: {e}")

            # ---------- Cleanup ----------

            # Wait until deletion time, but check for extensions
            while True:
                # Check if deletion has been extended
                deletion_extensions = await self.config.guild(guild).deletion_extensions()
                extension_data = deletion_extensions.get(str(event.id))

                if extension_data:
                    # Use the extended deletion time
                    extended_delete_time = datetime.fromtimestamp(
                        extension_data["delete_time"],
                        tz=timezone.utc
                    )
                    time_until_deletion = (extended_delete_time - datetime.now(timezone.utc)).total_seconds()
                else:
                    # Use the original deletion time
                    time_until_deletion = (delete_time - datetime.now(timezone.utc)).total_seconds()

                if time_until_deletion <= 0:
                    # Time to delete
                    break

                # Sleep for the remaining time, but wake up periodically to check for extensions
                # Sleep for minimum of 60 seconds or remaining time
                sleep_time = min(60, time_until_deletion)
                await asyncio.sleep(sleep_time)

            # Refetch stored data and delete/archive channels (with lock to prevent race)
            async with self._config_lock:
                stored = await self.config.guild(guild).event_channels()
                data = stored.get(str(event.id))
                if not data:
                    return

                # Handle text channel - archive if it has user messages, otherwise delete
                text_channel = guild.get_channel(data.get("text"))
                text_channel_archived = False
                if text_channel:
                    # Check if channel has user messages
                    has_user_messages = await self._has_user_messages(text_channel)

                    if has_user_messages:
                        # Archive the channel instead of deleting
                        role = guild.get_role(data.get("role"))
                        archived = await self._archive_text_channel(guild, text_channel, role, event.name, str(event.id))
                        if archived:
                            text_channel_archived = True
                            log.info(f"Text channel archived for event '{event.name}'")
                        else:
                            # If archiving failed, delete the channel
                            try:
                                await text_channel.delete(reason="Scheduled event ended (archive failed)")
                            except discord.NotFound:
                                pass
                    else:
                        # No user messages, delete the channel
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

                # Remove from stored config before role deletion
                stored.pop(str(event.id), None)
                await self.config.guild(guild).event_channels.set(stored)

                # Also remove from thread_event_links
                thread_id = data.get("forum_thread")
                if thread_id:
                    thread_links = await self.config.guild(guild).thread_event_links()
                    thread_links.pop(str(thread_id), None)
                    await self.config.guild(guild).thread_event_links.set(thread_links)
                    log.info(f"Removed thread link for thread {thread_id} (event ended)")

                # Clean up deletion extensions tracking
                deletion_extensions = await self.config.guild(guild).deletion_extensions()
                if str(event.id) in deletion_extensions:
                    deletion_extensions.pop(str(event.id), None)
                    await self.config.guild(guild).deletion_extensions.set(deletion_extensions)

            # Remove role from divider and delete role (outside lock, uses own lock)
            if role:
                await self._update_divider_permissions(guild, role, add=False)
                try:
                    await role.delete(reason="Scheduled event ended")
                except discord.Forbidden:
                    pass

            # Check if divider should be deleted (no more event roles)
            await self._cleanup_divider_if_empty(guild)
        except asyncio.CancelledError:
            # Task was cancelled - clean up if channels were created (with lock)
            async with self._config_lock:
                stored = await self.config.guild(guild).event_channels()
                data = stored.get(str(event.id))
                if data:
                    # Handle text channel - archive if it has user messages, otherwise delete
                    text_channel = guild.get_channel(data.get("text"))
                    text_channel_archived = False
                    if text_channel:
                        # Check if channel has user messages
                        has_user_messages = await self._has_user_messages(text_channel)

                        if has_user_messages:
                            # Archive the channel instead of deleting
                            role = guild.get_role(data.get("role"))
                            archived = await self._archive_text_channel(guild, text_channel, role, event.name, str(event.id))
                            if archived:
                                text_channel_archived = True
                                log.info(f"Text channel archived for cancelled event '{event.name}'")
                            else:
                                # If archiving failed, delete the channel
                                try:
                                    await text_channel.delete(reason="Scheduled event cancelled (archive failed)")
                                except (discord.NotFound, discord.Forbidden):
                                    pass
                        else:
                            # No user messages, delete the channel
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

                    role = guild.get_role(data["role"])

                    # Remove from stored config
                    stored.pop(str(event.id), None)
                    await self.config.guild(guild).event_channels.set(stored)

                    # Also remove from thread_event_links
                    thread_id = data.get("forum_thread")
                    if thread_id:
                        thread_links = await self.config.guild(guild).thread_event_links()
                        thread_links.pop(str(thread_id), None)
                        await self.config.guild(guild).thread_event_links.set(thread_links)
                        log.info(f"Removed thread link for thread {thread_id} (event cancelled)")

                    # Clean up deletion extensions tracking
                    deletion_extensions = await self.config.guild(guild).deletion_extensions()
                    if str(event.id) in deletion_extensions:
                        deletion_extensions.pop(str(event.id), None)
                        await self.config.guild(guild).deletion_extensions.set(deletion_extensions)

            # Remove role from divider and clean up (outside lock, uses own locks)
            if data:
                role = guild.get_role(data["role"])
                if role:
                    await self._update_divider_permissions(guild, role, add=False)

                # Check if divider should be deleted (no more event roles)
                await self._cleanup_divider_if_empty(guild)
            raise
        finally:
            # Clean up task reference
            self.active_tasks.pop(event.id, None)

    def _cancel_event_tasks(self, event_id: int):
        """Cancel all tasks related to an event (main task + retry tasks)."""
        # Cancel main task
        task = self.active_tasks.get(event_id)
        if task and not task.done():
            task.cancel()
            self.active_tasks.pop(event_id, None)

        # Cancel all retry tasks
        retry_keys = [key for key in self.active_tasks.keys() if isinstance(key, str) and key.startswith(f"{event_id}_retry_")]
        for retry_key in retry_keys:
            retry_task = self.active_tasks.get(retry_key)
            if retry_task and not retry_task.done():
                retry_task.cancel()
            self.active_tasks.pop(retry_key, None)

    async def _force_create_event_channels(self, guild: discord.Guild, event: discord.ScheduledEvent, requested_by: str):
        """Force create event channels immediately, bypassing minimum role requirements.

        This method is called when an admin uses the force create button.

        Parameters
        ----------
        guild : discord.Guild
            The guild
        event : discord.ScheduledEvent
            The scheduled event
        requested_by : str
            Name of the user who requested the force create
        """
        try:
            start_time = event.start_time.astimezone(timezone.utc)

            # Check if event already has channels (with lock to prevent race)
            async with self._config_lock:
                stored = await self.config.guild(guild).event_channels()
                if str(event.id) in stored:
                    log.warning(f"Force create requested but channels already exist for event '{event.name}'")
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

            # Check for role
            role = discord.utils.get(guild.roles, name=expected_role_name)
            if not role:
                log.warning(f"Force create: No matching role found for event '{event.name}'. Expected role: '{expected_role_name}'")
                return

            log.info(f"Force create: Found matching role '{expected_role_name}' for event '{event.name}' (requested by {requested_by})")

            # Get channel format and prepare channel names
            channel_format = await self.config.guild(guild).channel_format()
            space_replacer = await self.config.guild(guild).space_replacer()
            channel_name_limit = await self.config.guild(guild).channel_name_limit()
            channel_name_limit_char = await self.config.guild(guild).channel_name_limit_char()
            base_name = event.name.lower().replace(" ", space_replacer)

            # Apply character limit to base name only
            if channel_name_limit_char:
                char_index = base_name.find(channel_name_limit_char)
                if char_index != -1:
                    base_name = base_name[:char_index]
                elif len(base_name) > channel_name_limit:
                    base_name = base_name[:channel_name_limit]
            elif len(base_name) > channel_name_limit:
                base_name = base_name[:channel_name_limit]

            text_channel_name = channel_format.format(name=base_name, type="text")

            # Check for voice multipliers (but NOT minimum role requirements - force create bypasses that)
            voice_multipliers = await self.config.guild(guild).voice_multipliers()
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
                role_member_count, count_is_reliable = await self._get_role_member_count(guild, role, event.name)
                voice_count = max(1, role_member_count // voice_multiplier_capacity)
                user_limit = voice_multiplier_capacity + 1
                log.info(f"Force create: Voice multiplier active for keyword '{matched_keyword}': {role_member_count} members / {voice_multiplier_capacity} = {voice_count} channel(s) with limit {user_limit}")
            else:
                voice_count = 1
                user_limit = 0  # 0 = unlimited

            # Set up permissions
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

            # Add whitelisted roles to overwrites
            whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
            for whitelisted_role_id in whitelisted_role_ids:
                whitelisted_role = guild.get_role(whitelisted_role_id)
                if whitelisted_role:
                    overwrites[whitelisted_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        connect=True,
                        speak=True,
                    )

            text_channel = None
            voice_channels = []

            # Ensure divider channel exists before creating event channels
            await self._ensure_divider_channel(guild, category)

            try:
                # Create text channel
                text_channel = await guild.create_text_channel(
                    name=text_channel_name,
                    category=category,
                    reason=f"Force created by {requested_by} for scheduled event '{event.name}'",
                )
                log.info(f"Force create: Created text channel: {text_channel.name}")

                # Create voice channel(s)
                for i in range(voice_count):
                    if voice_count > 1:
                        voice_channel_name = channel_format.format(name=base_name, type="voice")
                        voice_channel_name = f"{voice_channel_name} {i + 1}"
                    else:
                        voice_channel_name = channel_format.format(name=base_name, type="voice")

                    voice_channel = await guild.create_voice_channel(
                        name=voice_channel_name,
                        category=category,
                        user_limit=user_limit,
                        reason=f"Force created by {requested_by} for scheduled event '{event.name}'",
                    )
                    voice_channels.append(voice_channel)
                    log.info(f"Force create: Created voice channel: {voice_channel.name}")

                # Apply permission overwrites
                await text_channel.edit(overwrites=overwrites)
                for voice_channel in voice_channels:
                    await voice_channel.edit(overwrites=overwrites)
                log.info(f"Force create: Applied permissions to {len(voice_channels) + 1} channel(s) for event '{event.name}'")

                # Add role to divider permissions
                await self._update_divider_permissions(guild, role, add=True)

                # Send announcement message if configured
                announcement_template = await self.config.guild(guild).announcement_message()
                if announcement_template:
                    unix_timestamp = int(event.start_time.timestamp())
                    discord_timestamp = f"<t:{unix_timestamp}:R>"

                    try:
                        announcement = announcement_template.format(
                            role=role.mention,
                            event=event.name,
                            time=discord_timestamp
                        )
                    except KeyError as e:
                        log.error(f"Invalid placeholder {e} in announcement message template")
                        announcement = None

                    if announcement:
                        try:
                            await text_channel.send(
                                f"⚡ **Channels force created by {requested_by}**\n\n{announcement}",
                                allowed_mentions=discord.AllowedMentions(roles=True)
                            )
                            log.info(f"Force create: Sent announcement to {text_channel.name}")
                        except discord.Forbidden:
                            log.warning(f"Force create: Could not send announcement - missing permissions")

            except discord.Forbidden as e:
                log.error(f"Force create: Permission error while creating channels for event '{event.name}': {e}")
                # Clean up any created channels
                if text_channel:
                    try:
                        await text_channel.delete(reason="Force create failed")
                    except:
                        pass
                for voice_channel in voice_channels:
                    try:
                        await voice_channel.delete(reason="Force create failed")
                    except:
                        pass
                return
            except Exception as e:
                log.error(f"Force create: Failed to create channels for event '{event.name}': {e}")
                # Clean up
                if text_channel:
                    try:
                        await text_channel.delete(reason="Force create failed")
                    except:
                        pass
                for voice_channel in voice_channels:
                    try:
                        await voice_channel.delete(reason="Force create failed")
                    except:
                        pass
                return

            # Store channel data (with lock)
            async with self._config_lock:
                stored = await self.config.guild(guild).event_channels()

                # Check if there's a thread linked to this event
                thread_links = await self.config.guild(guild).thread_event_links()
                linked_thread_id = None
                for thread_id, event_id in thread_links.items():
                    if event_id == str(event.id):
                        linked_thread_id = int(thread_id)
                        log.info(f"Force create: Found pre-linked thread {thread_id} for event '{event.name}'")
                        break

                # Create event channel entry
                stored[str(event.id)] = {
                    "text": text_channel.id,
                    "voice": [vc.id for vc in voice_channels],
                    "role": role.id,
                }

                # Add thread link if it exists
                if linked_thread_id:
                    stored[str(event.id)]["forum_thread"] = linked_thread_id
                    log.info(f"Force create: Added forum_thread {linked_thread_id} to event channels")

                await self.config.guild(guild).event_channels.set(stored)

            log.info(f"✅ Force create successful for event '{event.name}' by {requested_by}")

            # Now schedule the normal cleanup task (event start message, deletion warning, cleanup)
            deletion_hours = await self.config.guild(guild).deletion_hours()
            delete_time = start_time + timedelta(hours=deletion_hours)
            now = datetime.now(timezone.utc)

            # Wait until event starts
            await asyncio.sleep(max(0, (start_time - now).total_seconds()))

            # Send event start message if configured
            event_start_template = await self.config.guild(guild).event_start_message()
            if event_start_template:
                try:
                    event_start_msg = event_start_template.format(
                        role=role.mention,
                        event=event.name
                    )
                    await text_channel.send(event_start_msg, allowed_mentions=discord.AllowedMentions(roles=True))
                    log.info(f"Force create: Sent event start message")
                except KeyError as e:
                    log.error(f"Invalid placeholder {e} in event start message template")
                except discord.Forbidden:
                    log.warning(f"Force create: Could not send event start message - missing permissions")

            # Calculate when to send deletion warning (15 minutes before deletion)
            warning_time = delete_time - timedelta(minutes=15)
            await asyncio.sleep(max(0, (warning_time - datetime.now(timezone.utc)).total_seconds()))

            # Send deletion warning and lock channels
            deletion_warning_template = await self.config.guild(guild).deletion_warning_message()
            if deletion_warning_template:
                try:
                    # Always send warning if there are user messages (for archiving and extension)
                    has_user_messages = await self._has_user_messages(text_channel)

                    if has_user_messages:
                        try:
                            deletion_warning_msg = deletion_warning_template.format(
                                role=role.mention,
                                event=event.name
                            )
                            warning_message = await text_channel.send(deletion_warning_msg, allowed_mentions=discord.AllowedMentions(roles=True))
                            log.info(f"Force create: Sent deletion warning")

                            # Add extend reaction
                            try:
                                await warning_message.add_reaction("⏰")
                                log.info(f"Force create: Added extend reaction to deletion warning")

                                # Store deletion warning info
                                async with self._config_lock:
                                    deletion_extensions = await self.config.guild(guild).deletion_extensions()
                                    deletion_extensions[str(event.id)] = {
                                        "delete_time": delete_time.timestamp(),
                                        "warning_message_id": warning_message.id,
                                        "text_channel_id": text_channel.id,
                                    }
                                    await self.config.guild(guild).deletion_extensions.set(deletion_extensions)
                            except discord.Forbidden:
                                log.warning(f"Force create: Could not add reaction to deletion warning - missing permissions")
                        except KeyError as e:
                            log.error(f"Invalid placeholder {e} in deletion warning message template")
                        except discord.Forbidden:
                            log.warning(f"Force create: Could not send deletion warning - missing permissions")
                except Exception as e:
                    log.error(f"Force create: Error checking message history: {e}")

            # Wait until deletion time, but check for extensions
            while True:
                # Check if deletion has been extended
                deletion_extensions = await self.config.guild(guild).deletion_extensions()
                extension_data = deletion_extensions.get(str(event.id))

                if extension_data:
                    # Use the extended deletion time
                    extended_delete_time = datetime.fromtimestamp(
                        extension_data["delete_time"],
                        tz=timezone.utc
                    )
                    time_until_deletion = (extended_delete_time - datetime.now(timezone.utc)).total_seconds()
                else:
                    # Use the original deletion time
                    time_until_deletion = (delete_time - datetime.now(timezone.utc)).total_seconds()

                if time_until_deletion <= 0:
                    # Time to delete
                    break

                # Sleep for the remaining time, but wake up periodically to check for extensions
                sleep_time = min(60, time_until_deletion)
                await asyncio.sleep(sleep_time)

            # Delete/archive channels and clean up (with lock)
            async with self._config_lock:
                stored = await self.config.guild(guild).event_channels()
                data = stored.get(str(event.id))
                if not data:
                    return

                # Handle text channel - archive if it has user messages, otherwise delete
                text_channel = guild.get_channel(data.get("text"))
                text_channel_archived = False
                if text_channel:
                    # Check if channel has user messages
                    has_user_messages = await self._has_user_messages(text_channel)

                    if has_user_messages:
                        # Archive the channel instead of deleting
                        role = guild.get_role(data.get("role"))
                        archived = await self._archive_text_channel(guild, text_channel, role, event.name, str(event.id))
                        if archived:
                            text_channel_archived = True
                            log.info(f"Force create: Text channel archived for event '{event.name}'")
                        else:
                            # If archiving failed, delete the channel
                            try:
                                await text_channel.delete(reason="Scheduled event ended (archive failed)")
                            except discord.NotFound:
                                pass
                    else:
                        # No user messages, delete the channel
                        try:
                            await text_channel.delete(reason="Scheduled event ended")
                        except discord.NotFound:
                            pass

                # Delete all voice channels
                voice_channel_ids = data.get("voice", [])
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

                # Remove from stored config before role deletion
                stored.pop(str(event.id), None)
                await self.config.guild(guild).event_channels.set(stored)

                # Also remove from thread_event_links
                thread_id = data.get("forum_thread")
                if thread_id:
                    thread_links = await self.config.guild(guild).thread_event_links()
                    thread_links.pop(str(thread_id), None)
                    await self.config.guild(guild).thread_event_links.set(thread_links)
                    log.info(f"Force create: Removed thread link (event ended)")

                # Clean up deletion extensions tracking
                deletion_extensions = await self.config.guild(guild).deletion_extensions()
                if str(event.id) in deletion_extensions:
                    deletion_extensions.pop(str(event.id), None)
                    await self.config.guild(guild).deletion_extensions.set(deletion_extensions)

            # Remove role from divider and delete role
            if role:
                await self._update_divider_permissions(guild, role, add=False)
                try:
                    await role.delete(reason="Scheduled event ended")
                except discord.Forbidden:
                    pass

            # Check if divider should be deleted
            await self._cleanup_divider_if_empty(guild)

            log.info(f"Force create: Cleanup complete for event '{event.name}'")

        except asyncio.CancelledError:
            log.info(f"Force create task cancelled for event '{event.name}'")
            raise
        except Exception as e:
            log.error(f"Force create: Unexpected error for event '{event.name}': {e}", exc_info=True)

    async def _has_user_messages(self, text_channel: discord.TextChannel) -> bool:
        """Check if a text channel has any messages from users (not bots).

        Parameters
        ----------
        text_channel : discord.TextChannel
            The text channel to check

        Returns
        -------
        bool
            True if there are user messages, False otherwise
        """
        try:
            async for message in text_channel.history(limit=100):
                if not message.author.bot:
                    return True
            return False
        except Exception as e:
            log.error(f"Error checking for user messages in {text_channel.name}: {e}")
            return False

    async def _archive_text_channel(self, guild: discord.Guild, text_channel: discord.TextChannel, role: discord.Role, event_name: str, event_id: str = None) -> bool:
        """Move a text channel to the archive category and make it read-only.

        Parameters
        ----------
        guild : discord.Guild
            The guild
        text_channel : discord.TextChannel
            The text channel to archive
        role : discord.Role
            The event role
        event_name : str
            The event name

        Returns
        -------
        bool
            True if archived successfully, False otherwise
        """
        try:
            archive_category_id = await self.config.guild(guild).archive_category_id()

            # If no archive category is configured, try to find or create one
            if not archive_category_id:
                # Look for a category named "Event Archives" or similar
                archive_category = discord.utils.get(guild.categories, name="Event Archives")

                # If not found, create it
                if not archive_category:
                    try:
                        archive_category = await guild.create_category(
                            name="Event Archives",
                            reason="Auto-created for archiving event channels with messages"
                        )
                        log.info(f"Created archive category 'Event Archives' in {guild.name}")
                    except discord.Forbidden:
                        log.warning(f"Could not create archive category - missing permissions. Channel will be deleted instead.")
                        return False

                # Store the archive category ID
                await self.config.guild(guild).archive_category_id.set(archive_category.id)
                archive_category_id = archive_category.id
            else:
                archive_category = guild.get_channel(archive_category_id)

                # If the configured archive category doesn't exist anymore, try to create it
                if not archive_category:
                    try:
                        archive_category = await guild.create_category(
                            name="Event Archives",
                            reason="Archive category was deleted, recreating"
                        )
                        await self.config.guild(guild).archive_category_id.set(archive_category.id)
                        log.info(f"Recreated archive category 'Event Archives' in {guild.name}")
                    except discord.Forbidden:
                        log.warning(f"Could not create archive category - missing permissions. Channel will be deleted instead.")
                        return False

            # Set up read-only permissions for archived channel
            archived_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                ),
            }

            # If role still exists, give it read-only access
            if role:
                archived_overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )

            # Add whitelisted roles with read-only access
            whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
            for whitelisted_role_id in whitelisted_role_ids:
                whitelisted_role = guild.get_role(whitelisted_role_id)
                if whitelisted_role:
                    archived_overwrites[whitelisted_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True,
                    )

            # Move channel to archive category and update permissions
            # Ensure archived name doesn't exceed Discord's 100-character limit
            max_base_length = 100 - len("archived-")  # 91 characters
            base_name = text_channel.name[:max_base_length] if len(text_channel.name) > max_base_length else text_channel.name
            archived_name = f"archived-{base_name}"

            await text_channel.edit(
                category=archive_category,
                overwrites=archived_overwrites,
                name=archived_name,
                reason=f"Archived event channel for '{event_name}' (had user messages)"
            )

            # Send archive notification
            try:
                await text_channel.send(
                    f"📦 This channel has been archived because it contains messages. "
                    f"It is now read-only."
                )
            except discord.Forbidden:
                pass

            # Store archived channel info for tracking
            from datetime import datetime, timezone
            archived_channels = await self.config.guild(guild).archived_channels()
            archived_channels[str(text_channel.id)] = {
                "event_name": event_name,
                "original_name": base_name,  # Original name before "archived-" prefix
                "archived_at": datetime.now(timezone.utc).timestamp(),
                "event_id": event_id if event_id else "unknown",
            }
            await self.config.guild(guild).archived_channels.set(archived_channels)

            log.info(f"Archived text channel {text_channel.name} for event '{event_name}' - had user messages")
            return True

        except discord.Forbidden:
            log.warning(f"Could not archive channel {text_channel.name} - missing permissions. Channel will be deleted instead.")
            return False
        except Exception as e:
            log.error(f"Failed to archive channel {text_channel.name}: {e}. Channel will be deleted instead.")
            return False
