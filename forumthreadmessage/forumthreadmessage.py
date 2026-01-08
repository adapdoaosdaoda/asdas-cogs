"""ForumThreadMessage - Automatically send, edit twice, and optionally delete messages in new forum threads."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from redbot.core import commands, Config

log = logging.getLogger("red.asdas-cogs.forumthreadmessage")


class RoleButtonView(discord.ui.View):
    """View with a button to add the event role."""

    def __init__(self, role: discord.Role, emoji: str = "🎫", label: str = "Join Event Role"):
        super().__init__(timeout=None)  # Persistent view
        self.role = role
        # Add the button with role ID in custom_id
        self.add_item(RoleButton(role, emoji, label))


class RoleButton(discord.ui.Button):
    """Button to add an event role to the user."""

    def __init__(self, role: discord.Role, emoji: str = "🎫", label: str = "Join Event Role"):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"add_event_role:{role.id}"
        )
        self.role_id = role.id

    async def callback(self, interaction: discord.Interaction):
        """Add the event role to the user who clicked the button."""
        try:
            member = interaction.user
            if not isinstance(member, discord.Member):
                await interaction.response.send_message(
                    "This button can only be used in a server.",
                    ephemeral=True
                )
                return

            # Get the role from the guild
            role = interaction.guild.get_role(self.role_id)
            if not role:
                await interaction.response.send_message(
                    "This role no longer exists.",
                    ephemeral=True
                )
                log.warning(f"Role {self.role_id} not found in guild {interaction.guild.id}")
                return

            # Check if user already has the role
            if role in member.roles:
                await interaction.response.send_message(
                    f"You already have the {role.mention} role!",
                    ephemeral=True
                )
                return

            # Add the role
            await member.add_roles(role, reason="User requested event role via button")
            await interaction.response.send_message(
                f"Successfully added the {role.mention} role to you!",
                ephemeral=True
            )
            log.info(f"Added role {role.name} to {member.name} ({member.id}) via button")

        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to add this role to you.",
                ephemeral=True
            )
            log.error(f"Failed to add role {self.role_id} - missing permissions")
        except Exception as e:
            await interaction.response.send_message(
                "An error occurred while adding the role.",
                ephemeral=True
            )
            log.error(f"Error adding role {self.role_id}: {e}", exc_info=True)


class ForumThreadMessage(commands.Cog):
    """Automatically send messages in newly created forum threads.

    Messages are sent when a new thread is created in a configured forum channel.
    After 2 seconds, the message is edited to different content (first edit).
    After another 2 seconds, the message is edited again (second edit).
    After another 2 seconds, the message can optionally be deleted.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=817263542,  # Unique identifier for this cog
            force_registration=True,
        )

        # Register guild-level configuration
        self.config.register_guild(
            forum_channel_id=None,  # ID of the forum channel to monitor
            initial_message="Welcome to this thread!",  # Initial message content
            edited_message="Thread created successfully!",  # Message content after first edit
            third_edited_message="Thread is ready!",  # Message content after second edit
            delete_enabled=False,  # Whether to delete the message after editing
            thread_messages={},  # Store {thread_id: {"message_id": id, "thread_name": name}}
            role_button_enabled=True,  # Whether to automatically add role buttons
            role_button_emoji="🎫",  # Emoji for the role button
            role_button_text="Join Event Role",  # Text for the role button
            # Conditional message updates based on event timing
            # Note: Role minimum thresholds come from EventChannels' voice_minimum_roles config
            event_15min_before_enabled=False,  # Enable 15-min-before updates
            # Global messages (all events)
            event_15min_role_min_met="✅ Event starting in 15 minutes! We have {role_count} members with the event role!",
            event_15min_role_min_not_met="⚠️ Event starting in 15 minutes but we only have {role_count}/{role_minimum} members!",
            event_15min_default="⏰ Event starting in 15 minutes!",
            # Keyword-specific messages (events matching title_keywords)
            event_15min_keyword_role_min_met="",  # Empty = use global message
            event_15min_keyword_role_min_not_met="",  # Empty = use global message
            event_15min_keyword_default="",  # Empty = use global message
            event_15min_title_keywords=[],  # Keywords that trigger keyword-specific messages
            event_start_enabled=False,  # Enable at-start updates
            # Global messages (all events)
            event_start_role_min_met="🎉 Event is starting NOW! {role_count} members ready!",
            event_start_role_min_not_met="⚠️ Event is starting but we're short on members ({role_count}/{role_minimum})!",
            event_start_default="🚀 Event is starting NOW!",
            # Keyword-specific messages (events matching title_keywords)
            event_start_keyword_role_min_met="",  # Empty = use global message
            event_start_keyword_role_min_not_met="",  # Empty = use global message
            event_start_keyword_default="",  # Empty = use global message
            event_start_title_keywords=[],  # Keywords that trigger keyword-specific messages
        )

        # Background task for monitoring events
        self.event_monitor_task = None

    async def cog_load(self):
        """Start background task when cog loads."""
        self.event_monitor_task = asyncio.create_task(self._event_monitor_loop())
        log.info("Started event monitor background task")

    async def cog_unload(self):
        """Clean up background task when cog unloads."""
        if self.event_monitor_task:
            self.event_monitor_task.cancel()
            try:
                await self.event_monitor_task
            except asyncio.CancelledError:
                pass
            log.info("Stopped event monitor background task")

    async def _evaluate_conditional_message(
        self,
        guild: discord.Guild,
        event: discord.ScheduledEvent,
        role: discord.Role,
        timing: str  # "15min" or "start"
    ) -> Optional[str]:
        """Evaluate conditions and return the appropriate message for this event.

        Parameters
        ----------
        guild : discord.Guild
            The guild
        event : discord.ScheduledEvent
            The scheduled event
        role : discord.Role
            The event role
        timing : str
            Either "15min" or "start"

        Returns
        -------
        Optional[str]
            The message to use, or None if updates are disabled
        """
        config = self.config.guild(guild)

        # Check if this timing is enabled
        if timing == "15min":
            if not await config.event_15min_before_enabled():
                return None
            title_keywords = await config.event_15min_title_keywords()
            # Global messages (all events)
            msg_global_role_min_met = await config.event_15min_role_min_met()
            msg_global_role_min_not_met = await config.event_15min_role_min_not_met()
            msg_global_default = await config.event_15min_default()
            # Keyword-specific messages (matching events)
            msg_keyword_role_min_met = await config.event_15min_keyword_role_min_met()
            msg_keyword_role_min_not_met = await config.event_15min_keyword_role_min_not_met()
            msg_keyword_default = await config.event_15min_keyword_default()
        else:  # "start"
            if not await config.event_start_enabled():
                return None
            title_keywords = await config.event_start_title_keywords()
            # Global messages (all events)
            msg_global_role_min_met = await config.event_start_role_min_met()
            msg_global_role_min_not_met = await config.event_start_role_min_not_met()
            msg_global_default = await config.event_start_default()
            # Keyword-specific messages (matching events)
            msg_keyword_role_min_met = await config.event_start_keyword_role_min_met()
            msg_keyword_role_min_not_met = await config.event_start_keyword_role_min_not_met()
            msg_keyword_default = await config.event_start_keyword_default()

        # Get minimum role requirement from EventChannels
        role_minimum = 0
        matched_keyword = None
        eventchannels_cog = self.bot.get_cog("EventChannels")
        if eventchannels_cog:
            eventchannels_config = eventchannels_cog.config.guild(guild)
            voice_minimum_roles = await eventchannels_config.voice_minimum_roles()

            # Find the first matching keyword in the event name (same logic as EventChannels)
            event_name_lower = event.name.lower()
            for keyword, minimum in voice_minimum_roles.items():
                if keyword in event_name_lower:
                    matched_keyword = keyword
                    role_minimum = minimum
                    log.debug(f"Event '{event.name}' matched EventChannels keyword '{keyword}' with minimum {minimum}")
                    break

        # Check if event title matches keyword filter
        matches_keyword_filter = False
        if title_keywords:
            event_title_lower = event.name.lower()
            matches_keyword_filter = any(keyword.lower() in event_title_lower for keyword in title_keywords)
            if matches_keyword_filter:
                log.debug(f"Event '{event.name}' matches keyword filter {title_keywords}")

        # Get role member count
        role_count = len(role.members)

        # Choose message based on keyword match and role count
        message_template = None

        # If event matches keyword filter AND keyword-specific messages are configured, use those
        if matches_keyword_filter:
            if role_minimum > 0 and role_count >= role_minimum:
                message_template = msg_keyword_role_min_met or msg_global_role_min_met
            elif role_minimum > 0 and role_count < role_minimum:
                message_template = msg_keyword_role_min_not_met or msg_global_role_min_not_met
            else:
                message_template = msg_keyword_default or msg_global_default
        else:
            # Use global messages for all events (including non-matching when keywords are set)
            if role_minimum > 0 and role_count >= role_minimum:
                message_template = msg_global_role_min_met
            elif role_minimum > 0 and role_count < role_minimum:
                message_template = msg_global_role_min_not_met
            else:
                message_template = msg_global_default

        # Final fallback to global default
        if not message_template:
            message_template = msg_global_default

        # Format the message with placeholders
        try:
            message = message_template.format(
                role_count=role_count,
                role_minimum=role_minimum,
                event_name=event.name,
                role_mention=role.mention
            )
            return message
        except KeyError as e:
            log.error(f"Invalid placeholder {e} in message template. Valid: {{role_count}}, {{role_minimum}}, {{event_name}}, {{role_mention}}")
            return msg_default

    async def _update_event_thread_message(
        self,
        guild: discord.Guild,
        event: discord.ScheduledEvent,
        role: discord.Role,
        timing: str
    ):
        """Update the thread message for an event at a specific timing.

        Parameters
        ----------
        guild : discord.Guild
            The guild
        event : discord.ScheduledEvent
            The scheduled event
        role : discord.Role
            The event role
        timing : str
            Either "15min" or "start"
        """
        # Get the message to use
        message_content = await self._evaluate_conditional_message(guild, event, role, timing)
        if not message_content:
            return

        # Get EventChannels cog to find the linked thread
        eventchannels_cog = self.bot.get_cog("EventChannels")
        if not eventchannels_cog:
            log.debug("EventChannels cog not loaded, cannot update event messages")
            return

        # Get event channels data
        eventchannels_config = eventchannels_cog.config.guild(guild)
        event_channels = await eventchannels_config.event_channels()
        event_data = event_channels.get(str(event.id))

        if not event_data:
            log.debug(f"No event channels found for event {event.name} ({event.id})")
            return

        thread_id = event_data.get("forum_thread")
        if not thread_id:
            log.debug(f"No forum thread linked to event {event.name} ({event.id})")
            return

        # Get the thread
        thread = await eventchannels_cog.get_event_forum_thread(guild, event.id)
        if not thread:
            log.warning(f"Could not retrieve forum thread {thread_id} for event {event.name}")
            return

        # Get the stored message
        thread_messages = await self.config.guild(guild).thread_messages()
        thread_data = thread_messages.get(str(thread_id))

        if not thread_data:
            log.debug(f"No stored message found for thread {thread_id}")
            return

        message_id = thread_data.get("message_id")

        # Fetch and update the message
        try:
            message = await thread.fetch_message(message_id)
            await message.edit(
                content=message_content,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )
            timing_label = "15 minutes before start" if timing == "15min" else "at start"
            log.info(f"✅ Updated thread message for event '{event.name}' ({timing_label})")
        except discord.NotFound:
            log.warning(f"Message {message_id} not found in thread {thread_id}")
        except discord.Forbidden:
            log.error(f"No permission to edit message in thread {thread_id}")
        except Exception as e:
            log.error(f"Error updating message in thread {thread_id}: {e}", exc_info=True)

    async def _event_monitor_loop(self):
        """Background task that monitors events and updates messages at appropriate times."""
        await self.bot.wait_until_ready()
        log.info("Event monitor loop started")

        # Track which events we've already updated (to avoid duplicate updates)
        updated_15min = set()  # event_id
        updated_start = set()  # event_id

        while True:
            try:
                # Check every 30 seconds
                await asyncio.sleep(30)

                # Iterate through all guilds
                for guild in self.bot.guilds:
                    # Skip if EventChannels cog is not loaded
                    eventchannels_cog = self.bot.get_cog("EventChannels")
                    if not eventchannels_cog:
                        continue

                    # Get guild config
                    config = self.config.guild(guild)
                    enabled_15min = await config.event_15min_before_enabled()
                    enabled_start = await config.event_start_enabled()

                    # Skip if both are disabled
                    if not enabled_15min and not enabled_start:
                        continue

                    # Get event channels data
                    eventchannels_config = eventchannels_cog.config.guild(guild)
                    event_channels = await eventchannels_config.event_channels()

                    # Get current time
                    now = datetime.now(timezone.utc)

                    # Check each event
                    for event in guild.scheduled_events:
                        if event.status != discord.EventStatus.scheduled:
                            continue

                        # Skip if event doesn't have channels
                        event_data = event_channels.get(str(event.id))
                        if not event_data:
                            continue

                        # Skip if no forum thread linked
                        if not event_data.get("forum_thread"):
                            continue

                        # Get the role
                        role_id = event_data.get("role")
                        if not role_id:
                            continue

                        role = guild.get_role(role_id)
                        if not role:
                            continue

                        # Calculate time until event
                        time_until_start = (event.start_time - now).total_seconds()

                        # Check if we should update for 15-min-before
                        if enabled_15min and event.id not in updated_15min:
                            # Update if between 14-16 minutes before start (2 minute window)
                            if 14 * 60 <= time_until_start <= 16 * 60:
                                log.info(f"Triggering 15-min update for event '{event.name}' ({time_until_start:.0f}s until start)")
                                await self._update_event_thread_message(guild, event, role, "15min")
                                updated_15min.add(event.id)

                        # Check if we should update for event start
                        if enabled_start and event.id not in updated_start:
                            # Update if within 2 minutes of start
                            if -60 <= time_until_start <= 60:
                                log.info(f"Triggering start update for event '{event.name}' ({time_until_start:.0f}s until start)")
                                await self._update_event_thread_message(guild, event, role, "start")
                                updated_start.add(event.id)

                    # Clean up old event IDs from tracking sets (events that have ended)
                    current_event_ids = {event.id for event in guild.scheduled_events}
                    updated_15min = {eid for eid in updated_15min if eid in current_event_ids}
                    updated_start = {eid for eid in updated_start if eid in current_event_ids}

            except asyncio.CancelledError:
                log.info("Event monitor loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in event monitor loop: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def forumthreadmessage(self, ctx):
        """Configure automatic forum thread messages.

        This cog will automatically send a message in newly created threads
        in a configured forum channel, edit it twice (at 2s and 4s intervals),
        and optionally delete it after another 2 seconds.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @forumthreadmessage.command(name="channel")
    async def set_channel(self, ctx, channel: Optional[discord.ForumChannel] = None):
        """Set the forum channel to monitor for new threads.

        Use without arguments to disable monitoring.

        Parameters
        ----------
        channel : discord.ForumChannel, optional
            The forum channel to monitor. If not provided, monitoring is disabled.

        Examples
        --------
        `[p]forumthreadmessage channel #my-forum` - Set the forum channel
        `[p]forumthreadmessage channel` - Disable monitoring
        """
        if channel is None:
            await self.config.guild(ctx.guild).forum_channel_id.set(None)
            await ctx.send("✅ Forum thread monitoring has been disabled.")
        else:
            await self.config.guild(ctx.guild).forum_channel_id.set(channel.id)
            await ctx.send(f"✅ Forum thread monitoring enabled for {channel.mention}")

    @forumthreadmessage.command(name="initialmessage")
    async def set_initial_message(self, ctx, *, message: str):
        """Set the initial message to send in new threads.

        This message will be sent immediately when a new thread is created.

        **Available placeholders:**
        - `{thread_name}` - The forum thread title

        Parameters
        ----------
        message : str
            The message content to send initially.

        Examples
        --------
        `[p]forumthreadmessage initialmessage Welcome to the thread!`
        `[p]forumthreadmessage initialmessage New thread: {thread_name}`
        """
        await self.config.guild(ctx.guild).initial_message.set(message)
        await ctx.send(f"✅ Initial message set to:\n```{message}```")

    @forumthreadmessage.command(name="editedmessage")
    async def set_edited_message(self, ctx, *, message: str):
        """Set the message content after editing.

        The initial message will be edited to this content after 2 seconds.

        **Available placeholders:**
        - `{thread_name}` - The forum thread title

        Parameters
        ----------
        message : str
            The message content after editing.

        Examples
        --------
        `[p]forumthreadmessage editedmessage Thread created successfully!`
        `[p]forumthreadmessage editedmessage Welcome to {thread_name}!`
        """
        await self.config.guild(ctx.guild).edited_message.set(message)
        await ctx.send(f"✅ Edited message set to:\n```{message}```")

    @forumthreadmessage.command(name="thirdeditedmessage")
    async def set_third_edited_message(self, ctx, *, message: str):
        """Set the message content for the third edit.

        The message will be edited to this content after another 2 seconds.

        **Available placeholders:**
        - `{thread_name}` - The forum thread title

        Parameters
        ----------
        message : str
            The message content for the third edit.

        Examples
        --------
        `[p]forumthreadmessage thirdeditedmessage Thread is ready!`
        `[p]forumthreadmessage thirdeditedmessage Welcome to {thread_name}!`
        """
        await self.config.guild(ctx.guild).third_edited_message.set(message)
        await ctx.send(f"✅ Third edited message set to:\n```{message}```")

    @forumthreadmessage.command(name="delete")
    async def set_delete(self, ctx, enabled: bool):
        """Toggle whether to delete the message after editing.

        If enabled, the message will be deleted 2 seconds after the second edit (at 6s).

        Parameters
        ----------
        enabled : bool
            True to enable deletion, False to disable.

        Examples
        --------
        `[p]forumthreadmessage delete true` - Enable deletion
        `[p]forumthreadmessage delete false` - Disable deletion
        """
        await self.config.guild(ctx.guild).delete_enabled.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"✅ Message deletion has been {status}.")

    @forumthreadmessage.group(name="rolebutton", invoke_without_command=True)
    async def rolebutton_group(self, ctx):
        """Configure role button settings.

        Use subcommands to enable/disable buttons, change emoji, or change text.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @rolebutton_group.command(name="enable")
    async def rolebutton_enable(self, ctx):
        """Enable automatic role button creation on event threads.

        Examples
        --------
        `[p]forumthreadmessage rolebutton enable`
        """
        await self.config.guild(ctx.guild).role_button_enabled.set(True)
        await ctx.send("✅ Role button creation has been enabled.")

    @rolebutton_group.command(name="disable")
    async def rolebutton_disable(self, ctx):
        """Disable automatic role button creation on event threads.

        Examples
        --------
        `[p]forumthreadmessage rolebutton disable`
        """
        await self.config.guild(ctx.guild).role_button_enabled.set(False)
        await ctx.send("✅ Role button creation has been disabled.")

    @rolebutton_group.command(name="emoji")
    async def rolebutton_emoji(self, ctx, emoji: str):
        """Set the emoji for the role button.

        Parameters
        ----------
        emoji : str
            The emoji to use on the button (can be a unicode emoji or custom emoji).

        Examples
        --------
        `[p]forumthreadmessage rolebutton emoji 🎉`
        `[p]forumthreadmessage rolebutton emoji :custom_emoji:`
        """
        await self.config.guild(ctx.guild).role_button_emoji.set(emoji)
        await ctx.send(f"✅ Role button emoji set to: {emoji}")

    @rolebutton_group.command(name="text")
    async def rolebutton_text(self, ctx, *, text: str):
        """Set the text label for the role button.

        Parameters
        ----------
        text : str
            The text to display on the button.

        Examples
        --------
        `[p]forumthreadmessage rolebutton text Join Event`
        `[p]forumthreadmessage rolebutton text Click to get role`
        """
        await self.config.guild(ctx.guild).role_button_text.set(text)
        await ctx.send(f"✅ Role button text set to: `{text}`")

    @forumthreadmessage.group(name="eventmessage", aliases=["eventmsg"], invoke_without_command=True)
    async def eventmessage_group(self, ctx):
        """Configure conditional message updates based on event timing.

        ALL events get global messages (met/notmet/default).
        Events matching keywords get keyword-specific messages (if configured).

        Role minimums are configured via EventChannels' setminimumroles command.

        Message types:
        - Global: Applied to all events
        - Keyword: Applied to events matching title keywords (overrides global if set)
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @eventmessage_group.command(name="enable15min")
    async def eventmsg_enable_15min(self, ctx):
        """Enable message updates 15 minutes before event starts.

        Examples
        --------
        `[p]forumthreadmessage eventmessage enable15min`
        """
        await self.config.guild(ctx.guild).event_15min_before_enabled.set(True)
        await ctx.send("✅ 15-minute-before message updates have been enabled.")

    @eventmessage_group.command(name="disable15min")
    async def eventmsg_disable_15min(self, ctx):
        """Disable message updates 15 minutes before event starts.

        Examples
        --------
        `[p]forumthreadmessage eventmessage disable15min`
        """
        await self.config.guild(ctx.guild).event_15min_before_enabled.set(False)
        await ctx.send("✅ 15-minute-before message updates have been disabled.")

    @eventmessage_group.command(name="enablestart")
    async def eventmsg_enable_start(self, ctx):
        """Enable message updates when event starts.

        Examples
        --------
        `[p]forumthreadmessage eventmessage enablestart`
        """
        await self.config.guild(ctx.guild).event_start_enabled.set(True)
        await ctx.send("✅ Event-start message updates have been enabled.")

    @eventmessage_group.command(name="disablestart")
    async def eventmsg_disable_start(self, ctx):
        """Disable message updates when event starts.

        Examples
        --------
        `[p]forumthreadmessage eventmessage disablestart`
        """
        await self.config.guild(ctx.guild).event_start_enabled.set(False)
        await ctx.send("✅ Event-start message updates have been disabled.")

    @eventmessage_group.command(name="15min_met")
    async def eventmsg_15min_met(self, ctx, *, message: str):
        """Set the message shown 15 min before start when role minimum IS met.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_met ✅ Event in 15 min! {role_count} members ready!`
        """
        await self.config.guild(ctx.guild).event_15min_role_min_met.set(message)
        await ctx.send(f"✅ 15-min message (role min met) set to:\n```{message}```")

    @eventmessage_group.command(name="15min_notmet")
    async def eventmsg_15min_notmet(self, ctx, *, message: str):
        """Set the message shown 15 min before start when role minimum is NOT met.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_notmet ⚠️ Event in 15 min but only {role_count}/{role_minimum} members!`
        """
        await self.config.guild(ctx.guild).event_15min_role_min_not_met.set(message)
        await ctx.send(f"✅ 15-min message (role min not met) set to:\n```{message}```")

    @eventmessage_group.command(name="15min_default")
    async def eventmsg_15min_default(self, ctx, *, message: str):
        """Set the default message shown 15 min before start.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_default ⏰ Event starting in 15 minutes!`
        """
        await self.config.guild(ctx.guild).event_15min_default.set(message)
        await ctx.send(f"✅ 15-min default message set to:\n```{message}```")

    @eventmessage_group.command(name="15min_keywords")
    async def eventmsg_15min_keywords(self, ctx, *keywords: str):
        """Set title keywords for keyword-specific 15-min messages.

        Events matching these keywords will use keyword-specific messages (if configured).
        All events (including non-matching) will use global messages.

        Note: Role minimums come from EventChannels' setminimumroles configuration.

        Parameters
        ----------
        keywords : str
            Keywords to match in event title (case-insensitive)

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_keywords raid dungeon` - Match raid/dungeon events
        `[p]forumthreadmessage eventmessage 15min_keywords` - Clear keywords
        """
        await self.config.guild(ctx.guild).event_15min_title_keywords.set(list(keywords))
        if keywords:
            await ctx.send(f"✅ 15-min keyword filter set to: {', '.join(keywords)}")
        else:
            await ctx.send("✅ 15-min keyword filter cleared")

    @eventmessage_group.command(name="15min_keyword_met")
    async def eventmsg_15min_keyword_met(self, ctx, *, message: str):
        """Set keyword-specific message for 15 min before when role minimum IS met.

        This overrides the global message for events matching keywords.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_keyword_met 🔥 RAID in 15 min! {role_count} raiders!`
        """
        await self.config.guild(ctx.guild).event_15min_keyword_role_min_met.set(message)
        await ctx.send(f"✅ 15-min keyword message (role min met) set to:\n```{message}```")

    @eventmessage_group.command(name="15min_keyword_notmet")
    async def eventmsg_15min_keyword_notmet(self, ctx, *, message: str):
        """Set keyword-specific message for 15 min before when role minimum is NOT met.

        This overrides the global message for events matching keywords.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_keyword_notmet ⚠️ RAID in 15 min! Need {role_minimum}, have {role_count}!`
        """
        await self.config.guild(ctx.guild).event_15min_keyword_role_min_not_met.set(message)
        await ctx.send(f"✅ 15-min keyword message (role min not met) set to:\n```{message}```")

    @eventmessage_group.command(name="15min_keyword_default")
    async def eventmsg_15min_keyword_default(self, ctx, *, message: str):
        """Set keyword-specific default message for 15 min before.

        This overrides the global default for events matching keywords.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage 15min_keyword_default 🎯 Special event in 15 minutes!`
        """
        await self.config.guild(ctx.guild).event_15min_keyword_default.set(message)
        await ctx.send(f"✅ 15-min keyword default message set to:\n```{message}```")

    @eventmessage_group.command(name="start_met")
    async def eventmsg_start_met(self, ctx, *, message: str):
        """Set the message shown at event start when role minimum IS met.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_met 🎉 Event starting! {role_count} members ready!`
        """
        await self.config.guild(ctx.guild).event_start_role_min_met.set(message)
        await ctx.send(f"✅ Event-start message (role min met) set to:\n```{message}```")

    @eventmessage_group.command(name="start_notmet")
    async def eventmsg_start_notmet(self, ctx, *, message: str):
        """Set the message shown at event start when role minimum is NOT met.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_notmet ⚠️ Event starting but only {role_count}/{role_minimum}!`
        """
        await self.config.guild(ctx.guild).event_start_role_min_not_met.set(message)
        await ctx.send(f"✅ Event-start message (role min not met) set to:\n```{message}```")

    @eventmessage_group.command(name="start_default")
    async def eventmsg_start_default(self, ctx, *, message: str):
        """Set the default message shown at event start.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_default 🚀 Event is starting NOW!`
        """
        await self.config.guild(ctx.guild).event_start_default.set(message)
        await ctx.send(f"✅ Event-start default message set to:\n```{message}```")

    @eventmessage_group.command(name="start_keywords")
    async def eventmsg_start_keywords(self, ctx, *keywords: str):
        """Set title keywords for keyword-specific event-start messages.

        Events matching these keywords will use keyword-specific messages (if configured).
        All events (including non-matching) will use global messages.

        Note: Role minimums come from EventChannels' setminimumroles configuration.

        Parameters
        ----------
        keywords : str
            Keywords to match in event title (case-insensitive)

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_keywords raid dungeon` - Match raid/dungeon events
        `[p]forumthreadmessage eventmessage start_keywords` - Clear keywords
        """
        await self.config.guild(ctx.guild).event_start_title_keywords.set(list(keywords))
        if keywords:
            await ctx.send(f"✅ Event-start keyword filter set to: {', '.join(keywords)}")
        else:
            await ctx.send("✅ Event-start keyword filter cleared")

    @eventmessage_group.command(name="start_keyword_met")
    async def eventmsg_start_keyword_met(self, ctx, *, message: str):
        """Set keyword-specific message for event start when role minimum IS met.

        This overrides the global message for events matching keywords.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_keyword_met 🔥 RAID STARTING! {role_count} raiders ready!`
        """
        await self.config.guild(ctx.guild).event_start_keyword_role_min_met.set(message)
        await ctx.send(f"✅ Event-start keyword message (role min met) set to:\n```{message}```")

    @eventmessage_group.command(name="start_keyword_notmet")
    async def eventmsg_start_keyword_notmet(self, ctx, *, message: str):
        """Set keyword-specific message for event start when role minimum is NOT met.

        This overrides the global message for events matching keywords.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_keyword_notmet ⚠️ RAID STARTING! Only {role_count}/{role_minimum}!`
        """
        await self.config.guild(ctx.guild).event_start_keyword_role_min_not_met.set(message)
        await ctx.send(f"✅ Event-start keyword message (role min not met) set to:\n```{message}```")

    @eventmessage_group.command(name="start_keyword_default")
    async def eventmsg_start_keyword_default(self, ctx, *, message: str):
        """Set keyword-specific default message for event start.

        This overrides the global default for events matching keywords.

        Placeholders: {role_count}, {role_minimum}, {event_name}, {role_mention}

        Parameters
        ----------
        message : str
            The message template

        Examples
        --------
        `[p]forumthreadmessage eventmessage start_keyword_default 🎯 Special event is starting NOW!`
        """
        await self.config.guild(ctx.guild).event_start_keyword_default.set(message)
        await ctx.send(f"✅ Event-start keyword default message set to:\n```{message}```")

    @forumthreadmessage.command(name="settings")
    async def show_settings(self, ctx):
        """Show the current configuration for this server."""
        guild_config = await self.config.guild(ctx.guild).all()

        forum_channel_id = guild_config["forum_channel_id"]
        if forum_channel_id:
            forum_channel = ctx.guild.get_channel(forum_channel_id)
            channel_display = forum_channel.mention if forum_channel else f"Unknown Channel (ID: {forum_channel_id})"
        else:
            channel_display = "Not configured"

        delete_status = "Enabled" if guild_config["delete_enabled"] else "Disabled"

        embed = discord.Embed(
            title="Forum Thread Message Settings",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Forum Channel",
            value=channel_display,
            inline=False,
        )
        embed.add_field(
            name="Initial Message",
            value=f"```{guild_config['initial_message']}```",
            inline=False,
        )
        embed.add_field(
            name="First Edited Message (after 2s)",
            value=f"```{guild_config['edited_message']}```",
            inline=False,
        )
        embed.add_field(
            name="Second Edited Message (after 4s)",
            value=f"```{guild_config['third_edited_message']}```",
            inline=False,
        )
        embed.add_field(
            name="Delete After Edit",
            value=delete_status,
            inline=False,
        )

        # Role button settings
        role_button_status = "Enabled" if guild_config["role_button_enabled"] else "Disabled"
        embed.add_field(
            name="Role Button",
            value=role_button_status,
            inline=True,
        )
        embed.add_field(
            name="Button Emoji",
            value=guild_config["role_button_emoji"],
            inline=True,
        )
        embed.add_field(
            name="Button Text",
            value=f"`{guild_config['role_button_text']}`",
            inline=True,
        )

        await ctx.send(embed=embed)

    @forumthreadmessage.command(name="debug")
    async def debug_button(self, ctx, thread: discord.Thread):
        """Debug why the role button isn't appearing on a thread message.

        This command checks all conditions required for the role button to appear.

        Parameters
        ----------
        thread : discord.Thread
            The forum thread to debug.

        Examples
        --------
        `[p]forumthreadmessage debug <thread_link_or_id>`
        """
        embed = discord.Embed(
            title=f"RoleButton Debug: {thread.name}",
            color=discord.Color.blue(),
        )

        issues = []
        warnings = []
        success = []

        # Check 1: Is it a forum thread?
        if not isinstance(thread.parent, discord.ForumChannel):
            issues.append("❌ Not a forum thread")
            embed.add_field(name="Thread Type", value="❌ Not a forum thread", inline=False)
        else:
            success.append("✅ Valid forum thread")
            embed.add_field(name="Thread Type", value="✅ Valid forum thread", inline=False)

        # Check 2: Is delete_enabled false?
        guild_config = await self.config.guild(ctx.guild).all()
        delete_enabled = guild_config["delete_enabled"]
        if delete_enabled:
            issues.append("❌ Delete is enabled - messages are deleted before button can be added")
            embed.add_field(name="Delete Enabled", value="❌ True (messages get deleted)", inline=False)
        else:
            success.append("✅ Delete disabled")
            embed.add_field(name="Delete Enabled", value="✅ False (messages persist)", inline=False)

        # Check 3: Is message stored?
        thread_messages = guild_config["thread_messages"]
        thread_data = thread_messages.get(str(thread.id))
        if not thread_data:
            issues.append(f"❌ No stored message for thread {thread.id}")
            embed.add_field(name="Stored Message", value="❌ Not found in storage", inline=False)
        else:
            message_id = thread_data.get("message_id")
            success.append(f"✅ Message stored (ID: {message_id})")
            embed.add_field(name="Stored Message", value=f"✅ Found (ID: {message_id})", inline=False)

            # Check 3b: Can we fetch the message?
            try:
                message = await thread.fetch_message(message_id)
                success.append("✅ Message exists in Discord")
                embed.add_field(name="Message Exists", value="✅ Found in Discord", inline=False)
            except discord.NotFound:
                issues.append(f"❌ Message {message_id} not found in Discord")
                embed.add_field(name="Message Exists", value="❌ Deleted or not found", inline=False)
            except discord.Forbidden:
                issues.append("❌ No permission to fetch message")
                embed.add_field(name="Message Exists", value="❌ Permission denied", inline=False)

        # Check 4: Is EventChannels cog loaded?
        eventchannels_cog = self.bot.get_cog("EventChannels")
        if not eventchannels_cog:
            issues.append("❌ EventChannels cog not loaded")
            embed.add_field(name="EventChannels Cog", value="❌ Not loaded", inline=False)
        else:
            success.append("✅ EventChannels cog loaded")
            embed.add_field(name="EventChannels Cog", value="✅ Loaded", inline=False)

            # Check 5: Is there a linked event?
            try:
                eventchannels_config = eventchannels_cog.config.guild(ctx.guild)
                event_channels = await eventchannels_config.event_channels()

                linked_event = None
                for event_id, event_data in event_channels.items():
                    if event_data.get("forum_thread") == thread.id:
                        linked_event = event_id
                        role_id = event_data.get("role")
                        text_channel_id = event_data.get("text")

                        embed.add_field(name="Linked Event", value=f"✅ Event ID: {event_id}", inline=False)

                        # Check role
                        role = ctx.guild.get_role(role_id)
                        if role:
                            success.append(f"✅ Role exists: {role.name}")
                            embed.add_field(name="Event Role", value=f"✅ {role.mention}", inline=False)
                        else:
                            issues.append(f"❌ Role {role_id} not found")
                            embed.add_field(name="Event Role", value=f"❌ Role {role_id} not found", inline=False)

                        # Check text channel
                        text_channel = ctx.guild.get_channel(text_channel_id)
                        if text_channel:
                            success.append(f"✅ Event channel exists: {text_channel.name}")
                            embed.add_field(name="Event Channel", value=f"✅ {text_channel.mention}", inline=False)
                        else:
                            warnings.append(f"⚠️ Event channel {text_channel_id} not found")
                            embed.add_field(name="Event Channel", value=f"⚠️ Not found (ID: {text_channel_id})", inline=False)

                        break

                if not linked_event:
                    warnings.append("⚠️ No event linked to this thread")
                    embed.add_field(name="Linked Event", value="⚠️ No event links to this thread", inline=False)

            except Exception as e:
                issues.append(f"❌ Error checking EventChannels: {e}")
                embed.add_field(name="EventChannels Check", value=f"❌ Error: {str(e)[:100]}", inline=False)

        # Summary
        summary = []
        if issues:
            summary.append(f"**Issues ({len(issues)}):**\n" + "\n".join(issues))
        if warnings:
            summary.append(f"**Warnings ({len(warnings)}):**\n" + "\n".join(warnings))
        if success:
            summary.append(f"**Passing ({len(success)}):**\n" + "\n".join(success))

        embed.add_field(
            name="Summary",
            value="\n\n".join(summary) if summary else "No checks performed",
            inline=False
        )

        # Determine overall status
        if issues:
            embed.color = discord.Color.red()
            embed.description = "⚠️ Issues found that prevent the button from appearing"
        elif warnings:
            embed.color = discord.Color.orange()
            embed.description = "⚠️ Some warnings, button may not appear"
        else:
            embed.color = discord.Color.green()
            embed.description = "✅ All checks passed! Button should appear when event channel is created"

        await ctx.send(embed=embed)

    async def add_role_button_to_thread(self, guild: discord.Guild, thread: discord.Thread) -> bool:
        """Add role button to a thread's stored message.

        This is a helper method that can be called from anywhere to add the role button.
        Returns True if successful, False otherwise.

        Parameters
        ----------
        guild : discord.Guild
            The guild containing the thread
        thread : discord.Thread
            The thread to add the button to

        Returns
        -------
        bool
            True if button was added successfully, False otherwise
        """
        try:
            # Check if role buttons are enabled
            role_button_enabled = await self.config.guild(guild).role_button_enabled()
            if not role_button_enabled:
                log.debug(f"Role buttons are disabled for guild {guild.name}, skipping button addition")
                return False

            # Get stored message
            thread_messages = await self.config.guild(guild).thread_messages()
            thread_data = thread_messages.get(str(thread.id))

            if not thread_data:
                log.warning(f"No stored message found for thread {thread.id}")
                return False

            message_id = thread_data.get("message_id")

            # Get EventChannels cog
            eventchannels_cog = self.bot.get_cog("EventChannels")
            if not eventchannels_cog:
                log.warning("EventChannels cog is not loaded")
                return False

            # Find linked event
            eventchannels_config = eventchannels_cog.config.guild(guild)
            event_channels = await eventchannels_config.event_channels()

            matching_event_id = None
            matching_role_id = None

            for event_id, event_data in event_channels.items():
                if event_data.get("forum_thread") == thread.id:
                    matching_event_id = event_id
                    matching_role_id = event_data.get("role")
                    break

            if not matching_event_id or not matching_role_id:
                log.warning(f"No event linked to thread {thread.id}")
                return False

            # Get the role
            role = guild.get_role(matching_role_id)
            if not role:
                log.warning(f"Role {matching_role_id} not found")
                return False

            # Get button customization settings
            button_emoji = await self.config.guild(guild).role_button_emoji()
            button_text = await self.config.guild(guild).role_button_text()

            # Fetch and edit the message
            message = await thread.fetch_message(message_id)
            view = RoleButtonView(role, emoji=button_emoji, label=button_text)
            await message.edit(
                view=view,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )

            log.info(f"✅ Added role button for {role.name} to thread {thread.name} ({thread.id})")
            return True

        except discord.NotFound:
            log.warning(f"Message not found in thread {thread.id}")
            return False
        except discord.Forbidden:
            log.error(f"No permission to edit message in thread {thread.id}")
            return False
        except Exception as e:
            log.error(f"Error adding button to thread {thread.id}: {e}", exc_info=True)
            return False

    @forumthreadmessage.command(name="addbutton")
    async def add_button_manual(self, ctx, thread: discord.Thread):
        """Manually add the role button to a thread's message.

        This command finds the stored message in a thread and adds the event role button to it.
        Useful for fixing threads where the button didn't appear automatically.

        Parameters
        ----------
        thread : discord.Thread
            The forum thread to add the button to.

        Examples
        --------
        `[p]forumthreadmessage addbutton <thread_link_or_id>`
        """
        # Use the helper method
        success = await self.add_role_button_to_thread(ctx.guild, thread)

        if success:
            await ctx.send(f"✅ Successfully added role button to message in {thread.mention}")
        else:
            await ctx.send(f"❌ Failed to add button. Check logs for details or use `{ctx.prefix}forumthreadmessage debug {thread.id}` for more info.")

    @forumthreadmessage.command(name="test")
    async def test_flow(self, ctx, role: Optional[discord.Role] = None):
        """Test the full message flow over 1 minute.

        This command demonstrates the full flow:
        1. Send initial message (0s)
        2. Edit message after 20s
        3. Add role button after 40s (if role provided)
        4. Complete after 60s

        Parameters
        ----------
        role : discord.Role, optional
            The role to use for the button test. If not provided, skips button step.

        Examples
        --------
        `[p]forumthreadmessage test` - Test without role button
        `[p]forumthreadmessage test @EventRole` - Test with role button
        """
        try:
            # Step 1: Send initial message (0s)
            await ctx.send("**[Test Flow Started]** Sending initial message...")

            guild_config = await self.config.guild(ctx.guild).all()
            initial_message = guild_config["initial_message"]
            edited_message = guild_config["edited_message"]

            test_message = await ctx.send(
                initial_message,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )
            log.info(f"Test: Sent initial message in {ctx.channel.name}")

            # Step 2: Wait 20s and edit (20s mark)
            await ctx.send(f"**[Test]** Waiting 20 seconds before editing...")
            await asyncio.sleep(20)

            await test_message.edit(
                content=edited_message,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )
            await ctx.send(f"**[Test]** Message edited at 20s mark!")
            log.info(f"Test: Edited message in {ctx.channel.name}")

            # Step 3: Wait 20s more and add button (40s mark)
            if role:
                await ctx.send(f"**[Test]** Waiting 20 seconds before adding role button...")
                await asyncio.sleep(20)

                view = RoleButtonView(role)
                await test_message.edit(
                    view=view,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
                )
                await ctx.send(f"**[Test]** Role button added at 40s mark! Button will add {role.mention}")
                log.info(f"Test: Added role button for {role.name} in {ctx.channel.name}")

                # Step 4: Wait final 20s (60s total)
                await ctx.send(f"**[Test]** Waiting final 20 seconds...")
                await asyncio.sleep(20)
            else:
                # No role, wait 40s total instead
                await ctx.send(f"**[Test]** No role provided, waiting 40 seconds...")
                await asyncio.sleep(40)

            # Complete
            await ctx.send(f"✅ **[Test Complete]** Full flow finished at 60s mark!")
            log.info(f"Test: Flow completed in {ctx.channel.name}")

        except discord.HTTPException as e:
            await ctx.send(f"❌ **[Test Failed]** HTTP error: {e}")
            log.error(f"Test failed with HTTP error: {e}")
        except Exception as e:
            await ctx.send(f"❌ **[Test Failed]** Unexpected error: {e}")
            log.error(f"Test failed with unexpected error: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """Listen for new threads being created in forum channels."""
        # Only process forum threads
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        # Get the guild configuration
        guild = thread.guild
        if not guild:
            return

        guild_config = await self.config.guild(guild).all()
        forum_channel_id = guild_config["forum_channel_id"]

        # Check if we're monitoring this forum channel
        if not forum_channel_id or thread.parent.id != forum_channel_id:
            return

        # Get message configuration
        initial_message = guild_config["initial_message"]
        edited_message = guild_config["edited_message"]
        third_edited_message = guild_config["third_edited_message"]
        delete_enabled = guild_config["delete_enabled"]

        # Format messages with placeholders
        try:
            formatted_initial = initial_message.format(thread_name=thread.name)
        except KeyError:
            formatted_initial = initial_message

        try:
            formatted_edited = edited_message.format(thread_name=thread.name)
        except KeyError:
            formatted_edited = edited_message

        try:
            formatted_third = third_edited_message.format(thread_name=thread.name)
        except KeyError:
            formatted_third = third_edited_message

        try:
            # Send the initial message with suppressed notifications but allow all mentions
            message = await thread.send(
                formatted_initial,
                silent=True,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )
            log.info(f"Sent initial message in thread {thread.name} ({thread.id}) in guild {guild.name}")

            # Store the message reference for later editing when eventchannels creates a channel
            if not delete_enabled:
                thread_messages = await self.config.guild(guild).thread_messages()
                thread_messages[str(thread.id)] = {
                    "message_id": message.id,
                    "thread_name": thread.name,
                }
                await self.config.guild(guild).thread_messages.set(thread_messages)
                log.info(f"Stored message reference for thread {thread.name} ({thread.id})")

            # Wait 2 seconds
            await asyncio.sleep(2)

            # Edit the message (first edit)
            await message.edit(
                content=formatted_edited,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )
            log.info(f"Edited message (first edit) in thread {thread.name} ({thread.id}) in guild {guild.name}")

            # Wait another 2 seconds
            await asyncio.sleep(2)

            # Edit the message again (second edit)
            await message.edit(
                content=formatted_third,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
            )
            log.info(f"Edited message (second edit) in thread {thread.name} ({thread.id}) in guild {guild.name}")

            # If deletion is enabled, wait another 2 seconds and delete
            if delete_enabled:
                await asyncio.sleep(2)
                await message.delete()
                log.info(f"Deleted message in thread {thread.name} ({thread.id}) in guild {guild.name}")

        except discord.HTTPException as e:
            log.error(f"Failed to send/edit/delete message in thread {thread.id}: {e}")
        except Exception as e:
            log.error(f"Unexpected error in on_thread_create for thread {thread.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Listen for channel creation to detect when eventchannels creates event channels."""
        # Only process text channels
        if not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        if not guild:
            return

        log.debug(f"Channel created: {channel.name} ({channel.id}) in {guild.name}")

        # Try to get eventchannels cog
        try:
            eventchannels_cog = self.bot.get_cog("EventChannels")
            if not eventchannels_cog:
                log.debug(f"EventChannels cog not loaded, skipping button logic for {channel.name}")
                return

            # Retry with delays to wait for eventchannels to finish setting up
            # Retry intervals: 1s, 2s, 3s (total ~6s of retries)
            retry_delays = [1, 2, 3]

            matching_event_id = None
            matching_role_id = None
            matching_thread_id = None

            for attempt, delay in enumerate(retry_delays, start=1):
                # Wait before checking
                await asyncio.sleep(delay)

                # Get eventchannels config
                eventchannels_config = eventchannels_cog.config.guild(guild)
                event_channels = await eventchannels_config.event_channels()

                # Find if this channel is an event channel
                for event_id, event_data in event_channels.items():
                    if event_data.get("text") == channel.id:
                        matching_event_id = event_id
                        matching_role_id = event_data.get("role")
                        matching_thread_id = event_data.get("forum_thread")
                        log.debug(f"Found matching event {event_id} for channel {channel.name} on attempt {attempt}")
                        break

                # If we found the event and it has a forum thread, proceed
                if matching_event_id and matching_thread_id:
                    log.info(f"Found event {matching_event_id} with forum thread {matching_thread_id} on attempt {attempt}")
                    break

                # If we found the event but no forum thread yet, check if this is the last attempt
                if matching_event_id and attempt < len(retry_delays):
                    log.debug(f"Event {matching_event_id} found but no forum_thread yet on attempt {attempt}, will retry")
                    matching_event_id = None  # Reset for next attempt
                elif matching_event_id and attempt == len(retry_delays):
                    log.debug(f"Event {matching_event_id} found but no forum_thread after {attempt} attempts")
                    break

            if not matching_event_id or not matching_role_id:
                log.debug(f"Channel {channel.name} is not an event channel or missing role, skipping button logic")
                return

            # Get the role
            role = guild.get_role(matching_role_id)
            if not role:
                log.warning(f"Could not find role {matching_role_id} for event {matching_event_id}")
                return

            # Get the event to extract the name
            event = None
            for scheduled_event in guild.scheduled_events:
                if str(scheduled_event.id) == matching_event_id:
                    event = scheduled_event
                    break

            if not event:
                log.warning(f"Could not find scheduled event {matching_event_id}")
                return

            log.info(f"Event channel created for '{event.name}' with role {role.name}")

            # Check if role buttons are enabled
            role_button_enabled = await self.config.guild(guild).role_button_enabled()
            if not role_button_enabled:
                log.debug(f"Role buttons are disabled for guild {guild.name}, skipping button addition")
                return

            # Get the linked forum thread using the new helper method
            if matching_thread_id:
                log.debug(f"Event {matching_event_id} has forum_thread link: {matching_thread_id}")
                thread = await eventchannels_cog.get_event_forum_thread(guild, int(matching_event_id))
                if thread:
                    log.debug(f"Retrieved forum thread {thread.name} ({thread.id}) for event {matching_event_id}")

                    # Get the stored message for this thread
                    thread_messages = await self.config.guild(guild).thread_messages()
                    thread_data = thread_messages.get(str(thread.id))

                    if thread_data:
                        message_id = thread_data.get("message_id")
                        log.debug(f"Found stored message ID {message_id} for thread {thread.id}")

                        try:
                            message = await thread.fetch_message(message_id)
                            log.debug(f"Successfully fetched message {message_id} from thread {thread.id}")

                            # Get button customization settings
                            button_emoji = await self.config.guild(guild).role_button_emoji()
                            button_text = await self.config.guild(guild).role_button_text()

                            # Edit the message to add the role button
                            view = RoleButtonView(role, emoji=button_emoji, label=button_text)
                            await message.edit(
                                view=view,
                                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=True)
                            )

                            log.info(f"✅ Added role button for {role.name} to message in thread {thread.name} ({thread.id})")
                        except discord.NotFound:
                            log.warning(f"❌ Could not find message {message_id} in thread {thread.id} - message may have been deleted")
                        except discord.Forbidden:
                            log.error(f"❌ No permission to edit message in thread {thread.id}")
                        except Exception as e:
                            log.error(f"❌ Error editing message in thread {thread.id}: {e}", exc_info=True)
                    else:
                        log.warning(f"⚠️ No stored message found for thread {thread.id} - message may have been deleted or delete_enabled is True")
                else:
                    log.warning(f"⚠️ Could not retrieve forum thread for event {matching_event_id}")
            else:
                log.debug(f"No forum thread linked to event {matching_event_id}")

        except Exception as e:
            log.error(f"Error in on_guild_channel_create: {e}", exc_info=True)
