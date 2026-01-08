import asyncio
import logging

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

                # Cancel any active task and retry tasks for this event
                self._cancel_event_tasks(int(event_id))

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
    async def on_thread_create(self, thread: discord.Thread):
        """Link forum threads to events when thread name matches event name."""
        # Only process forum threads
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        guild = thread.guild
        if not guild:
            return

        # Threads are often created before event channels, so we need to retry with exponential backoff
        # Retry intervals: 2s, 5s, 10s, 20s, 30s (total ~67s of retries)
        retry_delays = [2, 5, 10, 20, 30]

        for attempt, delay in enumerate(retry_delays, start=1):
            # Wait before checking (skip on first attempt if it's attempt 1)
            if attempt > 1:
                await asyncio.sleep(delay)
                log.debug(f"Retry attempt {attempt} for thread '{thread.name}' after {delay}s delay")

            # Get all active events
            stored = await self.config.guild(guild).event_channels()
            if not stored:
                # No events with channels yet, continue to next retry
                if attempt < len(retry_delays):
                    log.debug(f"No event channels found yet for thread '{thread.name}', will retry in {retry_delays[attempt]}s")
                    continue
                else:
                    log.debug(f"No event channels found for thread '{thread.name}' after all retries")
                    return

            # Get all scheduled events in the guild
            scheduled_events = guild.scheduled_events

            # Try to match thread name to an event
            for scheduled_event in scheduled_events:
                event_id_str = str(scheduled_event.id)

                # Check if this event has channels created
                if event_id_str not in stored:
                    continue

                # Match if thread name matches event name (case-insensitive exact match)
                if thread.name.lower() == scheduled_event.name.lower():
                    # Link the thread to the event
                    async with self._config_lock:
                        current_stored = await self.config.guild(guild).event_channels()
                        if event_id_str in current_stored:
                            current_stored[event_id_str]["forum_thread"] = thread.id
                            await self.config.guild(guild).event_channels.set(current_stored)
                            log.info(f"Linked forum thread '{thread.name}' (ID: {thread.id}) to event '{scheduled_event.name}' (ID: {scheduled_event.id}) on attempt {attempt}")
                    return  # Successfully linked, exit

            # No match found in this attempt
            if attempt < len(retry_delays):
                log.debug(f"No matching event found for thread '{thread.name}' on attempt {attempt}, will retry in {retry_delays[attempt]}s")
            else:
                log.debug(f"No matching event found for thread '{thread.name}' after {attempt} attempts")

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
            stored.pop(event_to_remove, None)
            await self.config.guild(guild).event_channels.set(stored)

            # Check if divider should be deleted (no more event roles)
            await self._cleanup_divider_if_empty(guild)
