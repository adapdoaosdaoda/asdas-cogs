"""ForumThreadMessage - Automatically send, edit, and optionally delete messages in new forum threads."""
import asyncio
import logging
from typing import Optional

import discord
from redbot.core import commands, Config

log = logging.getLogger("red.asdas-cogs.forumthreadmessage")


class RoleButtonView(discord.ui.View):
    """View with a button to add the event role."""

    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)  # Persistent view
        self.role = role
        # Add the button with role ID in custom_id
        self.add_item(RoleButton(role))


class RoleButton(discord.ui.Button):
    """Button to add an event role to the user."""

    def __init__(self, role: discord.Role):
        super().__init__(
            label="Join Event Role",
            emoji="🎫",
            style=discord.ButtonStyle.primary,
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
    After 2 seconds, the message is edited to different content.
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
            edited_message="Thread created successfully!",  # Message content after edit
            delete_enabled=False,  # Whether to delete the message after editing
            thread_messages={},  # Store {thread_id: {"message_id": id, "thread_name": name}}
        )

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def forumthreadmessage(self, ctx):
        """Configure automatic forum thread messages.

        This cog will automatically send a message in newly created threads
        in a configured forum channel, edit it after 2 seconds, and optionally
        delete it after another 2 seconds.
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

        Parameters
        ----------
        message : str
            The message content to send initially.

        Examples
        --------
        `[p]forumthreadmessage initialmessage Welcome to the thread!`
        """
        await self.config.guild(ctx.guild).initial_message.set(message)
        await ctx.send(f"✅ Initial message set to:\n```{message}```")

    @forumthreadmessage.command(name="editedmessage")
    async def set_edited_message(self, ctx, *, message: str):
        """Set the message content after editing.

        The initial message will be edited to this content after 2 seconds.

        Parameters
        ----------
        message : str
            The message content after editing.

        Examples
        --------
        `[p]forumthreadmessage editedmessage Thread created successfully!`
        """
        await self.config.guild(ctx.guild).edited_message.set(message)
        await ctx.send(f"✅ Edited message set to:\n```{message}```")

    @forumthreadmessage.command(name="delete")
    async def set_delete(self, ctx, enabled: bool):
        """Toggle whether to delete the message after editing.

        If enabled, the message will be deleted 2 seconds after being edited.

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
            name="Edited Message",
            value=f"```{guild_config['edited_message']}```",
            inline=False,
        )
        embed.add_field(
            name="Delete After Edit",
            value=delete_status,
            inline=False,
        )

        await ctx.send(embed=embed)

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

            await test_message.edit(content=edited_message)
            await ctx.send(f"**[Test]** Message edited at 20s mark!")
            log.info(f"Test: Edited message in {ctx.channel.name}")

            # Step 3: Wait 20s more and add button (40s mark)
            if role:
                await ctx.send(f"**[Test]** Waiting 20 seconds before adding role button...")
                await asyncio.sleep(20)

                view = RoleButtonView(role)
                await test_message.edit(view=view)
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
        delete_enabled = guild_config["delete_enabled"]

        try:
            # Send the initial message with suppressed notifications but allow all mentions
            message = await thread.send(
                initial_message,
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

            # Edit the message
            await message.edit(content=edited_message)
            log.info(f"Edited message in thread {thread.name} ({thread.id}) in guild {guild.name}")

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

        # Wait a moment for eventchannels to finish setting up
        await asyncio.sleep(1)

        # Try to get eventchannels cog and its config
        try:
            eventchannels_cog = self.bot.get_cog("EventChannels")
            if not eventchannels_cog:
                return

            # Get eventchannels config
            eventchannels_config = eventchannels_cog.config.guild(guild)
            event_channels = await eventchannels_config.event_channels()

            # Find if this channel is an event channel
            matching_event_id = None
            matching_role_id = None

            for event_id, event_data in event_channels.items():
                if event_data.get("text") == channel.id:
                    matching_event_id = event_id
                    matching_role_id = event_data.get("role")
                    break

            if not matching_event_id or not matching_role_id:
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

            # Find matching threads by name
            thread_messages = await self.config.guild(guild).thread_messages()

            for thread_id_str, thread_data in thread_messages.items():
                thread_name = thread_data.get("thread_name", "")

                # Match if the event name is in the thread name (case-insensitive)
                if event.name.lower() in thread_name.lower():
                    thread_id = int(thread_id_str)
                    message_id = thread_data.get("message_id")

                    # Get the thread and message
                    thread = guild.get_thread(thread_id)
                    if not thread:
                        # Try fetching it
                        try:
                            thread = await guild.fetch_channel(thread_id)
                        except (discord.NotFound, discord.Forbidden):
                            log.warning(f"Could not find thread {thread_id}")
                            continue

                    if not isinstance(thread, discord.Thread):
                        continue

                    try:
                        message = await thread.fetch_message(message_id)

                        # Edit the message to add the role button
                        view = RoleButtonView(role)
                        await message.edit(view=view)

                        log.info(f"Added role button for {role.name} to message in thread {thread.name} ({thread.id})")
                    except discord.NotFound:
                        log.warning(f"Could not find message {message_id} in thread {thread_id}")
                    except discord.Forbidden:
                        log.error(f"No permission to edit message in thread {thread_id}")
                    except Exception as e:
                        log.error(f"Error editing message in thread {thread_id}: {e}", exc_info=True)

        except Exception as e:
            log.error(f"Error in on_guild_channel_create: {e}", exc_info=True)
