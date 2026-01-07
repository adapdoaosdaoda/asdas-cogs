"""ForumThreadMessage - Automatically send, edit, and optionally delete messages in new forum threads."""
import asyncio
import logging
from typing import Optional

import discord
from redbot.core import commands, Config

log = logging.getLogger("red.asdas-cogs.forumthreadmessage")


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
            # Send the initial message with suppressed notifications
            message = await thread.send(initial_message, silent=True)
            log.info(f"Sent initial message in thread {thread.name} ({thread.id}) in guild {guild.name}")

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
