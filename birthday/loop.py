from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, NoReturn

import discord
from redbot.core import commands
from redbot.core.utils import AsyncIter

from .abc import MixinMeta
from .utils import channel_perm_check, format_bday_message, role_perm_check
from .vexutils import get_vex_logger

log = get_vex_logger(__name__)


class BirthdayLoop(MixinMeta):
    @commands.command(hidden=True)
    @commands.is_owner()
    async def bdloopdebug(self, ctx: commands.Context) -> None:
        """
        Sends the current state of the Birthday loop.
        """
        await ctx.send(embed=self.loop_meta.get_debug_embed())

    async def birthday_role_manager(self) -> None:
        """Birthday role manager to handle coros, so they don't slow
        down the main loop. Remember d.py handles ratelimits."""
        while True:
            try:
                coro = await self.coro_queue.get()
                await coro
                log.trace("ran coro %s", coro)
            except discord.HTTPException as e:
                log.warning("A queued coro failed to run.", exc_info=e)

        # just using one task for all guilds is okay. maybe it's not the fastest as no async-ness
        # to get them doe faster as (some) rate limits are per-guild
        # but it's fine for now and the loop is hourly

    async def add_role(self, me: discord.Member, member: discord.Member, role: discord.Role):
        if error := role_perm_check(me, role):
            log.warning(
                "Not adding role %s to %s in guild %s because %s",
                role.id,
                member.id,
                member.guild.id,
                error,
            )
            return
        log.trace("Queued birthday role add for %s in guild %s", member.id, member.guild.id)
        self.coro_queue.put_nowait(
            member.add_roles(role, reason="Birthday cog - birthday starts today")
        )

    async def remove_role(self, me: discord.Member, member: discord.Member, role: discord.Role):
        if error := role_perm_check(me, role):
            log.warning(
                "Not removing role to %s in guild %s because %s",
                member.id,
                member.guild.id,
                error,
            )
            return
        log.trace("Queued birthday role remove for %s in guild %s", member.id, member.guild.id)
        self.coro_queue.put_nowait(
            member.remove_roles(role, reason="Birthday cog - birthday ends today")
        )

    async def send_announcement(
        self, channel: discord.TextChannel, message: str, role_mention: bool, image_path: str | None = None, reactions: list[str] | None = None
    ):
        if error := channel_perm_check(channel.guild.me, channel):
            log.warning(
                "Not sending announcement to %s in guild %s because %s",
                channel.id,
                channel.guild.id,
                error,
            )
            return

        log.trace("Queued birthday announcement for %s in guild %s", channel.id, channel.guild.id)
        log.trace("Message: %s", message)

        async def send_and_react():
            try:
                # Prepare image file if exists
                file = None
                if image_path and Path(image_path).exists():
                    file = discord.File(image_path, filename=Path(image_path).name)

                sent_message = await channel.send(
                    message,
                    file=file,
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, roles=role_mention, users=True
                    ),
                )

                if reactions:
                    for reaction in reactions:
                        try:
                            await sent_message.add_reaction(reaction)
                        except discord.HTTPException as e:
                            log.warning(
                                "Failed to add reaction %s to announcement in guild %s: %s",
                                reaction,
                                channel.guild.id,
                                e,
                            )
            except discord.Forbidden as e:
                log.warning(
                    "Missing permissions to send birthday announcement in channel %s (guild %s). "
                    "Please ensure the bot has Send Messages, Attach Files, and Add Reactions permissions.",
                    channel.id,
                    channel.guild.id,
                )
            except discord.HTTPException as e:
                log.warning(
                    "Failed to send birthday announcement in channel %s (guild %s): %s",
                    channel.id,
                    channel.guild.id,
                    e,
                )

        self.coro_queue.put_nowait(send_and_react())

    async def birthday_loop(self) -> NoReturn:
        """The Birthday loop. This coro will run forever."""
        await self.bot.wait_until_red_ready()
        await self.ready.wait()

        log.verbose("Birthday task started")

        # 1st loop
        try:
            self.loop_meta.iter_start()
            await self._update_birthdays()
            self.loop_meta.iter_finish()
            log.verbose("Initial loop has finished")
        except Exception as e:
            self.loop_meta.iter_error(e)
            log.exception(
                "Something went wrong in the Birthday loop. The loop will try again in an hour."
                "Please report this and the below information to Vexed.",
                exc_info=e,
            )

        # both iter_finish and iter_error set next_iter as not None
        assert self.loop_meta.next_iter is not None
        self.loop_meta.next_iter = self.loop_meta.next_iter.replace(
            minute=0
        )  # ensure further iterations are on the hour

        await self.loop_meta.sleep_until_next()

        # all further iterations
        while True:
            log.verbose("Loop has started next iteration")
            try:
                self.loop_meta.iter_start()
                await self._update_birthdays()
                self.loop_meta.iter_finish()
                log.verbose("Loop has finished")
            except Exception as e:
                self.loop_meta.iter_error(e)
                log.exception(
                    "Something went wrong in the Birthday loop. The loop will try again "
                    "in an hour. Please report this and the below information to Vexed.",
                    exc_info=e,
                )

            await self.loop_meta.sleep_until_next()

    async def _update_birthdays(self):
        """Update birthdays - handle roles and messages at different times"""
        all_birthdays: dict[int, dict[str, Any]] = await self.config.all_users()
        all_settings: dict[int, dict[str, Any]] = await self.config.all_guilds()

        async for guild_id, guild_settings in AsyncIter(all_settings.items(), steps=5):
            guild: discord.Guild | None = self.bot.get_guild(int(guild_id))
            if guild is None:
                log.trace("Guild %s is not in cache, skipping", guild_id)
                continue

            if await self.check_if_setup(guild) is False:
                log.trace("Guild %s is not setup, skipping", guild_id)
                continue

            # Get the separate times for roles and messages
            role_time_utc_s = guild_settings.get("role_time_utc_s")
            message_time_utc_s = guild_settings.get("message_time_utc_s")

            # Migrate old time_utc_s if needed
            old_time = guild_settings.get("time_utc_s")
            if old_time is not None and (role_time_utc_s is None or message_time_utc_s is None):
                role_time_utc_s = old_time
                message_time_utc_s = old_time
                await self.config.guild(guild).role_time_utc_s.set(old_time)
                await self.config.guild(guild).message_time_utc_s.set(old_time)

            if role_time_utc_s is None or message_time_utc_s is None:
                log.trace("Guild %s doesn't have times configured, skipping", guild_id)
                continue

            role_hour_td = datetime.timedelta(seconds=role_time_utc_s)
            message_hour_td = datetime.timedelta(seconds=message_time_utc_s)

            since_midnight = datetime.datetime.utcnow().replace(
                minute=0, second=0, microsecond=0
            ) - datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            is_role_time = since_midnight.total_seconds() == role_hour_td.total_seconds()
            is_message_time = since_midnight.total_seconds() == message_hour_td.total_seconds()

            # Skip if it's neither role time nor message time
            if not is_role_time and not is_message_time:
                log.trace("Not role time or message time for guild %s, skipping", guild_id)
                continue

            # Use role time for determining "today"
            today_dt = (datetime.datetime.utcnow() - role_hour_td).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            start = today_dt + role_hour_td
            end = start + datetime.timedelta(days=1)

            # Get required roles (migrate from old config if needed)
            old_required_role = guild_settings.get("required_role")
            required_role_ids = guild_settings.get("required_roles", [])

            if old_required_role and not required_role_ids:
                # Migrate from old single role to new list format
                required_role_ids = [old_required_role]
                await self.config.guild(guild).required_roles.set(required_role_ids)
                await self.config.guild(guild).require_role.clear()

            # Get role objects
            required_roles = []
            for role_id in required_role_ids:
                role = guild.get_role(role_id)
                if role:
                    required_roles.append(role)

            birthday_members: dict[discord.Member, datetime.datetime] = {}

            # Iterate through all users and check if they're in this guild
            async for user_id, user_data in AsyncIter(all_birthdays.items(), steps=50):
                birthday = user_data.get("birthday")
                if not birthday:  # birthday not set
                    continue
                member = guild.get_member(int(user_id))
                if member is None:
                    # User not in this guild, skip
                    continue

                proper_bday_dt = datetime.datetime(
                    year=birthday["year"] or 1, month=birthday["month"], day=birthday["day"]
                )
                this_year_bday_dt = proper_bday_dt.replace(year=today_dt.year) + role_hour_td

                # Check if member has at least one required role (if any are set)
                if required_roles and not any(role in member.roles for role in required_roles):
                    log.trace(
                        "Member %s for guild %s does not have required role, skipping",
                        user_id,
                        guild_id,
                    )
                    continue

                if start <= this_year_bday_dt < end:  # birthday is today
                    birthday_members[member] = proper_bday_dt

            role = guild.get_role(guild_settings["role_id"])
            if role is None:
                log.warning(
                    "Role %s for guild %s (%s) was not found",
                    guild_settings["role_id"],
                    guild_id,
                    guild.name,
                )
                continue

            log.trace("Members with birthdays in guild %s: %s", guild_id, birthday_members)

            # Handle role assignments/removals at role time
            if is_role_time:
                log.trace("Processing role updates for guild %s", guild_id)
                for member, dt in birthday_members.items():
                    if member not in role.members:
                        await self.add_role(guild.me, member, role)

                for member in role.members:
                    if member not in birthday_members:
                        await self.remove_role(guild.me, member, role)

            # Handle message sending at message time
            if is_message_time:
                log.trace("Processing message updates for guild %s", guild_id)

                channel = guild.get_channel(guild_settings["channel_id"])
                if channel is None or not isinstance(channel, discord.TextChannel):
                    log.warning(
                        "Channel %s for guild %s (%s) was not found",
                        guild_settings["channel_id"],
                        guild_id,
                        guild.name,
                    )
                    continue

                # Get image path and announcement reactions for announcements
                image_path = guild_settings.get("image_path")

                # Migrate from old single reaction to new list format
                old_reaction = guild_settings.get("announcement_reaction")
                announcement_reactions = guild_settings.get("announcement_reactions", [])

                if old_reaction and not announcement_reactions:
                    announcement_reactions = [old_reaction]
                    await self.config.guild(guild).announcement_reactions.set(announcement_reactions)
                    await self.config.guild(guild).announcement_reaction.clear()

                # Get list of users who already received messages today
                announced_today = guild_settings.get("announced_today", [])

                # Clear announced_today list if it's midnight UTC (start of new day)
                current_hour = datetime.datetime.utcnow().hour
                if current_hour == 0:
                    announced_today = []
                    await self.config.guild(guild).announced_today.set([])

                for member, dt in birthday_members.items():
                    # Skip if already announced today
                    if member.id in announced_today:
                        log.trace("Member %s already announced today in guild %s, skipping", member.id, guild_id)
                        continue

                    if dt.year == 1:
                        await self.send_announcement(
                            channel,
                            format_bday_message(guild_settings["message_wo_year"], member),
                            guild_settings["allow_role_mention"],
                            image_path,
                            announcement_reactions,
                        )
                    else:
                        age = today_dt.year - dt.year
                        await self.send_announcement(
                            channel,
                            format_bday_message(
                                guild_settings["message_w_year"], member, age
                            ),
                            guild_settings["allow_role_mention"],
                            image_path,
                            announcement_reactions,
                        )

                    # Mark this member as announced today
                    announced_today.append(member.id)

                # Save the updated announced_today list
                await self.config.guild(guild).announced_today.set(announced_today)

            log.trace("Potential updates for %s have been queued", guild_id)
