"""Configuration commands for Trade Commission cog."""
import discord
import logging
from typing import Optional
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list
import pytz

log = logging.getLogger("red.tradecommission")


class CommandsConfigMixin:
    """Mixin containing configuration commands for Trade Commission."""

    async def tc_schedule(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        day: str,
        hour: int,
        minute: int = 0,
        timezone: str = "UTC"
    ):
        """
        Schedule weekly Trade Commission messages.

        **Arguments:**
        - `channel`: The channel to send messages to
        - `day`: Day of week (Monday, Tuesday, etc.)
        - `hour`: Hour in 24h format (0-23)
        - `minute`: Minute (0-59), default 0
        - `timezone`: Timezone (e.g., UTC, America/New_York), default UTC

        **Example:**
        - `[p]tc schedule #trade-info Monday 9 0 America/New_York`
        """
        # Validate day
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        day_lower = day.lower()
        if day_lower not in days:
            await ctx.send(f"Invalid day! Use: {humanize_list(list(days.keys()))}")
            return

        # Validate hour and minute
        if not 0 <= hour <= 23:
            await ctx.send("Hour must be between 0 and 23!")
            return
        if not 0 <= minute <= 59:
            await ctx.send("Minute must be between 0 and 59!")
            return

        # Validate timezone
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            await ctx.send(f"Invalid timezone! Use a valid timezone like UTC or America/New_York.")
            return

        # Save config
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.config.guild(ctx.guild).schedule_day.set(days[day_lower])
        await self.config.guild(ctx.guild).schedule_hour.set(hour)
        await self.config.guild(ctx.guild).schedule_minute.set(minute)
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await self.config.guild(ctx.guild).enabled.set(True)

        await ctx.send(
            f"✅ Trade Commission messages scheduled!\n"
            f"**Channel:** {channel.mention}\n"
            f"**Schedule:** Every {day.title()} at {hour:02d}:{minute:02d} {timezone}"
        )

    async def tc_disable(self, ctx: commands.Context):
        """Disable weekly Trade Commission messages."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("✅ Weekly Trade Commission messages disabled.")

    async def tc_enable(self, ctx: commands.Context):
        """Enable weekly Trade Commission messages."""
        channel_id = await self.config.guild(ctx.guild).channel_id()
        if not channel_id:
            await ctx.send("❌ Please set up a schedule first using `[p]tc schedule`!")
            return

        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Weekly Trade Commission messages enabled.")

    async def tc_addrole(self, ctx: commands.Context, role: discord.Role):
        """
        Add a role that can use addinfo reactions.

        Users with this role will be able to click reactions on the addinfo message
        to select Trade Commission options, even if they don't have Manage Server permission.

        **Arguments:**
        - `role`: The role to add

        **Example:**
        - `[p]tc addrole @Trade Manager`
        """
        async with self.config.guild(ctx.guild).allowed_roles() as allowed_roles:
            if role.id in allowed_roles:
                await ctx.send(f"❌ {role.mention} is already allowed to use addinfo!")
                return

            allowed_roles.append(role.id)

        await ctx.send(f"✅ {role.mention} can now use addinfo reactions!")

    async def tc_removerole(self, ctx: commands.Context, role: discord.Role):
        """
        Remove a role from the addinfo allowed list.

        **Arguments:**
        - `role`: The role to remove

        **Example:**
        - `[p]tc removerole @Trade Manager`
        """
        async with self.config.guild(ctx.guild).allowed_roles() as allowed_roles:
            if role.id not in allowed_roles:
                await ctx.send(f"❌ {role.mention} is not in the allowed roles list!")
                return

            allowed_roles.remove(role.id)

        await ctx.send(f"✅ {role.mention} can no longer use addinfo reactions.")

    async def tc_listroles(self, ctx: commands.Context):
        """
        List all roles that can use addinfo reactions.

        Shows which roles have permission to click reactions on the addinfo message,
        in addition to users with Manage Server permission.
        """
        allowed_role_ids = await self.config.guild(ctx.guild).allowed_roles()

        if not allowed_role_ids:
            await ctx.send(
                "❌ No additional roles configured.\n"
                "Only users with **Manage Server** permission can use addinfo reactions.\n\n"
                "Use `[p]tc addrole` to add a role."
            )
            return

        # Get role objects
        roles = []
        for role_id in allowed_role_ids:
            role = ctx.guild.get_role(role_id)
            if role:
                roles.append(role.mention)
            else:
                roles.append(f"Deleted Role (ID: {role_id})")

        embed = discord.Embed(
            title="📝 Addinfo Allowed Roles",
            description=(
                "The following roles can use addinfo reactions:\n\n"
                + "\n".join(f"• {role}" for role in roles) +
                "\n\n*Note: Users with Manage Server permission can always use addinfo.*"
            ),
            color=discord.Color.blue()
        )

        await ctx.send(embed=embed)

    async def tc_adduser(self, ctx: commands.Context, user: discord.Member):
        """
        Add a user that can use addinfo reactions.

        Users added with this command will be able to click reactions on the addinfo message
        to select Trade Commission options, even if they don't have Manage Server permission.

        **Arguments:**
        - `user`: The user to add

        **Example:**
        - `[p]tc adduser @JohnDoe`
        """
        async with self.config.guild(ctx.guild).allowed_users() as allowed_users:
            if user.id in allowed_users:
                await ctx.send(f"❌ {user.mention} is already allowed to use addinfo!")
                return

            allowed_users.append(user.id)

        await ctx.send(f"✅ {user.mention} can now use addinfo reactions!")

    async def tc_removeuser(self, ctx: commands.Context, user: discord.Member):
        """
        Remove a user from the addinfo allowed list.

        **Arguments:**
        - `user`: The user to remove

        **Example:**
        - `[p]tc removeuser @JohnDoe`
        """
        async with self.config.guild(ctx.guild).allowed_users() as allowed_users:
            if user.id not in allowed_users:
                await ctx.send(f"❌ {user.mention} is not in the allowed users list!")
                return

            allowed_users.remove(user.id)

        await ctx.send(f"✅ {user.mention} can no longer use addinfo reactions.")

    async def tc_listusers(self, ctx: commands.Context):
        """
        List all users that can use addinfo reactions.

        Shows which individual users have permission to click reactions on the addinfo message,
        in addition to users with Manage Server permission or allowed roles.
        """
        allowed_user_ids = await self.config.guild(ctx.guild).allowed_users()

        if not allowed_user_ids:
            await ctx.send(
                "❌ No individual users configured.\n"
                "Only users with **Manage Server** permission or allowed roles can use addinfo reactions.\n\n"
                "Use `[p]tc adduser` to add a user."
            )
            return

        # Get user objects
        users = []
        for user_id in allowed_user_ids:
            user = ctx.guild.get_member(user_id)
            if user:
                users.append(user.mention)
            else:
                users.append(f"Left Server (ID: {user_id})")

        embed = discord.Embed(
            title="📝 Addinfo Allowed Users",
            description=(
                "The following users can use addinfo reactions:\n\n"
                + "\n".join(f"• {user}" for user in users) +
                "\n\n*Note: Users with Manage Server permission or allowed roles can also use addinfo.*"
            ),
            color=discord.Color.blue()
        )

        await ctx.send(embed=embed)

    async def tc_settitle(self, ctx: commands.Context, *, title: str):
        """
        Set the title/header for Trade Commission messages.

        **Arguments:**
        - `title`: The title text to display at the top of the embed

        **Example:**
        - `[p]tc settitle 📊 Weekly Trade Routes - Where Winds Meet`
        """
        await self.config.guild(ctx.guild).message_title.set(title)
        await ctx.send(f"✅ Message title set to:\n> {title}")

    async def tc_setinitial(self, ctx: commands.Context, *, description: str):
        """
        Set the initial description shown before options are added.

        This text appears when the weekly message is first posted,
        before anyone uses addinfo to select options.

        **Arguments:**
        - `description`: The description text

        **Example:**
        - `[p]tc setinitial This week's trade routes will be announced soon! Check back later.`
        """
        await self.config.guild(ctx.guild).initial_description.set(description)
        await ctx.send(f"✅ Initial description set to:\n> {description[:100]}{'...' if len(description) > 100 else ''}")

    async def tc_setpost(self, ctx: commands.Context, *, description: str):
        """
        Set the description shown after options are added.

        This text appears at the top of the message when options have been
        selected via addinfo reactions.

        **Arguments:**
        - `description`: The description text

        **Example:**
        - `[p]tc setpost This week's Trade Commission routes:`
        """
        await self.config.guild(ctx.guild).post_description.set(description)
        await ctx.send(f"✅ Post description set to:\n> {description[:100]}{'...' if len(description) > 100 else ''}")

    async def tc_setpingrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """
        Set a role to ping when posting Trade Commission messages.

        The role will be mentioned when the weekly message is posted,
        alerting members with that role.

        **Arguments:**
        - `role`: The role to ping (or omit to remove ping)

        **Examples:**
        - `[p]tc setpingrole @Traders` - Set ping role
        - `[p]tc setpingrole` - Remove ping role
        """
        if role is None:
            await self.config.guild(ctx.guild).ping_role_id.set(None)
            await ctx.send("✅ Ping role removed. Messages will no longer ping a role.")
        else:
            await self.config.guild(ctx.guild).ping_role_id.set(role.id)
            await ctx.send(f"✅ Will ping {role.mention} when posting Trade Commission messages.")

    async def tc_setnotification(self, ctx: commands.Context, *, message: str):
        """
        Set the notification message sent when all 3 options are selected.

        This message will be sent to the trade commission channel when someone
        selects the 3rd option via the addinfo panel. The configured ping role
        will be mentioned with this message. The message will automatically
        delete after 3 hours.

        **Arguments:**
        - `message`: The notification message text

        **Example:**
        - `[p]tc setnotification 📢 All 3 trade commission options have been selected! Check them out above!`
        """
        await self.config.guild(ctx.guild).notification_message.set(message)
        await ctx.send(f"✅ Notification message set to:\n> {message[:100]}{'...' if len(message) > 100 else ''}\n\n*This message will be sent (with role ping) when 3 options are selected and will auto-delete after 3 hours.*")
