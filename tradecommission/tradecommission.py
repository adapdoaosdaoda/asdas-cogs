"""Trade Commission weekly message cog for Where Winds Meet."""
import asyncio
import discord
from typing import Optional
from redbot.core import commands, Config
from redbot.core.bot import Red

# Import all mixins
from .utils import UtilsMixin
from .scheduling import SchedulingMixin
from .commands_config import CommandsConfigMixin
from .commands_options import CommandsOptionsMixin
from .commands_schedule import CommandsScheduleMixin
from .commands_actions import CommandsActionsMixin


class TradeCommission(
    UtilsMixin,
    SchedulingMixin,
    CommandsConfigMixin,
    CommandsOptionsMixin,
    CommandsScheduleMixin,
    CommandsActionsMixin,
    commands.Cog
):
    """Send weekly Trade Commission information for Where Winds Meet."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571751,
            force_registration=True,
        )
        # Global config - shared across all guilds
        default_global = {
            "trade_options": [],  # List of options: [{"emoji": "🔥", "title": "...", "description": "..."}, ...]
            "image_url": None,  # Image to display when information is added
            "emoji_titles": {},  # Custom titles for emoji groups: {"🔥": "Fire Routes", ...}
        }

        # Per-guild config - only for addinfo tracking
        default_guild = {
            "channel_id": None,
            "schedule_day": 0,  # 0 = Monday, 6 = Sunday
            "schedule_hour": 9,  # Hour in 24h format
            "schedule_minute": 0,
            "timezone": "UTC",
            "enabled": False,
            "current_message_id": None,
            "current_channel_id": None,
            "active_options": [],  # List of option indices that are currently active (max 3)
            "addinfo_message_id": None,  # The addinfo control message
            "allowed_roles": [],  # Role IDs that can use addinfo reactions
            "allowed_users": [],  # User IDs that can use addinfo reactions
            "message_title": "📊 Weekly Trade Commission - Where Winds Meet",  # Configurable header
            "initial_description": "This week's Trade Commission information will be added soon!\n\nCheck back later for updates.",  # Before addinfo
            "post_description": "This week's Trade Commission information:",  # After addinfo
            "ping_role_id": None,  # Role to ping when posting message
            "previous_message_id": None,  # Previous week's message to delete
            "notification_message": "📢 All 3 trade commission options have been selected! Check them out above!",  # Message sent when 3 options selected
            "notification_message_id": None,  # ID of notification message to delete after 3 hours

            # Sunday pre-shop restock notification
            "sunday_enabled": False,
            "sunday_hour": 19,
            "sunday_minute": 0,
            "sunday_message": "🔔 **Pre-Shop Restock Reminder!**\n\nThe shop will be restocking soon! Get ready!",
            "sunday_ping_role_id": None,

            # Wednesday sell recommendation notification
            "wednesday_enabled": False,
            "wednesday_hour": 19,
            "wednesday_minute": 0,
            "wednesday_message": "📈 **Recommended to Sell Now!**\n\nIt's Wednesday! Check your prices and consider selling!",
            "wednesday_ping_role_id": None,
        }

        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self._task = None
        self._ready = False

    async def cog_load(self):
        """Start the background task when cog loads."""
        await self.bot.wait_until_red_ready()
        self._ready = True
        self._task = asyncio.create_task(self._check_schedule_loop())

    async def cog_unload(self):
        """Cancel background task when cog unloads."""
        if self._task:
            self._task.cancel()

    @commands.group(name="tradecommission", aliases=["tc"])
    async def tradecommission(self, ctx: commands.Context):
        """
        Manage Trade Commission weekly messages.

        Global config commands (setoption, setimage) can be used in DMs by the bot owner.
        Server-specific commands require being used in a server with admin permissions.
        """
        pass

    # ==================== Configuration Commands ====================
    # These are wrappers that delegate to the mixin methods

    @tradecommission.command(name="schedule")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _schedule(self, ctx, channel: discord.TextChannel, day: str, hour: int, minute: int = 0, timezone: str = "UTC"):
        """Schedule weekly Trade Commission messages."""
        await self.tc_schedule(ctx, channel, day, hour, minute, timezone)

    @tradecommission.command(name="disable")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _disable(self, ctx):
        """Disable weekly Trade Commission messages."""
        await self.tc_disable(ctx)

    @tradecommission.command(name="enable")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _enable(self, ctx):
        """Enable weekly Trade Commission messages."""
        await self.tc_enable(ctx)

    @tradecommission.command(name="addrole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _addrole(self, ctx, role: discord.Role):
        """Add a role that can use addinfo reactions."""
        await self.tc_addrole(ctx, role)

    @tradecommission.command(name="removerole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _removerole(self, ctx, role: discord.Role):
        """Remove a role from the addinfo allowed list."""
        await self.tc_removerole(ctx, role)

    @tradecommission.command(name="listroles")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _listroles(self, ctx):
        """List all roles that can use addinfo reactions."""
        await self.tc_listroles(ctx)

    @tradecommission.command(name="adduser")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _adduser(self, ctx, user: discord.Member):
        """Add a user that can use addinfo reactions."""
        await self.tc_adduser(ctx, user)

    @tradecommission.command(name="removeuser")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _removeuser(self, ctx, user: discord.Member):
        """Remove a user from the addinfo allowed list."""
        await self.tc_removeuser(ctx, user)

    @tradecommission.command(name="listusers")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _listusers(self, ctx):
        """List all users that can use addinfo reactions."""
        await self.tc_listusers(ctx)

    @tradecommission.command(name="settitle")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _settitle(self, ctx, *, title: str):
        """Set the title/header for Trade Commission messages."""
        await self.tc_settitle(ctx, title=title)

    @tradecommission.command(name="setinitial")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _setinitial(self, ctx, *, description: str):
        """Set the initial description shown before options are added."""
        await self.tc_setinitial(ctx, description=description)

    @tradecommission.command(name="setpost")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _setpost(self, ctx, *, description: str):
        """Set the description shown after options are added."""
        await self.tc_setpost(ctx, description=description)

    @tradecommission.command(name="setpingrole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _setpingrole(self, ctx, role: Optional[discord.Role] = None):
        """Set a role to ping when posting Trade Commission messages."""
        await self.tc_setpingrole(ctx, role)

    @tradecommission.command(name="setnotification")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _setnotification(self, ctx, *, message: str):
        """Set the notification message sent when all 3 options are selected."""
        await self.tc_setnotification(ctx, message=message)

    # ==================== Option Management Commands ====================

    @tradecommission.command(name="setoption")
    async def _setoption(self, ctx, emoji: str, title: str, *, description: str):
        """Configure an option's information (Global Setting)."""
        await self.tc_setoption(ctx, emoji, title, description=description)

    @tradecommission.command(name="removeoption")
    async def _removeoption(self, ctx, *, title: str):
        """Remove an option by its title (Global Setting)."""
        await self.tc_removeoption(ctx, title=title)

    @tradecommission.command(name="listoptions")
    async def _listoptions(self, ctx):
        """List all configured trade options (Global Setting)."""
        await self.tc_listoptions(ctx)

    @tradecommission.command(name="setimage")
    @commands.is_owner()
    async def _setimage(self, ctx, image_url: Optional[str] = None):
        """Set the image to display in Trade Commission messages (Global Setting)."""
        await self.tc_setimage(ctx, image_url)

    @tradecommission.command(name="setgrouptitle")
    async def _setgrouptitle(self, ctx, emoji: str, *, title: str):
        """Set a custom title for an emoji-grouped option category (Global Setting)."""
        await self.tc_setgrouptitle(ctx, emoji, title=title)

    @tradecommission.command(name="removegrouptitle")
    async def _removegrouptitle(self, ctx, emoji: str):
        """Remove a custom title for an emoji-grouped option category (Global Setting)."""
        await self.tc_removegrouptitle(ctx, emoji)

    @tradecommission.command(name="listgrouptitles")
    async def _listgrouptitles(self, ctx):
        """List all custom emoji group titles (Global Setting)."""
        await self.tc_listgrouptitles(ctx)

    # ==================== Action Commands ====================

    @tradecommission.command(name="post")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _post(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Manually post a Trade Commission message now."""
        await self.tc_post(ctx, channel)

    @tradecommission.command(name="addinfo")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _addinfo(self, ctx):
        """Add information to the current week's Trade Commission message via buttons."""
        await self.tc_addinfo(ctx)

    @tradecommission.command(name="info")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _info(self, ctx):
        """Show current Trade Commission configuration."""
        await self.tc_info(ctx)

    @tradecommission.command(name="testnow")
    @commands.guild_only()
    @commands.is_owner()
    async def _testnow(self, ctx):
        """[Owner only] Test sending the weekly message immediately."""
        await self.tc_testnow(ctx)

    # ==================== Sunday Schedule Commands ====================

    @tradecommission.group(name="sunday")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _sunday(self, ctx):
        """Configure Sunday pre-shop restock notifications."""
        await self.tc_sunday(ctx)

    @_sunday.command(name="enable")
    async def _sunday_enable(self, ctx):
        """Enable Sunday pre-shop restock notifications."""
        await self.sunday_enable(ctx)

    @_sunday.command(name="disable")
    async def _sunday_disable(self, ctx):
        """Disable Sunday pre-shop restock notifications."""
        await self.sunday_disable(ctx)

    @_sunday.command(name="time")
    async def _sunday_time(self, ctx, hour: int, minute: int = 0):
        """Set the time for Sunday notifications."""
        await self.sunday_time(ctx, hour, minute)

    @_sunday.command(name="message")
    async def _sunday_message(self, ctx, *, message: str):
        """Set the message for Sunday notifications."""
        await self.sunday_message(ctx, message=message)

    @_sunday.command(name="pingrole")
    async def _sunday_pingrole(self, ctx, role: Optional[discord.Role] = None):
        """Set a role to ping with Sunday notifications."""
        await self.sunday_pingrole(ctx, role)

    @_sunday.command(name="test")
    async def _sunday_test(self, ctx):
        """Test the Sunday notification by sending it immediately."""
        await self.sunday_test(ctx)

    # ==================== Wednesday Schedule Commands ====================

    @tradecommission.group(name="wednesday")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def _wednesday(self, ctx):
        """Configure Wednesday sell recommendation notifications."""
        await self.tc_wednesday(ctx)

    @_wednesday.command(name="enable")
    async def _wednesday_enable(self, ctx):
        """Enable Wednesday sell recommendation notifications."""
        await self.wednesday_enable(ctx)

    @_wednesday.command(name="disable")
    async def _wednesday_disable(self, ctx):
        """Disable Wednesday sell recommendation notifications."""
        await self.wednesday_disable(ctx)

    @_wednesday.command(name="time")
    async def _wednesday_time(self, ctx, hour: int, minute: int = 0):
        """Set the time for Wednesday notifications."""
        await self.wednesday_time(ctx, hour, minute)

    @_wednesday.command(name="message")
    async def _wednesday_message(self, ctx, *, message: str):
        """Set the message for Wednesday notifications."""
        await self.wednesday_message(ctx, message=message)

    @_wednesday.command(name="pingrole")
    async def _wednesday_pingrole(self, ctx, role: Optional[discord.Role] = None):
        """Set a role to ping with Wednesday notifications."""
        await self.wednesday_pingrole(ctx, role)

    @_wednesday.command(name="test")
    async def _wednesday_test(self, ctx):
        """Test the Wednesday notification by sending it immediately."""
        await self.wednesday_test(ctx)
