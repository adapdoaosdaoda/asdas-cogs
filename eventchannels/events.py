import asyncio
import logging
from datetime import datetime, timezone

import discord
from redbot.core import commands

log = logging.getLogger("red.eventchannels")


class EventsMixin:
    """Mixin class containing event listeners for EventChannels cog."""

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        if event.guild and event.status == discord.EventStatus.scheduled:
            task = self.bot.loop.create_task(self._handle_event(event.guild, event))
            self.active_tasks[event.id] = task

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        """Cancel task and clean up channels when event is deleted."""
        self._cancel_event_tasks(event.id)

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        """Cancel task and clean up if event is cancelled or start time changes significantly."""
        if after.status == discord.EventStatus.cancelled:
            self._cancel_event_tasks(after.id)
        elif before.start_time != after.start_time and after.status == discord.EventStatus.scheduled:
            # Start time changed - cancel old task and all retry tasks, create new one
            self._cancel_event_tasks(after.id)
            # Give a moment for cancellation to complete
            await asyncio.sleep(0.1)
            new_task = self.bot.loop.create_task(self._handle_event(after.guild, after))
            self.active_tasks[after.id] = new_task

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Handle event role deletion - recreate if channels exist, or clean up properly."""
        guild = role.guild
        stored = await self.config.guild(guild).event_channels()

        # Find events associated with this role
        events_to_handle = []
        for event_id, data in stored.items():
            if data.get("role") == role.id:
                events_to_handle.append((event_id, data))
                log.info(f"Event role '{role.name}' was deleted externally for event {event_id}")

        for event_id, data in events_to_handle:
            # Check if channels still exist
            text_channel_id = data.get("text")
            text_channel = guild.get_channel(text_channel_id) if text_channel_id else None

            voice_channel_ids = data.get("voice", [])
            if isinstance(voice_channel_ids, int):
                voice_channel_ids = [voice_channel_ids]
            voice_channels_exist = any(guild.get_channel(vc_id) for vc_id in voice_channel_ids)

            # Check if there's an active task (meaning cleanup is scheduled)
            has_active_task = int(event_id) in self.active_tasks

            # Decide whether to recreate or cleanup
            should_cleanup = False

            if (text_channel or voice_channels_exist) and has_active_task:
                # Channels still exist and task is running - RECREATE the role
                log.info(f"Recreating role '{role.name}' for event {event_id} - channels still exist and cleanup is scheduled")
                try:
                    # Recreate the role with the same name
                    new_role = await guild.create_role(
                        name=role.name,
                        reason=f"Role was deleted early but event channels still exist - recreating for proper archival"
                    )
                    log.info(f"Recreated role '{new_role.name}' (new ID: {new_role.id}) for event {event_id}")

                    # Update stored config with new role ID
                    stored[event_id]["role"] = new_role.id
                    await self.config.guild(guild).event_channels.set(stored)

                    # Add permissions to existing channels
                    if text_channel:
                        try:
                            await text_channel.set_permissions(
                                new_role,
                                view_channel=True,
                                send_messages=True,
                                reason="Reapplying permissions after role recreation"
                            )
                            log.info(f"Applied permissions for recreated role to {text_channel.name}")
                        except discord.Forbidden:
                            log.warning(f"Could not apply permissions to {text_channel.name}")

                    for vc_id in voice_channel_ids:
                        voice_channel = guild.get_channel(vc_id)
                        if voice_channel:
                            try:
                                await voice_channel.set_permissions(
                                    new_role,
                                    view_channel=True,
                                    connect=True,
                                    speak=True,
                                    reason="Reapplying permissions after role recreation"
                                )
                                log.info(f"Applied permissions for recreated role to {voice_channel.name}")
                            except discord.Forbidden:
                                log.warning(f"Could not apply permissions to {voice_channel.name}")

                    # Update divider permissions
                    await self._update_divider_permissions(guild, new_role, add=True)

                    # Role recreated successfully, continue to next event
                    continue

                except discord.Forbidden:
                    log.error(f"Could not recreate role '{role.name}' - missing permissions. Channels will be cleaned up without role.")
                    # Fall through to cleanup
                    should_cleanup = True
            else:
                # No active task or no channels - need to clean up
                should_cleanup = True

            # Clean up if needed
            if should_cleanup:
                log.info(f"Cleaning up channels for event {event_id} (active_task={has_active_task}, channels_exist={text_channel or voice_channels_exist})")

                # Handle text channel - archive if it has user messages
                if text_channel:
                    has_user_messages = await self._has_user_messages(text_channel)

                    if has_user_messages:
                        # Try to get event name from stored data or use a placeholder
                        # Since we don't have the full event object, extract from role name if possible
                        event_name = f"event-{event_id}"

                        # Archive the channel (role is None since it was deleted)
                        archived = await self._archive_text_channel(guild, text_channel, None, event_name, event_id)
                        if archived:
                            log.info(f"Archived text channel for event {event_id} after role deletion")
                        else:
                            # If archiving failed, delete the channel
                            try:
                                await text_channel.delete(reason=f"Event role '{role.name}' was deleted (archive failed)")
                            except (discord.NotFound, discord.Forbidden) as e:
                                log.warning(f"Could not delete channel {text_channel_id}: {e}")
                    else:
                        # No user messages, delete the channel
                        try:
                            await text_channel.delete(reason=f"Event role '{role.name}' was deleted")
                            log.info(f"Deleted channel {text_channel.name} - associated role was deleted")
                        except (discord.NotFound, discord.Forbidden) as e:
                            log.warning(f"Could not delete channel {text_channel_id}: {e}")

                # Delete all voice channels
                for vc_id in voice_channel_ids:
                    voice_channel = guild.get_channel(vc_id)
                    if voice_channel:
                        try:
                            await voice_channel.delete(reason=f"Event role '{role.name}' was deleted")
                            log.info(f"Deleted voice channel {voice_channel.name} - associated role was deleted")
                        except (discord.NotFound, discord.Forbidden) as e:
                            log.warning(f"Could not delete channel {vc_id}: {e}")

                # Cancel any active task and retry tasks for this event
                self._cancel_event_tasks(int(event_id))

                # Mark for removal from config
                stored.pop(event_id, None)

                # Remove from thread_event_links
                if data.get("forum_thread"):
                    thread_links = await self.config.guild(guild).thread_event_links()
                    thread_links.pop(str(data["forum_thread"]), None)
                    await self.config.guild(guild).thread_event_links.set(thread_links)
                    log.info(f"Removed thread link for event {event_id} (role deleted)")

                # Clean up deletion extensions tracking
                deletion_extensions = await self.config.guild(guild).deletion_extensions()
                if event_id in deletion_extensions:
                    deletion_extensions.pop(event_id, None)
                    await self.config.guild(guild).deletion_extensions.set(deletion_extensions)

        # Save updated storage (in case roles were recreated with new IDs)
        await self.config.guild(guild).event_channels.set(stored)

        # Remove original role from divider permissions tracking (only for the deleted role)
        divider_roles = await self.config.guild(guild).divider_roles()
        if role.id in divider_roles:
            divider_roles.remove(role.id)
            await self.config.guild(guild).divider_roles.set(divider_roles)
            log.info(f"Removed deleted role '{role.name}' from divider permissions tracking")

        # Check if divider should be deleted (no more event roles)
        await self._cleanup_divider_if_empty(guild)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """Link forum threads to events when thread name matches event name."""
        # Only process forum threads
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        guild = thread.guild
        if not guild:
            return

        log.info(f"Forum thread created: '{thread.name}' (ID: {thread.id}) - attempting to link to event")

        # Retry with delays in case scheduled_events cache isn't populated yet
        # Retry intervals: 0s, 2s, 5s (total ~7s of retries)
        retry_delays = [0, 2, 5]

        for attempt, delay in enumerate(retry_delays, start=1):
            # Wait before checking (skip on first attempt)
            if attempt > 1:
                await asyncio.sleep(delay)
                log.info(f"Retry attempt {attempt} for thread '{thread.name}' after {delay}s delay")

            # Get all scheduled events in the guild
            scheduled_events = guild.scheduled_events
            log.info(f"Checking {len(scheduled_events)} scheduled events for thread '{thread.name}' (attempt {attempt})")

            # Try to match thread name to an event (case-insensitive exact match)
            for scheduled_event in scheduled_events:
                if thread.name.lower() == scheduled_event.name.lower():
                    event_id_str = str(scheduled_event.id)

                    # Store the link in thread_event_links (regardless of whether channels exist)
                    async with self._config_lock:
                        thread_links = await self.config.guild(guild).thread_event_links()
                        thread_links[str(thread.id)] = event_id_str
                        await self.config.guild(guild).thread_event_links.set(thread_links)
                        log.info(f"✅ Linked forum thread '{thread.name}' (ID: {thread.id}) to event '{scheduled_event.name}' (ID: {scheduled_event.id}) on attempt {attempt}")

                        # If event channels already exist, also add to event_channels
                        event_channels = await self.config.guild(guild).event_channels()
                        if event_id_str in event_channels:
                            event_channels[event_id_str]["forum_thread"] = thread.id
                            await self.config.guild(guild).event_channels.set(event_channels)
                            log.info(f"✅ Also added thread link to existing event channels for event {scheduled_event.name}")

                            # Trigger role button addition since channels already exist
                            # (normally this happens in on_guild_channel_create, but that already fired)
                            forumthreadmessage_cog = self.bot.get_cog("ForumThreadMessage")
                            if forumthreadmessage_cog:
                                log.info(f"Triggering role button addition for thread {thread.name} since event channels already exist")
                                asyncio.create_task(forumthreadmessage_cog.add_role_button_to_thread(guild, thread))
                            else:
                                log.warning("ForumThreadMessage cog not loaded, cannot add role button")

                    return  # Successfully linked, exit

            # No match found in this attempt
            event_names = ', '.join(repr(e.name) for e in scheduled_events) if scheduled_events else 'none'
            if attempt < len(retry_delays):
                log.info(f"No matching event found for thread '{thread.name}' on attempt {attempt}. Available events: {event_names}. Will retry in {retry_delays[attempt]}s")
            else:
                log.warning(f"⚠️ No matching event found for thread '{thread.name}' after {attempt} attempts. Available events: {event_names}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reactions on deletion warning messages to extend deletion time."""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        # Check if this is the extend emoji (⏰)
        if str(payload.emoji) != "⏰":
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Check if this reaction is on a deletion warning message
        async with self._config_lock:
            deletion_extensions = await self.config.guild(guild).deletion_extensions()

            # Find which event this message belongs to
            event_id_str = None
            for event_id, data in deletion_extensions.items():
                if data.get("warning_message_id") == payload.message_id:
                    event_id_str = event_id
                    break

            if not event_id_str:
                return  # Not a deletion warning message

            # Get the current deletion time
            current_delete_time = datetime.fromtimestamp(
                deletion_extensions[event_id_str]["delete_time"],
                tz=timezone.utc
            )

            # Extend by 4 hours
            from datetime import timedelta
            new_delete_time = current_delete_time + timedelta(hours=4)

            # Update the stored deletion time
            deletion_extensions[event_id_str]["delete_time"] = new_delete_time.timestamp()
            await self.config.guild(guild).deletion_extensions.set(deletion_extensions)

            log.info(f"Extended deletion time for event {event_id_str} by 4 hours to {new_delete_time}")

        # Get the channel and update the warning message
        text_channel_id = deletion_extensions[event_id_str].get("text_channel_id")
        if text_channel_id:
            text_channel = guild.get_channel(text_channel_id)
            if text_channel:
                try:
                    warning_message = await text_channel.fetch_message(payload.message_id)
                    # Get the user who reacted
                    user = guild.get_member(payload.user_id)
                    user_mention = user.mention if user else "Someone"

                    # Update the message to show the extension
                    time_until_deletion = new_delete_time - datetime.now(timezone.utc)
                    hours = int(time_until_deletion.total_seconds() // 3600)
                    minutes = int((time_until_deletion.total_seconds() % 3600) // 60)

                    extension_msg = f"\n\n⏰ **Extended by {user_mention}**: Deletion postponed by 4 hours. Channels will now be deleted in approximately {hours}h {minutes}m."

                    # Check if message already has an extension notification
                    if "⏰ **Extended by" in warning_message.content:
                        # Find the last extension and replace it
                        lines = warning_message.content.split("\n\n")
                        # Keep only the first line (original warning)
                        original_warning = lines[0]
                        await warning_message.edit(content=f"{original_warning}{extension_msg}")
                    else:
                        await warning_message.edit(content=f"{warning_message.content}{extension_msg}")

                    log.info(f"Updated deletion warning message with extension notification")
                except discord.NotFound:
                    log.warning(f"Could not find deletion warning message {payload.message_id}")
                except discord.Forbidden:
                    log.warning(f"Could not edit deletion warning message - missing permissions")
                except Exception as e:
                    log.error(f"Error updating deletion warning message: {e}")

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

                    # Cancel any active task and retry tasks
                    self._cancel_event_tasks(int(event_id))

                break

        # Remove event from storage
        if event_to_remove:
            # Get thread_id before removing from storage
            event_data = stored.get(event_to_remove)
            thread_id = event_data.get("forum_thread") if event_data else None

            stored.pop(event_to_remove, None)
            await self.config.guild(guild).event_channels.set(stored)

            # Also remove from thread_event_links
            if thread_id:
                thread_links = await self.config.guild(guild).thread_event_links()
                thread_links.pop(str(thread_id), None)
                await self.config.guild(guild).thread_event_links.set(thread_links)
                log.info(f"Removed thread link for thread {thread_id} (channels deleted)")

            # Check if divider should be deleted (no more event roles)
            await self._cleanup_divider_if_empty(guild)
