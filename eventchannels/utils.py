import asyncio
import logging

import discord

log = logging.getLogger("red.eventchannels")


class UtilsMixin:
    """Mixin class containing utility methods for EventChannels cog."""

    async def _startup_scan(self):
        await self.bot.wait_until_ready()

        # Run migration for all guilds
        for guild in self.bot.guilds:
            await self._migrate_deletion_warning_message(guild)
            await self._schedule_existing_events(guild)

    async def _migrate_deletion_warning_message(self, guild: discord.Guild):
        """Migrate old deletion warning messages to new default with extension feature.

        This updates the deletion warning message if it's still using the old default value
        to include the new extension feature instructions.
        """
        try:
            OLD_DEFAULT = "⚠️ These channels will be deleted in 15 minutes."
            NEW_DEFAULT = "⚠️ These channels will be deleted in 15 minutes. React with ⏰ to extend deletion by 4 hours."

            current_message = await self.config.guild(guild).deletion_warning_message()

            # Only update if the message is exactly the old default
            if current_message == OLD_DEFAULT:
                await self.config.guild(guild).deletion_warning_message.set(NEW_DEFAULT)
                log.info(f"Migrated deletion warning message to new default for guild '{guild.name}'")
        except Exception as e:
            log.error(f"Error migrating deletion warning message for guild '{guild.name}': {e}")

    async def _schedule_existing_events(self, guild: discord.Guild):
        try:
            events = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            return

        for event in events:
            if event.start_time and event.status == discord.EventStatus.scheduled:
                task = self.bot.loop.create_task(self._handle_event(guild, event))
                self.active_tasks[event.id] = task

    async def _cleanup_divider_if_empty(self, guild: discord.Guild):
        """Delete the divider channel if no event channels remain."""
        async with self._divider_lock:
            # Check if there are any active event channels (use config lock for reading)
            async with self._config_lock:
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
        async with self._divider_lock:
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

                    # Add all existing tracked event roles
                    for existing_role_id in divider_roles:
                        existing_role = guild.get_role(existing_role_id)
                        if existing_role:
                            overwrites[existing_role] = discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=False,
                                add_reactions=False,
                            )

                    # Add whitelisted roles with view-only permissions
                    whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
                    for whitelisted_role_id in whitelisted_role_ids:
                        whitelisted_role = guild.get_role(whitelisted_role_id)
                        if whitelisted_role:
                            overwrites[whitelisted_role] = discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=False,
                                add_reactions=False,
                            )

                    # Add the new event role
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

                    # Add remaining tracked event roles (excluding the one being removed)
                    for existing_role_id in divider_roles:
                        if existing_role_id != role.id:
                            existing_role = guild.get_role(existing_role_id)
                            if existing_role:
                                overwrites[existing_role] = discord.PermissionOverwrite(
                                    view_channel=True,
                                    send_messages=False,
                                    add_reactions=False,
                                )

                    # Add whitelisted roles with view-only permissions
                    whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
                    for whitelisted_role_id in whitelisted_role_ids:
                        whitelisted_role = guild.get_role(whitelisted_role_id)
                        if whitelisted_role:
                            overwrites[whitelisted_role] = discord.PermissionOverwrite(
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
        async with self._divider_lock:
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

                # Add permissions for tracked event roles
                divider_roles = await self.config.guild(guild).divider_roles()
                for role_id in divider_roles:
                    role = guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            add_reactions=False,
                        )

                # Add whitelisted roles with view-only permissions
                whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
                for whitelisted_role_id in whitelisted_role_ids:
                    whitelisted_role = guild.get_role(whitelisted_role_id)
                    if whitelisted_role:
                        overwrites[whitelisted_role] = discord.PermissionOverwrite(
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

    async def _get_role_member_count(self, guild: discord.Guild, role: discord.Role, event_name: str = None) -> tuple[int, bool]:
        """
        Get the member count for a role with diagnostic logging.

        Returns:
            tuple[int, bool]: (member_count, is_reliable)
                - member_count: The number of members with the role
                - is_reliable: False if the count might be incomplete due to missing intents/cache
        """
        member_count = len(role.members)
        is_reliable = True

        # Check if guild is chunked (indicates GUILD_MEMBERS intent is working)
        if not guild.chunked:
            is_reliable = False
            log.warning(
                f"⚠️ Member count for role '{role.name}' may be INCOMPLETE! "
                f"Guild '{guild.name}' is not chunked, indicating missing GUILD_MEMBERS intent or incomplete cache. "
                f"Reported count: {member_count}, but actual count may be higher. "
                f"Enable GUILD_MEMBERS intent in the Discord Developer Portal to get accurate counts."
            )
            if event_name:
                log.warning(
                    f"Event '{event_name}': Role member count ({member_count}) may be unreliable. "
                    f"This could cause incorrect minimum role checks or voice channel calculations."
                )

        # Additional diagnostic: Check if member count is suspiciously low
        # If a role has very few cached members but the guild is large, it's likely incomplete
        if member_count > 0 and member_count < 5 and guild.member_count > 100:
            log.warning(
                f"⚠️ Role '{role.name}' shows only {member_count} member(s), "
                f"which seems low for a guild with {guild.member_count} total members. "
                f"This may indicate incomplete member cache. Verify GUILD_MEMBERS intent is enabled."
            )
            is_reliable = False

        # If whitelisted roles are configured, check if they're affecting the count
        whitelisted_role_ids = await self.config.guild(guild).whitelisted_roles()
        whitelisted_overlap = sum(1 for m in role.members if any(r.id in whitelisted_role_ids for r in m.roles))

        if whitelisted_overlap > 0:
            log.debug(
                f"Role '{role.name}' has {whitelisted_overlap} member(s) who also have whitelisted roles. "
                f"Note: Whitelisted roles do NOT affect setminimumroles calculations - only the event role members are counted."
            )

        log.info(
            f"Role '{role.name}' member count: {member_count} "
            f"(reliable: {is_reliable}, chunked: {guild.chunked}, "
            f"guild members: {guild.member_count})"
        )

        return member_count, is_reliable

    async def get_event_forum_thread(self, guild: discord.Guild, event_id: int) -> discord.Thread | None:
        """
        Get the forum thread linked to an event.

        This is a public method that other cogs can use to retrieve the forum thread
        associated with a specific event.

        Args:
            guild: The Discord guild
            event_id: The ID of the scheduled event

        Returns:
            The forum Thread object if linked, otherwise None
        """
        stored = await self.config.guild(guild).event_channels()
        event_data = stored.get(str(event_id))

        if not event_data:
            return None

        thread_id = event_data.get("forum_thread")
        if not thread_id:
            return None

        # Try to get the thread from cache first
        thread = guild.get_thread(thread_id)
        if thread:
            return thread

        # If not in cache, try to fetch it
        try:
            thread = await guild.fetch_channel(thread_id)
            if isinstance(thread, discord.Thread):
                return thread
        except (discord.NotFound, discord.Forbidden):
            log.warning(f"Could not fetch forum thread {thread_id} for event {event_id}")

        return None

    async def get_event_data_by_role(self, guild: discord.Guild, role: discord.Role) -> dict | None:
        """
        Get event data by role ID.

        This is a public method that other cogs can use to retrieve all event data
        (including forum thread, text channel, voice channels) for a given role.

        Args:
            guild: The Discord guild
            role: The role to look up

        Returns:
            Dictionary with keys: "event_id", "text", "voice", "role", "forum_thread" (if linked)
            Returns None if no event is found for the role.
        """
        stored = await self.config.guild(guild).event_channels()

        for event_id, data in stored.items():
            if data.get("role") == role.id:
                return {
                    "event_id": event_id,
                    "text": data.get("text"),
                    "voice": data.get("voice"),
                    "role": data.get("role"),
                    "forum_thread": data.get("forum_thread"),
                }

        return None

    def build_event_channel_overwrites(
        self,
        guild: discord.Guild,
        role: discord.Role,
        whitelisted_role_ids: list[int]
    ) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        """Build permission overwrites for event channels.

        Args:
            guild: The Discord guild
            role: The event role to grant permissions to
            whitelisted_role_ids: List of whitelisted role IDs to also grant permissions

        Returns:
            Dictionary of permission overwrites for the channel
        """
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
        for whitelisted_role_id in whitelisted_role_ids:
            whitelisted_role = guild.get_role(whitelisted_role_id)
            if whitelisted_role:
                overwrites[whitelisted_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                )

        return overwrites

    def generate_channel_name(
        self,
        event_name: str,
        channel_format: str,
        space_replacer: str,
        channel_type: str,
        index: int | None = None,
        char_limit: int = 100,
        limit_char: str = ""
    ) -> str:
        """Generate channel name with optional index suffix.

        Args:
            event_name: The event name to base the channel name on
            channel_format: Format string for channel name (e.g., "{name}᲼{type}")
            space_replacer: Character to replace spaces with
            channel_type: Type of channel ("text" or "voice")
            index: Optional index for multiple voice channels
            char_limit: Character limit for the base name (default 100)
            limit_char: Character to limit name at (truncate before first occurrence)

        Returns:
            Formatted channel name
        """
        base_name = event_name.lower().replace(" ", space_replacer)

        # Apply character limit to base name only
        if limit_char:
            # Character-based limiting: truncate before first occurrence (exclusive)
            char_index = base_name.find(limit_char)
            if char_index != -1:
                base_name = base_name[:char_index]
            elif len(base_name) > char_limit:
                base_name = base_name[:char_limit]
        elif len(base_name) > char_limit:
            # Numeric limiting
            base_name = base_name[:char_limit]

        # Format with the limited base name
        channel_name = channel_format.format(name=base_name, type=channel_type)

        # Add index suffix for voice channels
        if index is not None:
            channel_name += f"-{index}"

        return channel_name

    async def wait_for_role(
        self,
        guild: discord.Guild,
        expected_role_name: str,
        event_start_time,
        timeout: int = 60
    ) -> discord.Role | None:
        """Wait for role to appear with exponential backoff.

        Args:
            guild: The Discord guild
            expected_role_name: Name of the role to wait for
            event_start_time: Event start time (for extended waiting if event is imminent)
            timeout: Initial timeout in seconds (default 60)

        Returns:
            The role if found, otherwise None
        """
        from datetime import datetime, timedelta, timezone

        role = discord.utils.get(guild.roles, name=expected_role_name)
        if role:
            return role

        # Try with exponential backoff: 5s, 10s, 20s, 40s... up to timeout
        delay = 5
        total_waited = 0
        while not role and total_waited < timeout:
            await asyncio.sleep(delay)
            total_waited += delay
            role = discord.utils.get(guild.roles, name=expected_role_name)
            if not role:
                delay *= 2  # Double the delay each time

        # If still no role and event is starting soon/now, wait up to 1 minute after start time
        if not role:
            now = datetime.now(timezone.utc)
            time_until_start = (event_start_time - now).total_seconds()

            # If event starts within 15 seconds or already started (up to 1 min ago)
            if -60 <= time_until_start <= 15:
                log.info(f"Event starting imminently. Waiting up to 1 minute after start for role '{expected_role_name}'...")

                # Wait until 1 minute after event start using exponential backoff
                one_min_after_start = event_start_time + timedelta(minutes=1)
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

        return role
