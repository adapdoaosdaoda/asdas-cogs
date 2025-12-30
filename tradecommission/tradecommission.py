"""Trade Commission weekly message cog for Where Winds Meet."""
import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list
import pytz
import re


def extract_final_emoji(text: str) -> Optional[str]:
    """Extract the final emoji from a text string.

    Args:
        text: The text to extract emoji from

    Returns:
        The final emoji found in the text, or None if no emoji found
    """
    # Unicode emoji pattern - matches standard emoji characters
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )

    # Find all emojis in the text
    emojis = emoji_pattern.findall(text)

    # Return the last emoji found, or None if no emojis
    return emojis[-1] if emojis else None


class TradeCommission(commands.Cog):
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

    async def _has_addinfo_permission(self, member: discord.Member) -> bool:
        """Check if a member has permission to use addinfo reactions."""
        # Check if user has Manage Server permission
        if member.guild_permissions.manage_guild:
            return True

        # Check if user is in the allowed users list
        allowed_user_ids = await self.config.guild(member.guild).allowed_users()
        if member.id in allowed_user_ids:
            return True

        # Check if user has one of the allowed roles
        allowed_role_ids = await self.config.guild(member.guild).allowed_roles()
        member_role_ids = [role.id for role in member.roles]

        return any(role_id in allowed_role_ids for role_id in member_role_ids)

    async def _check_schedule_loop(self):
        """Background loop to check for scheduled messages."""
        await self.bot.wait_until_ready()
        while True:
            try:
                for guild in self.bot.guilds:
                    await self._check_guild_schedule(guild)
                # Check every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in Trade Commission schedule loop: {e}")
                await asyncio.sleep(3600)

    async def _check_guild_schedule(self, guild: discord.Guild):
        """Check if it's time to send the weekly message for a guild."""
        config = await self.config.guild(guild).all()

        if not config["enabled"] or not config["channel_id"]:
            return

        channel = guild.get_channel(config["channel_id"])
        if not channel:
            return

        # Get timezone
        tz = pytz.timezone(config["timezone"])
        now = datetime.now(tz)

        # Check if it's the right day and hour
        if (now.weekday() == config["schedule_day"] and
            now.hour == config["schedule_hour"] and
            now.minute >= config["schedule_minute"] and
            now.minute < config["schedule_minute"] + 60):

            # Check if we already sent a message this week
            last_sent = await self.config.guild(guild).get_raw("last_sent", default=None)
            if last_sent:
                last_sent_dt = datetime.fromisoformat(last_sent)
                if (now - last_sent_dt).days < 7:
                    return

            # Send the weekly message
            await self._send_weekly_message(guild, channel)
            await self.config.guild(guild).last_sent.set(now.isoformat())

    async def _send_weekly_message(self, guild: discord.Guild, channel: discord.TextChannel):
        """Send the weekly Trade Commission message."""
        # Clear active options for new week
        await self.config.guild(guild).active_options.clear()

        config = await self.config.guild(guild).all()

        # Delete previous week's message if it exists
        if config["previous_message_id"]:
            try:
                prev_channel = guild.get_channel(config["current_channel_id"]) or channel
                prev_message = await prev_channel.fetch_message(config["previous_message_id"])
                await prev_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or no permission

        # Determine embed color from ping role or default
        embed_color = discord.Color.blue()
        if config["ping_role_id"]:
            ping_role = guild.get_role(config["ping_role_id"])
            if ping_role and ping_role.color != discord.Color.default():
                embed_color = ping_role.color

        embed = discord.Embed(
            title=config["message_title"],
            description=config["initial_description"],
            color=embed_color,
        )

        # Prepare content with ping if role is configured
        content = None
        if config["ping_role_id"]:
            role = guild.get_role(config["ping_role_id"])
            if role:
                content = role.mention

        try:
            message = await channel.send(content=content, embed=embed)
            # Store current message as previous for next week
            await self.config.guild(guild).previous_message_id.set(config["current_message_id"])
            # Set new current message
            await self.config.guild(guild).current_message_id.set(message.id)
            await self.config.guild(guild).current_channel_id.set(channel.id)
        except discord.Forbidden:
            pass

    @commands.group(name="tradecommission", aliases=["tc"])
    async def tradecommission(self, ctx: commands.Context):
        """
        Manage Trade Commission weekly messages.

        Global config commands (setoption, setimage) can be used in DMs by the bot owner.
        Server-specific commands require being used in a server with admin permissions.
        """
        pass

    @tradecommission.command(name="schedule")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="disable")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_disable(self, ctx: commands.Context):
        """Disable weekly Trade Commission messages."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("✅ Weekly Trade Commission messages disabled.")

    @tradecommission.command(name="enable")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_enable(self, ctx: commands.Context):
        """Enable weekly Trade Commission messages."""
        channel_id = await self.config.guild(ctx.guild).channel_id()
        if not channel_id:
            await ctx.send("❌ Please set up a schedule first using `[p]tc schedule`!")
            return

        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Weekly Trade Commission messages enabled.")

    @tradecommission.command(name="addrole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="removerole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="listroles")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="adduser")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="removeuser")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="listusers")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="settitle")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="setinitial")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="setpost")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="setpingrole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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

    @tradecommission.command(name="post")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_post(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """
        Manually post a Trade Commission message now.

        **Arguments:**
        - `channel`: Optional channel to post to. Uses configured channel if not specified.
        """
        if not channel:
            channel_id = await self.config.guild(ctx.guild).channel_id()
            if not channel_id:
                await ctx.send("❌ No channel configured! Please specify a channel.")
                return
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                await ctx.send("❌ Configured channel not found!")
                return

        await self._send_weekly_message(ctx.guild, channel)
        await ctx.send(f"✅ Posted Trade Commission message to {channel.mention}")

    @tradecommission.command(name="addinfo")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_addinfo(self, ctx: commands.Context):
        """
        Add information to the current week's Trade Commission message via reactions.

        This will create a message with reaction emotes. Click the reactions to add
        up to 3 options to the weekly Trade Commission message.
        """
        current_msg_id = await self.config.guild(ctx.guild).current_message_id()
        current_ch_id = await self.config.guild(ctx.guild).current_channel_id()

        if not current_msg_id or not current_ch_id:
            await ctx.send("❌ No current Trade Commission message found! Use `[p]tc post` first.")
            return

        channel = ctx.guild.get_channel(current_ch_id)
        if not channel:
            await ctx.send("❌ Channel not found!")
            return

        try:
            message = await channel.fetch_message(current_msg_id)
        except discord.NotFound:
            await ctx.send("❌ Message not found!")
            return

        # Get global trade options and emoji titles
        trade_options = await self.config.trade_options()
        active_options = await self.config.guild(ctx.guild).active_options()
        emoji_titles = await self.config.emoji_titles()

        if not trade_options:
            await ctx.send("❌ No trade options configured! Use `[p]tc setoption` to add options first.")
            return

        embed = discord.Embed(
            title="📝 Add Trade Commission Information",
            description=(
                "React with the emotes below to add information to this week's Trade Commission message.\n\n"
                "You can select up to **3 options**. Each option will add its configured information "
                "to the weekly message.\n\n"
                "**Click a reaction to toggle that option on/off.**"
            ),
            color=discord.Color.green(),
        )

        # Group options by their final emoji in description
        emoji_groups = {}  # {emoji: [(idx, option), ...]}
        no_emoji_options = []  # [(idx, option), ...]

        for idx, option in enumerate(trade_options):
            final_emoji = extract_final_emoji(option['description'])
            if final_emoji:
                if final_emoji not in emoji_groups:
                    emoji_groups[final_emoji] = []
                emoji_groups[final_emoji].append((idx, option))
            else:
                no_emoji_options.append((idx, option))

        # Build fields for each emoji group
        if emoji_groups or no_emoji_options:
            # Display emoji groups first
            for category_emoji, options_list in sorted(emoji_groups.items()):
                # Get custom title or use default
                group_title = emoji_titles.get(category_emoji, f"{category_emoji} Options")

                group_lines = []
                for idx, option in options_list:
                    status = "✅" if idx in active_options else "⬜"
                    group_lines.append(f"{status} {option['emoji']} **{option['title']}**")

                # Split into multiple fields if needed
                current_chunk = []
                current_length = 0
                field_count = 0

                for line in group_lines:
                    line_length = len(line) + 1  # +1 for newline
                    if current_length + line_length > 1000:  # Leave buffer
                        # Add current chunk
                        field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                        embed.add_field(
                            name=f"{group_title}{field_suffix}",
                            value="\n".join(current_chunk),
                            inline=True
                        )
                        current_chunk = [line]
                        current_length = line_length
                        field_count += 1
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                # Add remaining chunk
                if current_chunk:
                    field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                    embed.add_field(
                        name=f"{group_title}{field_suffix}",
                        value="\n".join(current_chunk),
                        inline=False
                    )

            # Display options without emoji last
            if no_emoji_options:
                group_lines = []
                for idx, option in no_emoji_options:
                    status = "✅" if idx in active_options else "⬜"
                    group_lines.append(f"{status} {option['emoji']} **{option['title']}**")

                # Split into multiple fields if needed
                current_chunk = []
                current_length = 0
                field_count = 0

                for line in group_lines:
                    line_length = len(line) + 1
                    if current_length + line_length > 1000:
                        field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                        embed.add_field(
                            name=f"Other Options{field_suffix}",
                            value="\n".join(current_chunk),
                            inline=True
                        )
                        current_chunk = [line]
                        current_length = line_length
                        field_count += 1
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                if current_chunk:
                    field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                    embed.add_field(
                        name=f"Other Options{field_suffix}",
                        value="\n".join(current_chunk),
                        inline=False
                    )
        else:
            embed.add_field(
                name="Available Options",
                value="No options configured",
                inline=False
            )

        embed.set_footer(text=f"Selected: {len(active_options)}/3")

        # Send the message and add reactions
        control_msg = await ctx.send(embed=embed)

        # Store the control message ID
        await self.config.guild(ctx.guild).addinfo_message_id.set(control_msg.id)

        # Add reaction emotes
        for option in trade_options:
            if option["emoji"]:  # Only add if emoji is configured
                try:
                    await control_msg.add_reaction(option["emoji"])
                except discord.HTTPException:
                    pass  # Skip if emoji is invalid

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reactions on addinfo messages."""
        # Ignore bot reactions
        if user.bot:
            return

        # Check if this is a guild
        if not reaction.message.guild:
            return

        guild = reaction.message.guild

        # Check if user has permission
        member = guild.get_member(user.id)
        if not member or not await self._has_addinfo_permission(member):
            return

        # Check if this is an addinfo message
        addinfo_msg_id = await self.config.guild(guild).addinfo_message_id()
        if not addinfo_msg_id or reaction.message.id != addinfo_msg_id:
            return

        # Find which option this emoji corresponds to
        trade_options = await self.config.trade_options()
        option_idx = None

        for idx, option in enumerate(trade_options):
            if str(reaction.emoji) == option["emoji"]:
                option_idx = idx
                break

        if option_idx is None:
            return

        # Toggle the option
        async with self.config.guild(guild).active_options() as active_options:
            if option_idx in active_options:
                # Remove option
                active_options.remove(option_idx)
            else:
                # Check if we've reached the limit
                if len(active_options) >= 3:
                    # Remove reaction and notify user
                    try:
                        await reaction.remove(user)
                    except discord.HTTPException:
                        pass
                    try:
                        await user.send("❌ Maximum of 3 options can be selected! Please deselect an option first.")
                    except discord.Forbidden:
                        pass
                    return

                # Add option
                active_options.append(option_idx)

        # Update the Trade Commission message
        await self.update_commission_message(guild)

        # Check if we now have 3 options selected
        active_options = await self.config.guild(guild).active_options()
        if len(active_options) == 3:
            # Delete the addinfo message
            try:
                await reaction.message.delete()
                await self.config.guild(guild).addinfo_message_id.set(None)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        else:
            # Update the control message
            await self._update_addinfo_message(guild, reaction.message)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """Handle reaction removals on addinfo messages."""
        # Ignore bot reactions
        if user.bot:
            return

        # Check if this is a guild
        if not reaction.message.guild:
            return

        guild = reaction.message.guild

        # Check if user has permission
        member = guild.get_member(user.id)
        if not member or not await self._has_addinfo_permission(member):
            return

        # Check if this is an addinfo message
        addinfo_msg_id = await self.config.guild(guild).addinfo_message_id()
        if not addinfo_msg_id or reaction.message.id != addinfo_msg_id:
            return

        # Find which option this emoji corresponds to
        trade_options = await self.config.trade_options()
        option_idx = None

        for idx, option in enumerate(trade_options):
            if str(reaction.emoji) == option["emoji"]:
                option_idx = idx
                break

        if option_idx is None:
            return

        # Remove the option if it's active
        async with self.config.guild(guild).active_options() as active_options:
            if option_idx in active_options:
                active_options.remove(option_idx)

        # Update the Trade Commission message
        await self.update_commission_message(guild)

        # Update the control message
        await self._update_addinfo_message(guild, reaction.message)

    async def _update_addinfo_message(self, guild: discord.Guild, message: discord.Message):
        """Update the addinfo control message."""
        trade_options = await self.config.trade_options()
        active_options = await self.config.guild(guild).active_options()
        emoji_titles = await self.config.emoji_titles()

        embed = discord.Embed(
            title="📝 Add Trade Commission Information",
            description=(
                "React with the emotes below to add information to this week's Trade Commission message.\n\n"
                "You can select up to **3 options**. Each option will add its configured information "
                "to the weekly message.\n\n"
                "**Click a reaction to toggle that option on/off.**"
            ),
            color=discord.Color.green(),
        )

        # Group options by their final emoji in description
        emoji_groups = {}  # {emoji: [(idx, option), ...]}
        no_emoji_options = []  # [(idx, option), ...]

        for idx, option in enumerate(trade_options):
            final_emoji = extract_final_emoji(option['description'])
            if final_emoji:
                if final_emoji not in emoji_groups:
                    emoji_groups[final_emoji] = []
                emoji_groups[final_emoji].append((idx, option))
            else:
                no_emoji_options.append((idx, option))

        # Build fields for each emoji group
        if emoji_groups or no_emoji_options:
            # Display emoji groups first
            for category_emoji, options_list in sorted(emoji_groups.items()):
                # Get custom title or use default
                group_title = emoji_titles.get(category_emoji, f"{category_emoji} Options")

                group_lines = []
                for idx, option in options_list:
                    status = "✅" if idx in active_options else "⬜"
                    group_lines.append(f"{status} {option['emoji']} **{option['title']}**")

                # Split into multiple fields if needed
                current_chunk = []
                current_length = 0
                field_count = 0

                for line in group_lines:
                    line_length = len(line) + 1  # +1 for newline
                    if current_length + line_length > 1000:  # Leave buffer
                        # Add current chunk
                        field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                        embed.add_field(
                            name=f"{group_title}{field_suffix}",
                            value="\n".join(current_chunk),
                            inline=True
                        )
                        current_chunk = [line]
                        current_length = line_length
                        field_count += 1
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                # Add remaining chunk
                if current_chunk:
                    field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                    embed.add_field(
                        name=f"{group_title}{field_suffix}",
                        value="\n".join(current_chunk),
                        inline=False
                    )

            # Display options without emoji last
            if no_emoji_options:
                group_lines = []
                for idx, option in no_emoji_options:
                    status = "✅" if idx in active_options else "⬜"
                    group_lines.append(f"{status} {option['emoji']} **{option['title']}**")

                # Split into multiple fields if needed
                current_chunk = []
                current_length = 0
                field_count = 0

                for line in group_lines:
                    line_length = len(line) + 1
                    if current_length + line_length > 1000:
                        field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                        embed.add_field(
                            name=f"Other Options{field_suffix}",
                            value="\n".join(current_chunk),
                            inline=True
                        )
                        current_chunk = [line]
                        current_length = line_length
                        field_count += 1
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                if current_chunk:
                    field_suffix = f" ({field_count + 1})" if field_count > 0 else ""
                    embed.add_field(
                        name=f"Other Options{field_suffix}",
                        value="\n".join(current_chunk),
                        inline=False
                    )
        else:
            embed.add_field(
                name="Available Options",
                value="No options configured",
                inline=False
            )

        embed.set_footer(text=f"Selected: {len(active_options)}/3")

        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    @tradecommission.command(name="setoption")
    async def tc_setoption(
        self,
        ctx: commands.Context,
        emoji: str,
        title: str,
        *,
        description: str
    ):
        """
        Configure an option's information (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        If an option with the same title exists, it will be updated.
        Otherwise, a new option will be added.

        **Arguments:**
        - `emoji`: Emoji to use for reactions (unicode emoji or custom server emoji)
        - `title`: Title for this option (used as identifier)
        - `description`: Description/information to show when this option is selected

        **Examples:**
        - `[p]tc setoption 🔥 "Silk Road" This week's trade route is the Silk Road with 20% bonus on silk items.`
        - `[p]tc setoption :custom_emoji: "Tea Trade" Premium tea trading available.`

        **Note:** To use custom server emojis, just type them normally (e.g., :tradeicon:) and Discord will auto-convert them.
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        # Validate emoji by testing if it can be added as a reaction
        # This works for both unicode emojis and custom Discord emojis
        try:
            await ctx.message.add_reaction(emoji)
            await ctx.message.clear_reaction(emoji)
        except discord.HTTPException:
            await ctx.send(
                "❌ Invalid emoji! Make sure the emoji is:\n"
                "• A valid unicode emoji (🔥, 💎, ⚔️)\n"
                "• A custom emoji from this server or a server the bot is in\n"
                "• Properly formatted"
            )
            return

        # Check if option with this title already exists
        async with self.config.trade_options() as trade_options:
            existing_idx = None
            for idx, option in enumerate(trade_options):
                if option["title"].lower() == title.lower():
                    existing_idx = idx
                    break

            new_option = {
                "emoji": emoji,
                "title": title,
                "description": description
            }

            if existing_idx is not None:
                # Update existing option
                trade_options[existing_idx] = new_option
                await ctx.send(
                    f"✅ Option **{title}** updated!\n"
                    f"**Emoji:** {emoji}\n"
                    f"**Description:** {description[:100]}{'...' if len(description) > 100 else ''}"
                )
            else:
                # Add new option
                trade_options.append(new_option)
                await ctx.send(
                    f"✅ New option added: **{title}**\n"
                    f"**Emoji:** {emoji}\n"
                    f"**Description:** {description[:100]}{'...' if len(description) > 100 else ''}\n"
                    f"**Total options:** {len(trade_options)}"
                )

    @tradecommission.command(name="removeoption")
    async def tc_removeoption(self, ctx: commands.Context, *, title: str):
        """
        Remove an option by its title (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Arguments:**
        - `title`: Title of the option to remove

        **Example:**
        - `[p]tc removeoption Silk Road`
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        async with self.config.trade_options() as trade_options:
            # Find the option with matching title
            found_idx = None
            for idx, option in enumerate(trade_options):
                if option["title"].lower() == title.lower():
                    found_idx = idx
                    break

            if found_idx is None:
                await ctx.send(f"❌ No option found with title: **{title}**")
                return

            # Remove the option
            removed = trade_options.pop(found_idx)
            await ctx.send(
                f"✅ Option removed: **{removed['title']}**\n"
                f"**Emoji:** {removed['emoji']}\n"
                f"**Remaining options:** {len(trade_options)}"
            )

    @tradecommission.command(name="listoptions")
    async def tc_listoptions(self, ctx: commands.Context):
        """
        List all configured trade options (Global Setting).

        Shows all available options that can be used across all servers.
        Can be used in DMs by the bot owner.
        """
        trade_options = await self.config.trade_options()

        if not trade_options:
            await ctx.send(
                "❌ No options configured yet!\n\n"
                "Use `[p]tc setoption <emoji> <title> <description>` to add options."
            )
            return

        embed = discord.Embed(
            title="📋 Configured Trade Commission Options",
            description=f"**Total Options:** {len(trade_options)}\n\n"
                       "These options are available across all servers using this cog.",
            color=discord.Color.blue()
        )

        for idx, option in enumerate(trade_options, 1):
            embed.add_field(
                name=f"{idx}. {option['emoji']} {option['title']}",
                value=option['description'][:200] + ('...' if len(option['description']) > 200 else ''),
                inline=False
            )

        await ctx.send(embed=embed)

    @tradecommission.command(name="setimage")
    @commands.is_owner()
    async def tc_setimage(self, ctx: commands.Context, image_url: str):
        """
        Set the image to display when Trade Commission information is added (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Arguments:**
        - `image_url`: Direct URL to an image file (must end in .png, .jpg, .jpeg, .gif, or .webp)

        **Example:**
        - `[p]tc setimage https://example.com/trade-commission.png`

        To remove the image, use: `[p]tc setimage none`
        """
        if image_url.lower() == "none":
            await self.config.image_url.set(None)
            await ctx.send("✅ Trade Commission image removed.")
            return

        # Basic URL validation
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        if not any(image_url.lower().endswith(ext) for ext in valid_extensions):
            await ctx.send(
                f"❌ Invalid image URL! Must end with one of: {', '.join(valid_extensions)}\n"
                f"Or use `none` to remove the image."
            )
            return

        if not image_url.startswith(('http://', 'https://')):
            await ctx.send("❌ Image URL must start with http:// or https://")
            return

        await self.config.image_url.set(image_url)

        # Show preview
        embed = discord.Embed(
            title="✅ Trade Commission Image Set",
            description="This image will be displayed when information is added to the weekly message.",
            color=discord.Color.green()
        )
        embed.set_image(url=image_url)

        await ctx.send(embed=embed)

    @tradecommission.command(name="setgrouptitle")
    async def tc_setgrouptitle(self, ctx: commands.Context, emoji: str, *, title: str):
        """
        Set a custom title for an emoji-grouped option category (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        When options are grouped by their final emoji in the addinfo message,
        this allows you to customize the group name instead of just showing the emoji.

        **Arguments:**
        - `emoji`: The emoji that groups options (e.g., 🔥)
        - `title`: Custom title for this emoji group

        **Examples:**
        - `[p]tc setgrouptitle 🔥 Fire Routes`
        - `[p]tc setgrouptitle 🌊 Water Routes`
        - `[p]tc setgrouptitle ⚔️ Combat Missions`
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        # Validate emoji
        try:
            await ctx.message.add_reaction(emoji)
            await ctx.message.clear_reaction(emoji)
        except discord.HTTPException:
            await ctx.send("❌ Invalid emoji! Make sure it's a valid unicode emoji or custom Discord emoji.")
            return

        async with self.config.emoji_titles() as emoji_titles:
            emoji_titles[emoji] = title

        await ctx.send(f"✅ Set emoji group title: {emoji} → **{title}**")

    @tradecommission.command(name="removegrouptitle")
    async def tc_removegrouptitle(self, ctx: commands.Context, emoji: str):
        """
        Remove a custom title for an emoji-grouped option category (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Arguments:**
        - `emoji`: The emoji to remove the custom title from

        **Example:**
        - `[p]tc removegrouptitle 🔥`
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        async with self.config.emoji_titles() as emoji_titles:
            if emoji not in emoji_titles:
                await ctx.send(f"❌ No custom title set for {emoji}")
                return

            removed_title = emoji_titles.pop(emoji)

        await ctx.send(f"✅ Removed custom title for {emoji} (was: **{removed_title}**)")

    @tradecommission.command(name="listgrouptitles")
    async def tc_listgrouptitles(self, ctx: commands.Context):
        """
        List all custom emoji group titles (Global Setting).

        Shows all configured custom titles for emoji-grouped option categories.
        Can be used in DMs by the bot owner.
        """
        emoji_titles = await self.config.emoji_titles()

        if not emoji_titles:
            await ctx.send(
                "❌ No custom emoji group titles configured.\n\n"
                "Use `[p]tc setgrouptitle <emoji> <title>` to add custom titles."
            )
            return

        embed = discord.Embed(
            title="📋 Emoji Group Titles",
            description=f"**Total:** {len(emoji_titles)}\n\nCustom titles for emoji-grouped options:",
            color=discord.Color.blue()
        )

        for emoji, title in emoji_titles.items():
            embed.add_field(
                name=f"{emoji}",
                value=f"**{title}**",
                inline=True
            )

        await ctx.send(embed=embed)

    @tradecommission.command(name="info")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_info(self, ctx: commands.Context):
        """Show current Trade Commission configuration."""
        guild_config = await self.config.guild(ctx.guild).all()
        global_config = await self.config.all()

        embed = discord.Embed(
            title="📊 Trade Commission Configuration",
            color=discord.Color.blue(),
        )

        # Schedule info
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        channel = ctx.guild.get_channel(guild_config["channel_id"]) if guild_config["channel_id"] else None

        schedule_text = (
            f"**Status:** {'✅ Enabled' if guild_config['enabled'] else '❌ Disabled'}\n"
            f"**Channel:** {channel.mention if channel else 'Not set'}\n"
            f"**Schedule:** {days[guild_config['schedule_day']]} at {guild_config['schedule_hour']:02d}:{guild_config['schedule_minute']:02d}\n"
            f"**Timezone:** {guild_config['timezone']}"
        )
        embed.add_field(name="Schedule", value=schedule_text, inline=False)

        # Message customization info
        message_custom_text = (
            f"**Title:** {guild_config['message_title']}\n"
            f"**Initial Description:** {guild_config['initial_description'][:60]}{'...' if len(guild_config['initial_description']) > 60 else ''}\n"
            f"**Post Description:** {guild_config['post_description'][:60]}{'...' if len(guild_config['post_description']) > 60 else ''}"
        )

        # Add ping role if set
        if guild_config['ping_role_id']:
            ping_role = ctx.guild.get_role(guild_config['ping_role_id'])
            message_custom_text += f"\n**Ping Role:** {ping_role.mention if ping_role else 'Deleted Role'}"
        else:
            message_custom_text += "\n**Ping Role:** None"

        embed.add_field(name="Message Customization", value=message_custom_text, inline=False)

        # Options info (from global config)
        options_text = []
        for idx, option in enumerate(global_config["trade_options"], 1):
            options_text.append(
                f"{idx}. {option['emoji']} **{option['title']}**\n"
                f"   └ {option['description'][:80]}{'...' if len(option['description']) > 80 else ''}"
            )

        embed.add_field(
            name="Configured Options (Global)",
            value="\n\n".join(options_text) if options_text else "No options configured. Use `[p]tc setoption` to add options.",
            inline=False
        )

        # Image info (from global config)
        if global_config["image_url"]:
            embed.add_field(
                name="📸 Image",
                value=f"[View Image]({global_config['image_url']})",
                inline=False
            )

        # Allowed roles info
        allowed_role_ids = guild_config["allowed_roles"]
        if allowed_role_ids:
            roles = []
            for role_id in allowed_role_ids:
                role = ctx.guild.get_role(role_id)
                if role:
                    roles.append(role.mention)
                else:
                    roles.append(f"Deleted Role (ID: {role_id})")

            roles_text = "\n".join(f"• {role}" for role in roles)
            roles_text += "\n\n*Users with Manage Server permission also have access*"
            embed.add_field(
                name="📝 Addinfo Allowed Roles",
                value=roles_text,
                inline=False
            )

        # Current week info
        if guild_config["current_message_id"]:
            current_ch = ctx.guild.get_channel(guild_config["current_channel_id"])
            active_options = guild_config["active_options"]
            current_text = (
                f"**Channel:** {current_ch.mention if current_ch else 'Unknown'}\n"
                f"**Message ID:** {guild_config['current_message_id']}\n"
                f"**Active Options:** {len(active_options)}/3"
            )
            embed.add_field(name="Current Week", value=current_text, inline=False)

        await ctx.send(embed=embed)

    @tradecommission.command(name="testnow")
    @commands.guild_only()
    @commands.is_owner()
    async def tc_testnow(self, ctx: commands.Context):
        """[Owner only] Test sending the weekly message immediately."""
        channel_id = await self.config.guild(ctx.guild).channel_id()
        if not channel_id:
            await ctx.send("❌ No channel configured!")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Channel not found!")
            return

        await self._send_weekly_message(ctx.guild, channel)
        await ctx.send(f"✅ Test message sent to {channel.mention}")

    async def update_commission_message(self, guild: discord.Guild):
        """Update the current Trade Commission message with active options."""
        guild_config = await self.config.guild(guild).all()
        global_config = await self.config.all()

        current_msg_id = guild_config["current_message_id"]
        current_ch_id = guild_config["current_channel_id"]

        if not current_msg_id or not current_ch_id:
            return

        channel = guild.get_channel(current_ch_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(current_msg_id)
        except discord.NotFound:
            return

        # Determine embed color from ping role or default
        embed_color = discord.Color.gold()
        if guild_config["ping_role_id"]:
            ping_role = guild.get_role(guild_config["ping_role_id"])
            if ping_role and ping_role.color != discord.Color.default():
                embed_color = ping_role.color

        # Build embed with active options
        embed = discord.Embed(
            title=guild_config["message_title"],
            color=embed_color,
        )

        active_options = guild_config["active_options"]
        trade_options = global_config["trade_options"]
        image_url = global_config["image_url"]

        if active_options:
            description_parts = [guild_config["post_description"]]
            for option_idx in active_options:
                # Ensure the index is valid
                if 0 <= option_idx < len(trade_options):
                    option = trade_options[option_idx]
                    description_parts.append(f"{option['emoji']} **{option['title']}**\n{option['description']}")

            embed.description = "\n\n".join(description_parts)

            # Add image when information is present
            if image_url:
                embed.set_image(url=image_url)
        else:
            embed.description = guild_config["initial_description"]

        try:
            await message.edit(embed=embed)
        except discord.Forbidden:
            pass
