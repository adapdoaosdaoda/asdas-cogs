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

            # Send deletion warning and lock channels (only if there was recent activity)
            deletion_warning_template = await self.config.guild(guild).deletion_warning_message()
            if deletion_warning_template:
                # Check if there was a message sent in the last 15 minutes
                try:
                    last_message = None
                    async for message in text_channel.history(limit=1):
                        last_message = message
                        break

                    # Only send warning if there was a message in the last 15 minutes
                    should_send_warning = False
                    if last_message:
                        time_since_last_message = datetime.now(timezone.utc) - last_message.created_at
                        if time_since_last_message <= timedelta(minutes=15):
                            should_send_warning = True
                            log.info(f"Last message in {text_channel.name} was {time_since_last_message.total_seconds():.0f}s ago - sending deletion warning")
                        else:
                            log.info(f"Last message in {text_channel.name} was {time_since_last_message.total_seconds():.0f}s ago - skipping deletion warning")
                    else:
                        log.info(f"No messages found in {text_channel.name} - skipping deletion warning")

                    if should_send_warning:
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
                except Exception as e:
                    log.error(f"Error checking message history for deletion warning in {text_channel.name}: {e}")

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
                                view_channel=True,  # Maintain view permission
                                send_messages=False,  # Locked
                                connect=True,  # Maintain connect permission
                                speak=False,  # Locked in voice
                            ),
                        }

                        # Add whitelisted roles to locked overwrites (keep view but lock send/speak)
                        whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
                        for whitelisted_role_id in whitelisted_role_ids:
                            whitelisted_role = guild.get_role(whitelisted_role_id)
                            if whitelisted_role:
                                locked_overwrites[whitelisted_role] = discord.PermissionOverwrite(
                                    view_channel=True,
                                    send_messages=False,  # Locked
                                    connect=True,
                                    speak=False,  # Locked in voice
                                )

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

            # Refetch stored data and delete channels (with lock to prevent race)
            async with self._config_lock:
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
