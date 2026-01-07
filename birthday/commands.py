from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Union

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.commands import CheckFailure
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import box, pagify, warning
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate
from rich.table import Table  # type:ignore

from .abc import MixinMeta
from .components.paged_embed import PaginatedEmbedView
from .components.setup import SetupView
from .consts import MAX_BDAY_MSG_LEN
from .converters import BirthdayConverter, TimeConverter
from .utils import channel_perm_check, format_bday_message, role_perm_check
from .vexutils import get_vex_logger, no_colour_rich_markup
from .vexutils.button_pred import wait_for_yes_no

log = get_vex_logger(__name__)


class BirthdayCommands(MixinMeta):
    async def setup_check(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            raise CheckFailure("This command can only be used in a server.")
            # this should have been caught by guild only check, but this keeps type checker happy
            # and idk what order decos run in so

        if not await self.check_if_setup(ctx.guild):
            await ctx.send(
                "This command is not available until the cog has been setup. "
                f"Get an admin to use `{ctx.clean_prefix}bdset interactive` to get started "
                f"or check what's missing with `{ctx.clean_prefix}birthdayinfo`."
            )
            raise CheckFailure("cog needs setup")

    @commands.hybrid_group(aliases=["bday"])
    async def birthday(self, ctx: commands.Context):
        """Set and manage your birthday."""

    @birthday.command(aliases=["add"])
    async def set(self, ctx: commands.Context, *, birthday: BirthdayConverter):
        """
        Set your birthday.

        Only the month and day are stored - birth years are not supported.

        If you use a date in the format xx/xx or xx-xx, MM-DD is assumed.

        This command works in DMs or in servers.

        **Examples:**
        - `[p]bday set 24th September`
        - `[p]bday set 24th Sept`
        - `[p]bday set 9/24`
        - `[p]bday set 9-24`
        """
        # Check if there's a channel restriction (only in guilds)
        if ctx.guild:
            set_channel_id = await self.config.guild(ctx.guild).set_channel_id()
            if set_channel_id is not None and ctx.channel.id != set_channel_id:
                set_channel = ctx.guild.get_channel(set_channel_id)
                if set_channel:
                    await ctx.send(
                        f"You can only set your birthday in {set_channel.mention}.",
                        ephemeral=True
                    )
                else:
                    await ctx.send(
                        "You can only set your birthday in a specific channel, but that channel "
                        "no longer exists. Please contact an admin.",
                        ephemeral=True
                    )
                return

        # Store birthday without year
        async with self.config.user(ctx.author).birthday() as bday:
            bday["year"] = None
            bday["month"] = birthday.month
            bday["day"] = birthday.day

        try:
            await ctx.message.add_reaction("✅")
        except discord.HTTPException:
            # Fallback to text message if reaction fails
            await ctx.send("✅ Your birthday has been set!")

    @birthday.command(aliases=["delete", "del"])
    async def remove(self, ctx: commands.Context):
        """Remove your birthday. This command works in DMs or in servers."""
        m = await ctx.send("Are you sure?")
        start_adding_reactions(m, ReactionPredicate.YES_OR_NO_EMOJIS)
        check = ReactionPredicate.yes_or_no(m, ctx.author)  # type:ignore

        try:
            await self.bot.wait_for("reaction_add", check=check, timeout=60)
        except asyncio.TimeoutError:
            for reaction in ReactionPredicate.YES_OR_NO_EMOJIS:
                if ctx.guild:
                    await m.remove_reaction(reaction, ctx.guild.me)
                else:
                    await m.remove_reaction(reaction, self.bot.user)
            return

        if check.result is False:
            await ctx.send("Cancelled.")
            return

        await self.config.user(ctx.author).birthday.set({})
        await ctx.send("Your birthday has been removed.")

    @commands.dm_only()  # type:ignore
    @birthday.command()
    async def show(self, ctx: commands.Context):
        """Show your birthday. This command only works in DMs."""
        birthday_data = await self.config.user(ctx.author).birthday()

        if not birthday_data or not birthday_data.get("month"):
            await ctx.send("You haven't set your birthday yet. Use `[p]birthday set` to set it.")
            return

        # Reconstruct the datetime from stored data
        birthday_dt = datetime.datetime(
            year=1,
            month=birthday_data["month"],
            day=birthday_data["day"],
        )

        # Format the birthday string (month and day only)
        formatted_date = birthday_dt.strftime("%B %d")
        await ctx.send(f"Your birthday is **{formatted_date}**.")

    @commands.guild_only()  # type:ignore
    @commands.before_invoke(setup_check)  # type:ignore
    @birthday.command()
    async def upcoming(self, ctx: commands.Context, days: int = 7):
        """View upcoming birthdays, defaults to 7 days.

        **Examples:**
        - `[p]birthday upcoming` - default of 7 days
        - `[p]birthday upcoming 14` - 14 days
        """
        # guild only check in decorator
        if TYPE_CHECKING:
            assert isinstance(ctx.author, discord.Member)
            assert ctx.guild is not None

        if days < 1 or days > 365:
            await ctx.send("You must enter a number of days greater than 0 and smaller than 365.")
            return

        today_dt = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        all_birthdays: dict[int, dict[str, dict]] = await self.config.all_users()

        log.trace("raw data for all bdays: %s", all_birthdays)

        parsed_bdays: dict[int, list[str]] = defaultdict(list)
        number_day_mapping: dict[int, str] = {}

        async for user_id, user_data in AsyncIter(all_birthdays.items(), steps=50):
            if not user_data.get("birthday"):  # birthday removed or not set
                continue
            member = ctx.guild.get_member(user_id)
            if not isinstance(member, discord.Member):
                continue

            birthday_dt = datetime.datetime(
                year=user_data["birthday"]["year"] or 1,
                month=user_data["birthday"]["month"],
                day=user_data["birthday"]["day"],
            )

            if today_dt.month == birthday_dt.month and today_dt.day == birthday_dt.day:
                parsed_bdays[0].append(member.mention)
                number_day_mapping[0] = "Today"
                continue

            this_year_bday = birthday_dt.replace(year=today_dt.year)
            next_year_bday = birthday_dt.replace(year=today_dt.year + 1)
            next_birthday_dt = this_year_bday if this_year_bday > today_dt else next_year_bday

            diff = next_birthday_dt - today_dt
            if diff.days > days:
                continue

            parsed_bdays[diff.days].append(member.mention)
            number_day_mapping[diff.days] = next_birthday_dt.strftime("%B %d")

        log.trace("bdays parsed: %s", parsed_bdays)

        if len(parsed_bdays) == 0:
            await ctx.send(f"No upcoming birthdays in the next {days} days.")
            return

        sorted_parsed_bdays = sorted(parsed_bdays.items(), key=lambda x: x[0])

        MAX_PER_PAGE = 25

        if len(sorted_parsed_bdays) < MAX_PER_PAGE:
            embed = discord.Embed(title="Upcoming Birthdays", colour=await ctx.embed_colour())
            for day, members in sorted_parsed_bdays:
                embed.add_field(name=number_day_mapping.get(day), value="\n".join(members))
            await ctx.send(embed=embed)
        else:
            pages = len(sorted_parsed_bdays) // MAX_PER_PAGE + (
                1 if len(sorted_parsed_bdays) % MAX_PER_PAGE > 0 else 0
            )
            embeds = []
            for i in range(pages):
                embed = discord.Embed(
                    title="Upcoming Birthdays",
                    description=f"Page {i + 1}/{pages}",
                    colour=await ctx.embed_colour(),
                )
                for day, members in sorted_parsed_bdays[i * MAX_PER_PAGE : (i + 1) * MAX_PER_PAGE]:
                    embed.add_field(name=number_day_mapping.get(day), value="\n".join(members))
                embeds.append(embed)

            view = PaginatedEmbedView(embeds, ctx.author.id)
            await ctx.send(embed=embeds[0], view=view)


class BirthdayAdminCommands(MixinMeta):
    @commands.guild_only()
    @commands.is_owner()
    @commands.group(hidden=True)
    async def birthdaydebug(self, ctx: commands.Context):
        """Birthday debug commands."""

    @birthdaydebug.command(name="upcoming")
    async def debug_upcoming(self, ctx: commands.Context):
        await ctx.send_interactive(
            pagify(str(await self.config.all_members(ctx.guild)), shorten_by=12), "py"
        )

    @commands.group()
    @commands.guild_only()  # type:ignore
    @commands.admin_or_permissions(manage_guild=True)
    async def bdset(self, ctx: commands.Context):
        """
        Birthday management commands for admins.

        Looking to set your own birthday? Use `[p]birthday set` or `[p]bday set`.
        """

    @commands.bot_has_permissions(manage_roles=True)
    @bdset.command()
    async def interactive(self, ctx: commands.Context):
        """Start interactive setup"""
        # guild only check in group
        if TYPE_CHECKING:
            assert isinstance(ctx.author, discord.Member)

        await ctx.send("Click below to start.", view=SetupView(ctx.author, self.bot, self.config))

    @bdset.command()
    async def settings(self, ctx: commands.Context):
        """View your current settings"""
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.me, discord.Member)

        table = Table("Name", "Value", title="Settings for this server")

        async with self.config.guild(ctx.guild).all() as conf:
            log.trace("raw config: %s", conf)

            channel = ctx.guild.get_channel(conf["channel_id"])
            table.add_row("Channel", channel.name if channel else "Channel deleted")

            role = ctx.guild.get_role(conf["role_id"])
            table.add_row("Role", role.name if role else "Role deleted")

            # Display role time
            role_time_s = conf.get("role_time_utc_s")
            if role_time_s is None:
                # Try old time field for migration
                old_time = conf.get("time_utc_s")
                if old_time is not None:
                    role_time = datetime.datetime.utcfromtimestamp(old_time).strftime("%H:%M UTC")
                else:
                    role_time = "Not set. Use `[p]bdset roletime`"
            else:
                role_time = datetime.datetime.utcfromtimestamp(role_time_s).strftime("%H:%M UTC")
            table.add_row("Role time", role_time)

            # Display message time
            message_time_s = conf.get("message_time_utc_s")
            if message_time_s is None:
                # Try old time field for migration
                old_time = conf.get("time_utc_s")
                if old_time is not None:
                    message_time = datetime.datetime.utcfromtimestamp(old_time).strftime("%H:%M UTC")
                else:
                    message_time = "Not set. Use `[p]bdset messagetime`"
            else:
                message_time = datetime.datetime.utcfromtimestamp(message_time_s).strftime("%H:%M UTC")
            table.add_row("Message time", message_time)

            table.add_row("Allow role mentions", str(conf["allow_role_mention"]))

            # Migrate old config if needed
            old_require_role = conf.get("require_role")
            required_roles = conf.get("required_roles", [])

            if old_require_role and not required_roles:
                # Migrate from old single role to new list format
                required_roles = [old_require_role]
                await self.config.guild(ctx.guild).required_roles.set(required_roles)
                await self.config.guild(ctx.guild).require_role.clear()

            if required_roles:
                role_names = []
                for role_id in required_roles:
                    role = ctx.guild.get_role(role_id)
                    if role:
                        role_names.append(role.name)

                if role_names:
                    if len(role_names) == 1:
                        table.add_row(
                            "Required role",
                            f"{role_names[0]}. Only users with this role can set their birthday and have it announced.",
                        )
                    else:
                        table.add_row(
                            "Required roles",
                            f"{', '.join(role_names)}. Users must have at least one of these roles to set their birthday and have it announced.",
                        )
                else:
                    table.add_row(
                        "Required role",
                        "Set, but all roles have been deleted. All users can set their birthday and have it announced.",
                    )
            else:
                table.add_row(
                    "Required role",
                    "Not set. All users can set their birthday and have it announced.",
                )

            set_channel = ctx.guild.get_channel(conf.get("set_channel_id"))
            if set_channel:
                table.add_row(
                    "Set channel restriction",
                    f"{set_channel.name}. Users can only set birthdays in this channel.",
                )
            else:
                table.add_row(
                    "Set channel restriction",
                    "Not set. Users can set their birthday in any channel.",
                )

            image_path = conf.get("image_path")
            if image_path and Path(image_path).exists():
                table.add_row("Announcement image", "Set")
            else:
                table.add_row("Announcement image", "Not set")

            # Migrate old config if needed
            old_reaction = conf.get("announcement_reaction")
            announcement_reactions = conf.get("announcement_reactions", [])

            if old_reaction and not announcement_reactions:
                announcement_reactions = [old_reaction]
                await self.config.guild(ctx.guild).announcement_reactions.set(announcement_reactions)
                await self.config.guild(ctx.guild).announcement_reaction.clear()

            if announcement_reactions:
                reactions_str = " ".join(announcement_reactions)
                if len(announcement_reactions) == 1:
                    table.add_row("Announcement reaction", reactions_str)
                else:
                    table.add_row("Announcement reactions", reactions_str)
            else:
                table.add_row("Announcement reactions", "Not set")

            message_w_year = conf["message_w_year"] or "No message set. You must set this before getting notifications."
            message_wo_year = conf["message_wo_year"] or "No message set. You must set this before getting notifications."

        warnings = "\n"
        if (error := role is None) or (error := role_perm_check(ctx.me, role)):
            if isinstance(error, bool):
                error = "Role deleted."
            warnings += warning(error + " This may result in repeated notifications.\n")
        if (error := channel is None) or (error := channel_perm_check(ctx.me, channel)):
            if isinstance(error, bool):
                error = "Channel deleted."
            warnings += warning(error + " You won't get birthday notifications.\n")

        final_table = no_colour_rich_markup(table)
        message = (
            final_table
            + "\nMessage with year:\n"
            + box(message_w_year)
            + "\nMessage without year:\n"
            + box(message_wo_year)
            + warnings
        )

        # Send message with pagination if it exceeds Discord's limit
        if len(message) > 2000:
            await ctx.send_interactive(pagify(message, page_length=1900))
        else:
            await ctx.send(message)

    @bdset.command()
    async def listall(self, ctx: commands.Context):
        """List all birthdays for members in this server."""
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        all_birthdays: dict[int, dict[str, dict]] = await self.config.all_users()

        members_with_birthdays = []

        async for user_id, user_data in AsyncIter(all_birthdays.items(), steps=50):
            if not user_data.get("birthday"):
                continue

            member = ctx.guild.get_member(user_id)
            if not isinstance(member, discord.Member):
                continue

            birthday_data = user_data["birthday"]
            birthday_dt = datetime.datetime(
                year=birthday_data["year"] or 1,
                month=birthday_data["month"],
                day=birthday_data["day"],
            )

            if birthday_data["year"]:
                date_str = birthday_dt.strftime("%B %d, %Y")
            else:
                date_str = birthday_dt.strftime("%B %d")

            members_with_birthdays.append((member.display_name, date_str, birthday_dt))

        if not members_with_birthdays:
            await ctx.send("No members in this server have set their birthdays.")
            return

        # Sort by month and day
        members_with_birthdays.sort(key=lambda x: (x[2].month, x[2].day))

        # Build the message
        lines = [f"**{name}**: {date}" for name, date, _ in members_with_birthdays]
        message = "\n".join(lines)

        # Send paginated if too long
        if len(message) > 2000:
            pages = []
            current_page = []
            current_length = 0

            for line in lines:
                if current_length + len(line) + 1 > 2000:
                    pages.append("\n".join(current_page))
                    current_page = [line]
                    current_length = len(line)
                else:
                    current_page.append(line)
                    current_length += len(line) + 1

            if current_page:
                pages.append("\n".join(current_page))

            for i, page in enumerate(pages, 1):
                await ctx.send(f"**Birthdays ({i}/{len(pages)})**\n{page}")
        else:
            await ctx.send(f"**Birthdays ({len(members_with_birthdays)} members)**\n{message}")

    @bdset.command()
    async def time(self, ctx: commands.Context, *, time: TimeConverter):
        """
        Set the time of day for both birthday messages and role updates.

        This sets both the role time and message time to the same value.
        To set them separately, use `[p]bdset roletime` and `[p]bdset messagetime`.

        Minutes are ignored.

        **Examples:**
        - `[p]bdset time 7:00` - set both times to 7:00AM UTC
        - `[p]bdset time 12AM` - set both times to midnight UTC
        - `[p]bdset time 3PM` - set both times to 3:00PM UTC
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        midnight = datetime.datetime.utcnow().replace(
            year=1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

        time_utc_s = int((time - midnight).total_seconds())

        async with self.config.guild(ctx.guild).all() as conf:
            old_role = conf.get("role_time_utc_s")
            old_message = conf.get("message_time_utc_s")

            conf["role_time_utc_s"] = time_utc_s
            conf["message_time_utc_s"] = time_utc_s

            # Increment setup state if either was None
            if old_role is None:
                conf["setup_state"] += 1
            if old_message is None:
                conf["setup_state"] += 1

        await ctx.send(
            f"Time set! I'll send birthday messages and update birthday roles at"
            f" {time.strftime('%H:%M')} UTC.\n\n"
            f"To set different times for roles and messages, use `{ctx.clean_prefix}bdset roletime` "
            f"and `{ctx.clean_prefix}bdset messagetime`."
        )

    @bdset.command()
    async def roletime(self, ctx: commands.Context, *, time: TimeConverter):
        """
        Set the time of day for birthday role updates.

        The birthday role will be assigned/removed at this time.

        Minutes are ignored.

        **Examples:**
        - `[p]bdset roletime 0:00` - set role time to midnight UTC
        - `[p]bdset roletime 6AM` - set role time to 6:00AM UTC
        - `[p]bdset roletime 12PM` - set role time to noon UTC
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        midnight = datetime.datetime.utcnow().replace(
            year=1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

        time_utc_s = int((time - midnight).total_seconds())

        async with self.config.guild(ctx.guild).all() as conf:
            old = conf.get("role_time_utc_s")
            conf["role_time_utc_s"] = time_utc_s

            if old is None:
                conf["setup_state"] += 1

        await ctx.send(
            f"Role time set! I'll update birthday roles at {time.strftime('%H:%M')} UTC."
        )

    @bdset.command()
    async def messagetime(self, ctx: commands.Context, *, time: TimeConverter):
        """
        Set the time of day for birthday message announcements.

        Birthday messages will be sent at this time.

        Minutes are ignored.

        **Examples:**
        - `[p]bdset messagetime 9:00` - set message time to 9:00AM UTC
        - `[p]bdset messagetime 12PM` - set message time to noon UTC
        - `[p]bdset messagetime 6PM` - set message time to 6:00PM UTC
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        midnight = datetime.datetime.utcnow().replace(
            year=1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

        time_utc_s = int((time - midnight).total_seconds())

        async with self.config.guild(ctx.guild).all() as conf:
            old = conf.get("message_time_utc_s")
            conf["message_time_utc_s"] = time_utc_s

            if old is None:
                conf["setup_state"] += 1

        await ctx.send(
            f"Message time set! I'll send birthday announcements at {time.strftime('%H:%M')} UTC."
        )

    @bdset.command()
    async def msgwithoutyear(self, ctx: commands.Context, *, message: str):
        """
        Set the message to send when the user did not provide a year.

        If you would like to mention a role, you will need to run `[p]bdset rolemention true`.

        **Placeholders:**
        - `{name}` - the user's name
        - `{mention}` - an @ mention of the user

            All the placeholders are optional.

        **Examples:**
        - `[p]bdset msgwithoutyear Happy birthday {mention}!`
        - `[p]bdset msgwithoutyear {mention}'s birthday is today! Happy birthday {name}.`
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.author, discord.Member)

        if len(message) > MAX_BDAY_MSG_LEN:
            await ctx.send(
                f"That message is too long! It needs to be under {MAX_BDAY_MSG_LEN} characters."
            )

        try:
            format_bday_message(message, ctx.author, 1)
        except KeyError as e:
            await ctx.send(
                f"You have a placeholder `{{{e.args[0]}}}` that is invalid. You can only include"
                " `{name}` and `{mention}` for the message without a year."
            )
            return

        async with self.config.guild(ctx.guild).all() as conf:
            if conf["message_wo_year"] is None:
                conf["setup_state"] += 1

            conf["message_wo_year"] = message

        await ctx.send("Message set. Here's how it will look:")
        await ctx.send(
            format_bday_message(message, ctx.author),
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @bdset.command()
    async def msgwithyear(self, ctx: commands.Context, *, message: str):
        """
        Set the message to send when the user did provide a year.

        If you would like to mention a role, you will need to run `[p]bdset rolemention true`

        **Placeholders:**
        - `{name}` - the user's name
        - `{mention}` - an @ mention of the user
        - `{new_age}` - the user's new age

            All the placeholders are optional.

        **Examples:**
        - `[p]bdset msgwithyear {mention} has turned {new_age}, happy birthday!`
        - `[p]bdset msgwithyear {name} is {new_age} today! Happy birthday {mention}!`
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.author, discord.Member)

        if len(message) > MAX_BDAY_MSG_LEN:
            await ctx.send(
                f"That message is too long! It needs to be under {MAX_BDAY_MSG_LEN} characters."
            )

        try:
            format_bday_message(message, ctx.author, 1)
        except KeyError as e:
            await ctx.send(
                f"You have a placeholder `{{{e.args[0]}}}` that is invalid. You can only include"
                " `{name}`, `{mention}` and `{new_age}` for the message with a year."
            )
            return

        async with self.config.guild(ctx.guild).all() as conf:
            if conf["message_w_year"] is None:
                conf["setup_state"] += 1

            conf["message_w_year"] = message

        await ctx.send("Message set. Here's how it will look, if you're turning 20:")
        await ctx.send(
            format_bday_message(message, ctx.author, 20),
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @bdset.command()
    async def channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the channel where the birthday message will be sent.

        **Example:**
        - `[p]bdset channel #birthdays` - set the channel to #birthdays
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.me, discord.Member)

        if channel.permissions_for(ctx.me).send_messages is False:
            await ctx.send(
                "I can't do that because I don't have permissions to send messages in"
                f" {channel.mention}."
            )
            return

        async with self.config.guild(ctx.guild).all() as conf:
            if conf["channel_id"] is None:
                conf["setup_state"] += 1

            conf["channel_id"] = channel.id

        await ctx.send(f"Channel set to {channel.mention}.")

    @commands.bot_has_permissions(manage_roles=True)
    @bdset.command()
    async def role(self, ctx: commands.Context, *, role: discord.Role):
        """
        Set the role that will be given to the user on their birthday.

        You can give the exact name or a mention.

        **Example:**
        - `[p]bdset role @Birthday` - set the role to @Birthday
        - `[p]bdset role Birthday` - set the role to @Birthday without a mention
        - `[p]bdset role 418058139913063657` - set the role with an ID
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.me, discord.Member)

        # no need to check hierarchy for author, since command is locked to admins
        if ctx.me.top_role < role:
            await ctx.send(f"I can't use {role.name} because it is higher than my highest role.")
            return

        async with self.config.guild(ctx.guild).all() as conf:
            if conf["role_id"] is None:
                conf["setup_state"] += 1

            conf["role_id"] = role.id

        await ctx.send(f"Role set to {role.name}.")

    @bdset.command()
    async def forceset(
        self, ctx: commands.Context, user: discord.Member, *, birthday: BirthdayConverter
    ):
        """
        Force-set a specific user's birthday.

        Only the month and day are stored - birth years are not supported.

        You can @ mention any user or type out their exact name. If you're typing out a name with
        spaces, make sure to put quotes around it (`"`).

        **Examples:**
        - `[p]bdset set @User 1-1` - set the birthday of `@User` to January 1st
        - `[p]bdset set User 1/1` - set the birthday of `@User` to January 1st
        - `[p]bdset set "User with spaces" 1-1` - set the birthday of `@User with spaces` to January 1st
        - `[p]bdset set 354125157387344896 1/1` - set the birthday of `354125157387344896` to January 1st
        """
        async with self.config.user(user).birthday() as bday:
            bday["year"] = None
            bday["month"] = birthday.month
            bday["day"] = birthday.day

        str_bday = birthday.strftime("%B %d")
        await ctx.send(f"{user.name}'s birthday has been set as {str_bday}. This will apply globally across all servers.")

    @bdset.command()
    async def forceremove(self, ctx: commands.Context, user: discord.Member):
        """Force-remove a user's birthday."""
        # guild only check in group
        if TYPE_CHECKING:
            assert isinstance(user, discord.Member)
            assert ctx.guild is not None

        m = await ctx.send(f"Are you sure? `{user.name}`'s birthday will be removed.")
        start_adding_reactions(m, ReactionPredicate.YES_OR_NO_EMOJIS)
        check = ReactionPredicate.yes_or_no(m, ctx.author)  # type:ignore

        try:
            await self.bot.wait_for("reaction_add", check=check, timeout=60)
        except asyncio.TimeoutError:
            for reaction in ReactionPredicate.YES_OR_NO_EMOJIS:
                await m.remove_reaction(reaction, ctx.guild.me)
            return

        if check.result is False:
            await ctx.send("Cancelled.")
            return

        await self.config.user(user).birthday.set({})
        await ctx.send(f"{user.name}'s birthday has been removed globally.")

    @commands.is_owner()
    @bdset.command()
    async def zemigrate(self, ctx: commands.Context):
        """
        Import data from ZeCogs'/flare's fork of Birthdays cog
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        if await self.config.guild(ctx.guild).setup_state() != 0:
            m = await ctx.send(
                "You have already started setting the cog up. Are you sure? This will overwrite"
                " your old data for all guilds."
            )

            start_adding_reactions(m, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(m, ctx.author)  # type:ignore
            try:
                await self.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send("Timeout. Cancelling.")
                return

            if pred.result is False:
                await ctx.send("Cancelling.")
                return

        bday_conf = Config.get_conf(
            None,
            int(
                "402907344791714442305425963449545260864366380186701260757993729164269683092560089"
                "8581468610241444437790345710548026575313281401238342705437492295956906331"
            ),
            cog_name="Birthdays",
        )

        for guild_id, guild_data in (await bday_conf.all_guilds()).items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            new_data = {
                "channel_id": guild_data.get("channel", None),
                "role_id": guild_data.get("role", None),
                "message_w_year": "{mention} is now **{new_age} years old**. :tada:",
                "message_wo_year": "It's {mention}'s birthday today! :tada:",
                "role_time_utc_s": 0,  # UTC midnight
                "message_time_utc_s": 0,  # UTC midnight
                "setup_state": 7,  # Updated from 5 to 7 for separate times
            }
            await self.config.guild(guild).set_raw(value=new_data)

        bday_conf.init_custom("GUILD_DATE", 2)
        all_member_data = await bday_conf.custom("GUILD_DATE").all()  # type:ignore
        if "backup" in all_member_data:
            del all_member_data["backup"]

        for guild_id, guild_data in all_member_data.items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            for day, users in guild_data.items():
                for user_id, year in users.items():
                    dt = datetime.datetime.fromordinal(int(day))

                    new_data = {
                        "year": None,  # Year support removed
                        "month": dt.month,
                        "day": dt.day,
                    }
                    await self.config.member_from_ids(int(guild_id), int(user_id)).birthday.set(
                        new_data
                    )

        await ctx.send(
            "All set. You can now configure the messages and time to send with other commands"
            " under `[p]bdset`, if you would like to change it from ZeLarp's. This is per-guild."
        )

    @bdset.command()
    async def rolemention(self, ctx: commands.Context, value: bool):
        """
        Choose whether or not to allow role mentions in birthday messages.

        By default role mentions are suppressed.

        To allow role mentions in the birthday message, run `[p]bdset rolemention true`.
        Disable them with `[p]bdset rolemention true`
        """
        await self.config.guild(ctx.guild).allow_role_mention.set(value)
        if value:
            await ctx.send("Role mentions have been enabled.")
        else:
            await ctx.send("Role mentions have been disabled.")

    @bdset.command()
    async def requiredrole(self, ctx: commands.Context, role1: Union[discord.Role, None] = None, role2: Union[discord.Role, None] = None):
        """
        Set up to 2 roles that users must have to set their birthday.

        Users must have at least one of the specified roles to set their
        birthday and have it announced.

        If they set their birthday and then lose all required roles, their birthday
        will be stored but will be ignored until they regain at least one role.

        You can purge birthdays of users who no longer have any required role
        with `[p]bdset requiredrolepurge`.

        If no roles are provided, the requirement is removed.

        View the current roles with `[p]bdset settings`.

        **Example:**
        - `[p]bdset requiredrole @Subscribers` - set one required role
        - `[p]bdset requiredrole @Subscribers @Members` - set two required roles
        - `[p]bdset requiredrole` - remove all required roles
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        # Migrate old config if needed
        old_require_role = await self.config.guild(ctx.guild).require_role()
        current_required_roles = await self.config.guild(ctx.guild).required_roles()

        if old_require_role and not current_required_roles:
            # Migrate from old single role to new list format
            current_required_roles = [old_require_role]
            await self.config.guild(ctx.guild).required_roles.set(current_required_roles)
            await self.config.guild(ctx.guild).require_role.clear()

        if role1 is None and role2 is None:
            # Clear all required roles
            if current_required_roles:
                await self.config.guild(ctx.guild).required_roles.set([])
                await ctx.send(
                    "All required roles have been removed. Birthdays can be set by anyone and will "
                    "always be announced."
                )
            else:
                await ctx.send(
                    "No roles are currently set. Birthdays can be set by anyone and will always be "
                    "announced."
                )
                await ctx.send_help()
        else:
            # Build list of role IDs
            role_ids = []
            role_names = []

            if role1:
                role_ids.append(role1.id)
                role_names.append(role1.name)

            if role2:
                role_ids.append(role2.id)
                role_names.append(role2.name)

            await self.config.guild(ctx.guild).required_roles.set(role_ids)

            if len(role_ids) == 1:
                await ctx.send(
                    f"The required role has been set to {role_names[0]}. Users without this role "
                    "will not have their birthday announced."
                )
            else:
                await ctx.send(
                    f"Required roles have been set to {' and '.join(role_names)}. Users must have "
                    "at least one of these roles to have their birthday announced."
                )

    @bdset.command(name="requiredrolepurge")
    async def requiredrole_purge(self, ctx: commands.Context):
        """Remove birthdays from the database for users who no longer have any required role.

        If you have required roles set, this will remove birthdays for users who don't have any of them.

        Users without any required role are temporarily ignored until they regain at least one role.

        This command allows you to permanently remove their birthday data from the database.
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        # Migrate old config if needed
        old_require_role = await self.config.guild(ctx.guild).require_role()
        required_roles = await self.config.guild(ctx.guild).required_roles()

        if old_require_role and not required_roles:
            # Migrate from old single role to new list format
            required_roles = [old_require_role]
            await self.config.guild(ctx.guild).required_roles.set(required_roles)
            await self.config.guild(ctx.guild).require_role.clear()

        if not required_roles:
            await ctx.send(
                "You don't have any required roles set. This command is only useful if you have "
                "required roles set."
            )
            return

        # Get all the role objects
        roles = []
        for role_id in required_roles:
            role = ctx.guild.get_role(role_id)
            if role:
                roles.append(role)

        if not roles:
            await ctx.send(
                "All required roles have been deleted. This command is only useful if you have "
                "valid required roles set."
            )
            return

        all_members = await self.config.all_members(ctx.guild)
        purged = 0
        for member_id, member_data in all_members.items():
            member = ctx.guild.get_member(member_id)
            if member is None:
                continue

            # Check if member has at least one of the required roles
            has_required_role = any(role in member.roles for role in roles)

            if not has_required_role:
                await self.config.member_from_ids(ctx.guild.id, member_id).birthday.clear()
                purged += 1

        await ctx.send(f"Purged {purged} users from the database.")

    @bdset.command()
    async def setchannel(self, ctx: commands.Context, channel: Union[discord.TextChannel, None] = None):
        """
        Set a channel where users must use the birthday set command.

        If users try to set their birthday outside this channel, they'll be told to use the correct channel.

        If no channel is provided, the restriction is removed and users can set their birthday anywhere.

        **Example:**
        - `[p]bdset setchannel #birthdays` - require users to set birthdays in #birthdays
        - `[p]bdset setchannel` - remove the channel restriction
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        if channel is None:
            await self.config.guild(ctx.guild).set_channel_id.clear()
            await ctx.send(
                "The channel restriction has been removed. Users can now set their birthday in any channel."
            )
        else:
            await self.config.guild(ctx.guild).set_channel_id.set(channel.id)
            await ctx.send(
                f"Users can now only set their birthday in {channel.mention}."
            )

    @bdset.command()
    async def image(self, ctx: commands.Context, image_url: Union[str, None] = None):
        """
        Set an image to include in birthday announcements.

        You can either provide a direct link to an image or upload an image file directly.

        If no URL is provided and no file is uploaded, the image will be removed from birthday announcements.

        **Example:**
        - `[p]bdset image https://i.imgur.com/example.png` - set the birthday image from URL
        - `[p]bdset image` - remove the birthday image
        - Upload a file with the command to use that image
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        # Check if there's an attachment
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            # Verify it's an image
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                await ctx.send("The uploaded file doesn't appear to be an image. Please upload an image file.")
                return

            image_url = attachment.url

        # Remove image if no URL and no attachment
        if image_url is None:
            # Delete old image file if it exists
            old_image_path = await self.config.guild(ctx.guild).image_path()
            if old_image_path:
                old_path = Path(old_image_path)
                if old_path.exists():
                    old_path.unlink()

            await self.config.guild(ctx.guild).image_path.clear()
            await self.config.guild(ctx.guild).image_url.clear()
            await ctx.send("The birthday announcement image has been removed.")
            return

        # Download and save the image
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status != 200:
                            await ctx.send(f"Failed to download image. Status code: {resp.status}")
                            return

                        # Get file extension from content type
                        content_type = resp.headers.get('Content-Type', '')
                        if not content_type.startswith('image/'):
                            await ctx.send("The URL doesn't appear to point to an image.")
                            return

                        # Determine file extension
                        ext_map = {
                            'image/png': '.png',
                            'image/jpeg': '.jpg',
                            'image/jpg': '.jpg',
                            'image/gif': '.gif',
                            'image/webp': '.webp',
                        }
                        ext = ext_map.get(content_type, '.png')

                        # Delete old image if it exists
                        old_image_path = await self.config.guild(ctx.guild).image_path()
                        if old_image_path:
                            old_path = Path(old_image_path)
                            if old_path.exists():
                                old_path.unlink()

                        # Save new image
                        image_filename = f"{ctx.guild.id}_birthday{ext}"
                        image_path = self.images_path / image_filename

                        image_data = await resp.read()
                        image_path.write_bytes(image_data)

                        # Store the path in config
                        await self.config.guild(ctx.guild).image_path.set(str(image_path))
                        await self.config.guild(ctx.guild).image_url.clear()

                        await ctx.send(f"Birthday announcements will now include this image.")

            except aiohttp.ClientError as e:
                await ctx.send(f"Failed to download image: {e}")
            except Exception as e:
                log.exception("Error downloading birthday image", exc_info=e)
                await ctx.send(f"An error occurred while downloading the image.")

    @bdset.command()
    async def reaction(self, ctx: commands.Context, *emojis: str):
        """
        Set emoji reactions to add to birthday announcement messages.

        The bot will automatically react to birthday announcements with these emojis.

        Provide one or more unicode emojis (like 🎉) or custom server emojis.
        If no emojis are provided, all reactions will be removed from birthday announcements.

        **Example:**
        - `[p]bdset reaction 🎉` - set a single birthday reaction
        - `[p]bdset reaction 🎉 🎂 🎈` - set multiple birthday reactions
        - `[p]bdset reaction :custom_emoji:` - set a custom emoji reaction
        - `[p]bdset reaction` - remove all birthday reactions
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        # Migrate old config if needed
        old_reaction = await self.config.guild(ctx.guild).announcement_reaction()
        current_reactions = await self.config.guild(ctx.guild).announcement_reactions()

        if old_reaction and not current_reactions:
            current_reactions = [old_reaction]
            await self.config.guild(ctx.guild).announcement_reactions.set(current_reactions)
            await self.config.guild(ctx.guild).announcement_reaction.clear()

        if not emojis:
            await self.config.guild(ctx.guild).announcement_reactions.set([])
            await self.config.guild(ctx.guild).announcement_reaction.clear()
            await ctx.send("All birthday announcement reactions have been removed.")
        else:
            # Validate all emojis by testing if they can be added as reactions
            valid_emojis = []
            invalid_emojis = []

            for emoji in emojis:
                try:
                    await ctx.message.add_reaction(emoji)
                    await ctx.message.clear_reaction(emoji)
                    valid_emojis.append(emoji)
                except discord.HTTPException:
                    invalid_emojis.append(emoji)

            if invalid_emojis:
                await ctx.send(
                    f"Invalid emoji(s): {', '.join(invalid_emojis)}\n"
                    "Make sure emojis are:\n"
                    "- Valid unicode emojis (like 🎉)\n"
                    "- Custom emojis from this server or a server the bot is in"
                )
                if not valid_emojis:
                    return

            await self.config.guild(ctx.guild).announcement_reactions.set(valid_emojis)
            await self.config.guild(ctx.guild).announcement_reaction.clear()

            if len(valid_emojis) == 1:
                await ctx.send(f"Birthday announcements will now be reacted to with {valid_emojis[0]}")
            else:
                emoji_str = " ".join(valid_emojis)
                await ctx.send(f"Birthday announcements will now be reacted to with {emoji_str}")

    @bdset.command()
    async def test(self, ctx: commands.Context, *, member: discord.Member = None):
        """
        Send a test birthday announcement message.

        This will send a test message to the configured birthday channel using the current settings.

        **Example:**
        - `[p]bdset test` - send a test announcement for yourself
        - `[p]bdset test @User` - send a test announcement for a specific user
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.me, discord.Member)

        if member is None:
            member = ctx.author

        # Check if setup is complete
        if not await self.check_if_setup(ctx.guild):
            await ctx.send(
                "The birthday cog is not fully set up yet. Please complete the setup first using "
                f"`{ctx.clean_prefix}bdset interactive` or check what's missing with "
                f"`{ctx.clean_prefix}birthdayinfo`."
            )
            return

        # Get the birthday channel
        channel_id = await self.config.guild(ctx.guild).channel_id()
        channel = ctx.guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            await ctx.send("The birthday channel is not set or no longer exists.")
            return

        # Check permissions
        if error := channel_perm_check(ctx.me, channel):
            await ctx.send(f"I can't send messages in {channel.mention}: {error}")
            return

        # Get the message (no year support)
        message = await self.config.guild(ctx.guild).message_wo_year()
        formatted_message = format_bday_message(message, member)

        # Get image path
        image_path = await self.config.guild(ctx.guild).image_path()

        # Get role mention setting
        allow_role_mention = await self.config.guild(ctx.guild).allow_role_mention()

        # Get announcement reactions
        old_reaction = await self.config.guild(ctx.guild).announcement_reaction()
        announcement_reactions = await self.config.guild(ctx.guild).announcement_reactions()

        # Migrate old config if needed
        if old_reaction and not announcement_reactions:
            announcement_reactions = [old_reaction]
            await self.config.guild(ctx.guild).announcement_reactions.set(announcement_reactions)
            await self.config.guild(ctx.guild).announcement_reaction.clear()

        # Send the test message
        await ctx.send(f"Sending test birthday announcement to {channel.mention}...")

        try:
            # Prepare image file if exists
            file = None
            if image_path and Path(image_path).exists():
                file = discord.File(image_path, filename=Path(image_path).name)

            sent_message = await channel.send(
                formatted_message,
                file=file,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=allow_role_mention, users=True
                ),
            )

            # Add reactions if configured
            if announcement_reactions:
                failed_reactions = []
                for reaction in announcement_reactions:
                    try:
                        await sent_message.add_reaction(reaction)
                    except discord.HTTPException:
                        failed_reactions.append(reaction)

                if failed_reactions:
                    await ctx.send(
                        f"Test announcement sent, but failed to add reaction(s): {' '.join(failed_reactions)}. "
                        "The emoji(s) may no longer be valid."
                    )
                    return

            await ctx.send("Test announcement sent successfully!")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to send test announcement: {e}")

    @bdset.command()
    async def forcesend(self, ctx: commands.Context):
        """
        Force send birthday announcements for anyone with a birthday today.

        This manually triggers birthday announcements, useful if the automated
        announcement didn't run at the configured time.

        This will send announcements even if they were already sent today.

        **Example:**
        - `[p]bdset forcesend` - force send all birthday announcements for today
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None
            assert isinstance(ctx.me, discord.Member)

        # Check if setup is complete
        if not await self.check_if_setup(ctx.guild):
            await ctx.send(
                "The birthday cog is not fully set up yet. Please complete the setup first using "
                f"`{ctx.clean_prefix}bdset interactive` or check what's missing with "
                f"`{ctx.clean_prefix}birthdayinfo`."
            )
            return

        async with ctx.typing():
            # Get guild settings
            guild_settings = await self.config.guild(ctx.guild).all()

            # Get role time to determine "today"
            role_time_utc_s = guild_settings.get("role_time_utc_s")
            if role_time_utc_s is None:
                await ctx.send("Role time is not configured. Please set it with `[p]bdset roletime`.")
                return

            role_hour_td = datetime.timedelta(seconds=role_time_utc_s)

            # Determine today based on role time
            today_dt = (datetime.datetime.utcnow() - role_hour_td).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            start = today_dt + role_hour_td
            end = start + datetime.timedelta(days=1)

            # Get required roles
            required_role_ids = guild_settings.get("required_roles", [])
            required_roles = []
            for role_id in required_role_ids:
                role = ctx.guild.get_role(role_id)
                if role:
                    required_roles.append(role)

            # Find all members with birthdays today
            all_birthdays = await self.config.all_users()
            birthday_members: dict[discord.Member, datetime.datetime] = {}

            for user_id, user_data in all_birthdays.items():
                birthday = user_data.get("birthday")
                if not birthday:
                    continue

                member = ctx.guild.get_member(int(user_id))
                if member is None:
                    continue

                # Check if member has required role (if any are set)
                if required_roles and not any(role in member.roles for role in required_roles):
                    continue

                proper_bday_dt = datetime.datetime(
                    year=birthday["year"] or 1, month=birthday["month"], day=birthday["day"]
                )
                this_year_bday_dt = proper_bday_dt.replace(year=today_dt.year) + role_hour_td

                if start <= this_year_bday_dt < end:  # birthday is today
                    birthday_members[member] = proper_bday_dt

            if not birthday_members:
                await ctx.send("No one has a birthday today.")
                return

            # Get the birthday channel
            channel_id = guild_settings["channel_id"]
            channel = ctx.guild.get_channel(channel_id)
            if channel is None or not isinstance(channel, discord.TextChannel):
                await ctx.send(
                    f"Birthday channel (ID: {channel_id}) was not found or is not a text channel."
                )
                return

            # Check permissions
            if error := channel_perm_check(ctx.me, channel):
                await ctx.send(f"I can't send messages in {channel.mention}: {error}")
                return

            # Get announcement settings
            image_path = guild_settings.get("image_path")
            announcement_reactions = guild_settings.get("announcement_reactions", [])
            allow_role_mention = guild_settings.get("allow_role_mention", False)

            # Migrate old reaction config if needed
            old_reaction = guild_settings.get("announcement_reaction")
            if old_reaction and not announcement_reactions:
                announcement_reactions = [old_reaction]
                await self.config.guild(ctx.guild).announcement_reactions.set(announcement_reactions)
                await self.config.guild(ctx.guild).announcement_reaction.clear()

            # Get the announced_today list
            announced_today = guild_settings.get("announced_today", [])

            # Send announcements
            sent_count = 0
            for member, dt in birthday_members.items():
                await self.send_announcement(
                    channel,
                    format_bday_message(guild_settings["message_wo_year"], member),
                    allow_role_mention,
                    image_path,
                    announcement_reactions,
                )

                # Add to announced_today list if not already there
                if member.id not in announced_today:
                    announced_today.append(member.id)

                sent_count += 1

            # Update the announced_today list
            await self.config.guild(ctx.guild).announced_today.set(announced_today)

            if sent_count == 1:
                await ctx.send(f"✅ Sent 1 birthday announcement to {channel.mention}.")
            else:
                await ctx.send(f"✅ Sent {sent_count} birthday announcements to {channel.mention}.")

    @bdset.command()
    async def stop(self, ctx: commands.Context):
        """
        Stop the cog from sending birthday messages and giving roles in the server.
        """
        # group has guild check
        if TYPE_CHECKING:
            assert ctx.guild is not None

        confirm = await wait_for_yes_no(
            ctx, "Are you sure you want to stop sending updates and giving roles?"
        )
        if confirm is False:
            await ctx.send("Okay, nothing's changed.")
            return

        await self.config.guild(ctx.guild).clear()

        confirm = await wait_for_yes_no(
            ctx,
            "I've deleted your configuration. Would you also like to delete the data about when"
            " users birthdays are?",
        )
        if confirm is False:
            await ctx.send("I'll keep that.")
            return

        await self.config.clear_all_members(ctx.guild)
        await ctx.send("Deleted.")
