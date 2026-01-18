import asyncio
from datetime import datetime, timedelta, timezone
import logging

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

from .utils import UtilsMixin
from .handlers import HandlersMixin
from .events import EventsMixin
from .commands_config import CommandsConfigMixin
from .commands_view import CommandsViewMixin
from .commands_test import CommandsTestMixin
from .timing import (
    DEFAULT_CREATION_MINUTES,
    DEFAULT_DELETION_HOURS,
    WARNING_MINUTES,
    EXTENSION_HOURS,
)

log = logging.getLogger("red.eventchannels")


class EventChannels(UtilsMixin, HandlersMixin, EventsMixin, CommandsConfigMixin, CommandsViewMixin, CommandsTestMixin, commands.Cog):
    """Creates text & voice channels from Discord Scheduled Events and cleans them up."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817263540)
        self.config.register_guild(
            event_channels={},
            thread_event_links={},  # Maps thread_id (str) -> event_id (str) for forum threads linked to events
            category_id=None,
            timezone="UTC",  # Default timezone
            role_format="{name} {day_abbrev} {day}. {month_abbrev} {time}",  # Default role format
            channel_format="{name}᲼{type}",  # Default channel name format
            space_replacer="᲼",  # Character to replace spaces in channel names
            creation_minutes=DEFAULT_CREATION_MINUTES,  # Default creation time in minutes before event
            deletion_hours=DEFAULT_DELETION_HOURS,  # Default deletion time in hours
            announcement_message="{role} The event is starting soon!",  # Default announcement
            event_start_message="{role} The event is starting now!",  # Message sent at event start
            deletion_warning_message=f"⚠️ These channels will be deleted in {WARNING_MINUTES} minutes. React with ⏰ to extend deletion by {EXTENSION_HOURS} hours.",  # Warning before deletion
            divider_enabled=True,  # Enable divider channel by default
            divider_name="━━━━━━ EVENT CHANNELS ━━━━━━",  # Default divider name
            divider_channel_id=None,  # Stores the divider channel ID
            divider_roles=[],  # Track role IDs that have access to the divider
            channel_name_limit=100,  # Character limit for channel names (Discord max is 100)
            channel_name_limit_char="",  # Character to limit name at (empty = use numeric limit)
            voice_multipliers={},  # Dictionary of keyword:multiplier pairs for dynamic voice channel creation
            voice_minimum_roles={},  # Dictionary of keyword:minimum_count pairs for enforcing minimum role members
            minimum_retry_intervals=[10, 5, 2],  # Minutes before event start to retry if minimum not met (default: 10min, 5min, 2min)
            whitelisted_roles=[],  # List of role IDs that always have view, read, connect & speak permissions
            archive_category_id=None,  # Category where channels with messages are moved instead of being deleted
            deletion_extensions={},  # Maps event_id (str) -> {"delete_time": timestamp, "warning_message_id": int, "text_channel_id": int}
            archived_channels={},  # Maps channel_id (str) -> {"event_name": str, "original_name": str, "archived_at": timestamp, "event_id": str}
        )
        self.active_tasks = {}  # Store tasks by event_id for cancellation
        self._config_lock = asyncio.Lock()  # Protect event_channels config updates
        self._divider_lock = asyncio.Lock()  # Protect divider channel operations
        self.bot.loop.create_task(self._startup_scan())

    # ---------- Setup Commands ----------

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def eventchannels(self, ctx):
        """Display all EventChannels commands with explanations."""
        prefix = ctx.clean_prefix

        embed = discord.Embed(
            title="EventChannels Commands",
            description="Automatically creates text & voice channels from Discord Scheduled Events and manages cleanup.",
            color=discord.Color.blue()
        )

        # Configuration Commands - Basic
        config_commands_basic = (
            f"`{prefix}eventchannels setcategory <category>` - Set where event channels will be created\n"
            f"`{prefix}eventchannels setarchivecategory <category>` - Set where archived channels will be moved\n"
            f"`{prefix}eventchannels settimezone <timezone>` - Set timezone for event role matching (e.g., Europe/Amsterdam)\n"
            f"`{prefix}eventchannels setcreationtime <minutes>` - Set when channels are created before event start (default: 15)\n"
            f"`{prefix}eventchannels setdeletion <hours>` - Set when channels are deleted after event start (default: 4)\n"
        )
        embed.add_field(name="Configuration - Basic", value=config_commands_basic, inline=False)

        # Configuration Commands - Advanced
        config_commands_advanced = (
            f"`{prefix}eventchannels setroleformat <format>` - Customize role name format pattern\n"
            f"`{prefix}eventchannels setchannelformat <format>` - Customize channel name format pattern\n"
            f"`{prefix}eventchannels setannouncement <message>` - Set announcement message in event channels\n"
            f"`{prefix}eventchannels setstartmessage <message>` - Set message posted when event starts\n"
            f"`{prefix}eventchannels setdeletionwarning <message>` - Set warning message before channel deletion\n"
            f"`{prefix}eventchannels setchannelnamelimit <limit>` - Set maximum character limit for channel names (default: 100)\n"
            f"`{prefix}eventchannels linkthread <thread> <event_id>` - Manually link a forum thread to an event\n"
        )
        embed.add_field(name="Configuration - Advanced", value=config_commands_advanced, inline=False)

        # Archive Features
        archive_commands = (
            f"**Automatic Archiving:**\n"
            f"Channels with user messages are automatically archived instead of deleted.\n"
            f"Archived channels are moved to the archive category, made read-only, and prefixed with 'archived-'.\n\n"
            f"**Deletion Extension:**\n"
            f"React with ⏰ to the deletion warning message to extend deletion by {EXTENSION_HOURS} hours.\n"
            f"This allows you to keep channels open longer if needed."
        )
        embed.add_field(name="Archive & Deletion Features", value=archive_commands, inline=False)

        # Voice Multiplier Commands
        voice_commands = (
            f"`{prefix}eventchannels setvoicemultiplier <keyword> <count>` - Add/update voice multiplier for a keyword\n"
            f"`{prefix}eventchannels listvoicemultipliers` - List all configured voice multipliers\n"
            f"`{prefix}eventchannels removevoicemultiplier <keyword>` - Remove a specific voice multiplier\n"
            f"`{prefix}eventchannels disablevoicemultiplier` - Disable all voice multipliers\n"
            f"`{prefix}eventchannels setminimumroles <keyword> <count>` - Set minimum role members required for a keyword\n"
            f"`{prefix}eventchannels listminimumroles` - List all configured minimum role requirements\n"
            f"`{prefix}eventchannels removeminimumroles <keyword>` - Remove minimum role requirement for a keyword\n"
        )
        embed.add_field(name="Voice Channel Multiplier", value=voice_commands, inline=False)

        # Divider Commands
        divider_commands = (
            f"`{prefix}eventchannels setdivider <true/false> [name]` - Enable/disable divider channel\n"
        )
        embed.add_field(name="Divider Channel", value=divider_commands, inline=False)

        # Whitelisted Roles Commands
        whitelist_commands = (
            f"`{prefix}eventchannels addwhitelistedrole <role>` - Add a role to the whitelist for automatic permissions\n"
            f"`{prefix}eventchannels removewhitelistedrole <role>` - Remove a role from the whitelist\n"
            f"`{prefix}eventchannels listwhitelistedroles` - List all whitelisted roles\n"
        )
        embed.add_field(name="Whitelisted Roles", value=whitelist_commands, inline=False)

        # View Settings
        view_commands = f"`{prefix}eventchannels viewsettings` - View current configuration settings"
        embed.add_field(name="View Settings", value=view_commands, inline=False)

        # Testing
        test_commands = (
            f"`{prefix}eventchannels testchannellock` - Test channel locking permissions\n"
            f"`{prefix}eventchannels testeventroles [role]` - Show event role member counts\n"
            f"`{prefix}eventchannels stresstest` - Comprehensive stress test of all features\n"
        )
        embed.add_field(name="Testing", value=test_commands, inline=False)

        embed.set_footer(text="Most commands require Manage Guild permission")

        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            # Fallback to plain text if bot lacks embed permissions
            message = (
                f"**EventChannels Commands**\n\n"
                f"**Configuration - Basic:**\n{config_commands_basic}\n\n"
                f"**Configuration - Advanced:**\n{config_commands_advanced}\n\n"
                f"**Archive & Deletion Features:**\n{archive_commands}\n\n"
                f"**Voice Channel Multiplier:**\n{voice_commands}\n\n"
                f"**Divider Channel:**\n{divider_commands}\n\n"
                f"**Whitelisted Roles:**\n{whitelist_commands}\n\n"
                f"**View Settings:**\n{view_commands}\n\n"
                f"**Testing:**\n{test_commands}\n\n"
                f"Most commands require Manage Guild permission"
            )
            await ctx.send(message)

    # ---------- Configuration Commands ----------

    @eventchannels.command(name="setcategory")
    async def setcategory(self, ctx, category: discord.CategoryChannel):
        """Wrapper for seteventcategory from CommandsConfigMixin."""
        await self.seteventcategory(ctx, category)

    @eventchannels.command(name="setarchivecategory")
    async def setarchivecategory(self, ctx, category: discord.CategoryChannel):
        """Wrapper for seteventarchivecategory from CommandsConfigMixin."""
        await self.seteventarchivecategory(ctx, category)

    @eventchannels.command(name="settimezone")
    async def settimezone(self, ctx, tz: str):
        """Wrapper for seteventtimezone from CommandsConfigMixin."""
        await self.seteventtimezone(ctx, tz)

    @eventchannels.command(name="setdeletion")
    async def setdeletion(self, ctx, hours: int):
        """Wrapper for seteventdeletion from CommandsConfigMixin."""
        await self.seteventdeletion(ctx, hours)

    @eventchannels.command(name="setcreationtime")
    async def setcreationtime(self, ctx, minutes: int):
        """Wrapper for seteventcreationtime from CommandsConfigMixin."""
        await self.seteventcreationtime(ctx, minutes)

    @eventchannels.command(name="setroleformat")
    async def setroleformat(self, ctx, *, format_string: str):
        """Wrapper for seteventroleformat from CommandsConfigMixin."""
        await self.seteventroleformat(ctx, format_string=format_string)

    @eventchannels.command(name="setchannelformat")
    async def setchannelformat(self, ctx, format_string: str, space_replacer: str = None):
        """Wrapper for seteventchannelformat from CommandsConfigMixin."""
        await self.seteventchannelformat(ctx, format_string, space_replacer)

    @eventchannels.command(name="setchannelnamelimit")
    async def setchannelnamelimit_cmd(self, ctx, limit: str):
        """Wrapper for setchannelnamelimit from CommandsConfigMixin."""
        await self.setchannelnamelimit(ctx, limit)

    @eventchannels.command(name="setvoicemultiplier")
    async def setvoicemultiplier_cmd(self, ctx, keyword: str, multiplier: int):
        """Wrapper for setvoicemultiplier from CommandsConfigMixin."""
        await self.setvoicemultiplier(ctx, keyword, multiplier)

    @eventchannels.command(name="disablevoicemultiplier")
    async def disablevoicemultiplier_cmd(self, ctx):
        """Wrapper for disablevoicemultiplier from CommandsConfigMixin."""
        await self.disablevoicemultiplier(ctx)

    @eventchannels.command(name="removevoicemultiplier")
    async def removevoicemultiplier_cmd(self, ctx, keyword: str):
        """Wrapper for removevoicemultiplier from CommandsConfigMixin."""
        await self.removevoicemultiplier(ctx, keyword)

    @eventchannels.command(name="setminimumroles")
    async def setminimumroles_cmd(self, ctx, keyword: str, minimum: int):
        """Wrapper for setminimumroles from CommandsConfigMixin."""
        await self.setminimumroles(ctx, keyword, minimum)

    @eventchannels.command(name="removeminimumroles")
    async def removeminimumroles_cmd(self, ctx, keyword: str):
        """Wrapper for removeminimumroles from CommandsConfigMixin."""
        await self.removeminimumroles(ctx, keyword)

    @eventchannels.command(name="addwhitelistedrole")
    async def addwhitelistedrole_cmd(self, ctx, role: discord.Role):
        """Wrapper for addwhitelistedrole from CommandsConfigMixin."""
        await self.addwhitelistedrole(ctx, role)

    @eventchannels.command(name="removewhitelistedrole")
    async def removewhitelistedrole_cmd(self, ctx, role: discord.Role):
        """Wrapper for removewhitelistedrole from CommandsConfigMixin."""
        await self.removewhitelistedrole(ctx, role)

    @eventchannels.command(name="setannouncement")
    async def setannouncement(self, ctx, *, message: str):
        """Wrapper for seteventannouncement from CommandsConfigMixin."""
        await self.seteventannouncement(ctx, message=message)

    @eventchannels.command(name="setstartmessage")
    async def setstartmessage(self, ctx, *, message: str):
        """Wrapper for seteventstartmessage from CommandsConfigMixin."""
        await self.seteventstartmessage(ctx, message=message)

    @eventchannels.command(name="setdeletionwarning")
    async def setdeletionwarning_cmd(self, ctx, *, message: str):
        """Wrapper for setdeletionwarning from CommandsConfigMixin."""
        await self.setdeletionwarning(ctx, message=message)

    @eventchannels.command(name="setdivider")
    async def setdivider(self, ctx, enabled: bool, *, divider_name: str = None):
        """Wrapper for seteventdivider from CommandsConfigMixin."""
        await self.seteventdivider(ctx, enabled, divider_name=divider_name)

    @eventchannels.command(name="linkthread")
    async def linkthread(self, ctx, thread: discord.Thread, event_id: str):
        """Wrapper for linkthreadtoevent from CommandsConfigMixin."""
        await self.linkthreadtoevent(ctx, thread, event_id)

    # ---------- View Commands ----------

    @eventchannels.command(name="viewsettings")
    async def viewsettings(self, ctx):
        """Wrapper for vieweventsettings from CommandsViewMixin."""
        await self.vieweventsettings(ctx)

    @eventchannels.command(name="listvoicemultipliers")
    async def listvoicemultipliers_cmd(self, ctx):
        """Wrapper for listvoicemultipliers from CommandsViewMixin."""
        await self.listvoicemultipliers(ctx)

    @eventchannels.command(name="listminimumroles")
    async def listminimumroles_cmd(self, ctx):
        """Wrapper for listminimumroles from CommandsViewMixin."""
        await self.listminimumroles(ctx)

    @eventchannels.command(name="listwhitelistedroles")
    async def listwhitelistedroles_cmd(self, ctx):
        """Wrapper for listwhitelistedroles from CommandsViewMixin."""
        await self.listwhitelistedroles(ctx)

    # ---------- Test Commands ----------

    @eventchannels.command(name="testchannellock")
    async def testchannellock_cmd(self, ctx):
        """Wrapper for testchannellock from CommandsTestMixin."""
        await self.testchannellock(ctx)

    @eventchannels.command(name="testeventroles")
    async def testeventroles_cmd(self, ctx, role: discord.Role = None):
        """Wrapper for testeventroles from CommandsTestMixin."""
        await self.testeventroles(ctx, role)

    @eventchannels.command(name="stresstest")
    async def stresstest_cmd(self, ctx):
        """Wrapper for stresstest from CommandsTestMixin."""
        await self.stresstest(ctx)

    # ---------- Cog Lifecycle ----------

    def cog_unload(self):
        """Cancel all active tasks when cog is unloaded."""
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()
