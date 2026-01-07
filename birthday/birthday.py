from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

import discord
from redbot.core import commands, data_manager
from redbot.core.bot import Red
from redbot.core.config import Config

from .abc import CompositeMetaClass
from .commands import BirthdayAdminCommands, BirthdayCommands
from .loop import BirthdayLoop
from .vexutils import format_help, format_info, get_vex_logger
from .vexutils.loop import VexLoop

log = get_vex_logger(__name__)


class Birthday(
    commands.Cog,
    BirthdayLoop,
    BirthdayCommands,
    BirthdayAdminCommands,
    metaclass=CompositeMetaClass,
):
    """
    Birthdays

    Set yours and get a message and role on your birthday!
    """

    __version__ = "1.4.0"
    __author__ = "@vexingvexed"

    def __init__(self, bot: Red) -> None:
        self.bot = bot

        self.config: Config = Config.get_conf(self, 418078199982063626, force_registration=True)
        self.config.register_global(version=0)
        self.config.register_guild(
            time_utc_s=None,  # deprecated, kept for migration
            role_time_utc_s=None,
            message_time_utc_s=None,
            message_w_year=None,
            message_wo_year=None,
            channel_id=None,
            role_id=None,
            setup_state=0,  # 0 is not setup, 5 is everything setup. this is so it can be steadily
            # incremented with individual setup commands or with the interactive setup, then
            # easily checked
            require_role=False,  # deprecated, kept for migration
            required_roles=[],  # list of role IDs, user needs at least one
            allow_role_mention=False,
            set_channel_id=None,  # channel where users can set their birthday
            image_url=None,  # deprecated, kept for migration
            image_path=None,  # local path to birthday image
            announcement_reaction=None,  # deprecated, kept for migration
            announcement_reactions=[],  # list of emojis to react to announcement messages with
            announced_today=[],  # list of user IDs who received messages today
        )
        self.config.register_member(birthday={"year": 1, "month": 1, "day": 1})  # deprecated, kept for migration
        self.config.register_user(birthday={"year": 1, "month": 1, "day": 1})

        # Set up data directory for storing images
        self.data_path = data_manager.cog_data_path(self)
        self.images_path = self.data_path / "images"
        self.images_path.mkdir(parents=True, exist_ok=True)

        self.loop_meta = VexLoop("Birthday loop", 60 * 60)
        self.loop = self.bot.loop.create_task(self.birthday_loop())
        self.role_manager = self.bot.loop.create_task(self.birthday_role_manager())
        self.coro_queue = asyncio.Queue()

        self.ready = asyncio.Event()

        bot.add_dev_env_value("birthday", lambda _: self)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """Thanks Sinbad."""
        return format_help(self, ctx)

    async def cog_unload(self):
        self.loop.cancel()
        self.role_manager.cancel()

        try:
            self.bot.remove_dev_env_value("birthday")
        except KeyError:
            pass

    async def red_delete_data_for_user(self, **kwargs) -> None:
        # will delete for any requester
        target_u_id: int | None = kwargs.get("user_id")
        if target_u_id is None:
            log.info("Unable to delete user data for user with ID 0 because it's invalid.")
            return

        # Delete from new user config
        user_data = await self.config.user_from_id(target_u_id).birthday()
        if user_data:
            await self.config.user_from_id(target_u_id).clear()
            log.debug("Deleted user data for user with ID %s.", target_u_id)
        else:
            log.debug("No user data found for user with ID %s.", target_u_id)

    async def _set_bot_birthday(self) -> None:
        """Automatically set the bot's birthday to its creation date from Discord snowflake."""
        if self.bot.user is None:
            log.warning("Bot user not available, cannot set bot birthday")
            return

        bot_id = self.bot.user.id

        # Check if bot already has a birthday set
        bot_bday = await self.config.user_from_id(bot_id).birthday()
        if bot_bday and bot_bday.get("year") != 1:
            # Birthday already set with a year, don't override
            log.debug("Bot birthday already set, skipping auto-set")
            return

        # Calculate creation date from Discord snowflake
        # Discord epoch is January 1, 2015 00:00:00 UTC
        # Snowflake format: (timestamp << 22) | (worker_id << 17) | (process_id << 12) | increment
        discord_epoch = 1420070400000  # milliseconds
        timestamp_ms = (bot_id >> 22) + discord_epoch

        # Convert to datetime
        creation_date = datetime.datetime.utcfromtimestamp(timestamp_ms / 1000)

        # Set the bot's birthday
        await self.config.user_from_id(bot_id).birthday.set({
            "year": creation_date.year,
            "month": creation_date.month,
            "day": creation_date.day,
        })

        log.info(
            f"Automatically set bot birthday to {creation_date.year}-{creation_date.month:02d}-{creation_date.day:02d} "
            f"(bot creation date)"
        )

    async def cog_load(self) -> None:
        version = await self.config.version()
        if version == 0:  # first load so no need to update
            await self.config.version.set(3)
        elif version == 1:
            # Migrate from member-based to user-based storage
            log.info("Migrating birthday data from member-based to user-based storage...")
            all_members = await self.config.all_members()
            migrated_users = set()

            for guild_id, guild_data in all_members.items():
                for user_id, data in guild_data.items():
                    if user_id not in migrated_users and data.get("birthday"):
                        # Only migrate if user doesn't already have a global birthday set
                        user_bday = await self.config.user_from_id(user_id).birthday()
                        if not user_bday or user_bday.get("year") == 1:
                            await self.config.user_from_id(user_id).birthday.set(data["birthday"])
                        migrated_users.add(user_id)

            await self.config.version.set(3)
            log.info(f"Migrated {len(migrated_users)} user birthdays to global storage")
        elif version == 2:
            # Migrate from single time to separate role and message times
            log.info("Migrating from single time to separate role and message times...")
            all_guilds = await self.config.all_guilds()
            migrated_guilds = 0

            for guild_id, guild_data in all_guilds.items():
                old_time = guild_data.get("time_utc_s")
                if old_time is not None:
                    # Set both role and message times to the old time
                    await self.config.guild_from_id(guild_id).role_time_utc_s.set(old_time)
                    await self.config.guild_from_id(guild_id).message_time_utc_s.set(old_time)
                    # Update setup state from 5 to 7
                    if guild_data.get("setup_state") == 5:
                        await self.config.guild_from_id(guild_id).setup_state.set(7)
                    migrated_guilds += 1

            await self.config.version.set(3)
            log.info(f"Migrated {migrated_guilds} guilds to separate time configuration")

        # Automatically set the bot's birthday to its creation date
        await self._set_bot_birthday()

        self.ready.set()

        log.trace("birthday ready")

    @commands.command(hidden=True, aliases=["birthdayinfo"])
    async def bdayinfo(self, ctx: commands.Context):
        if ctx.guild:
            setup_state_detail, setup_state_brief = await self.setup_check_detail(ctx.guild, ctx)
        else:
            setup_state_detail, setup_state_brief = (
                {},
                "Run this command in a server to check for setup details",
            )
        await ctx.send(
            await format_info(
                ctx, self.qualified_name, self.__version__, extras=setup_state_detail
            )
            + "\n"
            + setup_state_brief
        )

    async def check_if_setup(self, guild: discord.Guild) -> bool:
        state = await self.config.guild(guild).setup_state()
        log.trace("setup state: %s", state)
        return state == 7  # Updated from 5 to 7 to account for two separate time settings

    async def setup_check_detail(
        self, guild: discord.Guild, ctx: commands.Context | None = None
    ) -> tuple[dict[str, str], str]:
        state = await self.config.guild(guild).setup_state()
        if state == 7:
            return {
                "Message with year": "Set",
                "Message without year": "Set",
                "Message channel": "Set",
                "Role ID": "Set",
                "Role time": "Set",
                "Message time": "Set",
            }, "Initial setup has been completed"
        else:
            if ctx:
                p = ctx.clean_prefix
            else:
                p = "[p]"
            state = {
                "Message with year": "Set",
                "Message without year": "Set",
                "Message channel": "Set",
                "Role ID": "Set",
                "Role time": "Set",
                "Message time": "Set",
            }
            if await self.config.guild(guild).role_time_utc_s() is None:
                state["Role time"] = f"Not set. Use `{p}bdset roletime`"
            if await self.config.guild(guild).message_time_utc_s() is None:
                state["Message time"] = f"Not set. Use `{p}bdset messagetime`"
            if await self.config.guild(guild).message_w_year() is None:
                state["Message with year"] = f"Not set. Use `{p}bdset msgwithyear`"
            if await self.config.guild(guild).message_wo_year() is None:
                state["Message without year"] = f"Not set. Use `{p}bdset msgwithoutyear`"
            if await self.config.guild(guild).channel_id() is None:
                state["Message channel"] = f"Not set. Use `{p}bdset channel`"
            if await self.config.guild(guild).role_id() is None:
                state["Role ID"] = f"Not set. Use `{p}bdset role`"
            return state, "Initial setup is not yet complete, so the cog won't work."
