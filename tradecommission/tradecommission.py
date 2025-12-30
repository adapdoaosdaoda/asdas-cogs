"""Trade Commission weekly message cog for Where Winds Meet."""
import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list
import pytz


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
            "trade_info": {
                "option1": {"emoji": "1️⃣", "title": "Option 1", "description": ""},
                "option2": {"emoji": "2️⃣", "title": "Option 2", "description": ""},
                "option3": {"emoji": "3️⃣", "title": "Option 3", "description": ""},
            },
            "image_url": None,  # Image to display when information is added
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
            "active_options": [],  # List of option keys that are currently active
            "addinfo_message_id": None,  # The addinfo control message
            "allowed_roles": [],  # Role IDs that can use addinfo reactions
            "message_title": "📊 Weekly Trade Commission - Where Winds Meet",  # Configurable header
            "initial_description": "This week's Trade Commission information will be added soon!\n\nCheck back later for updates.",  # Before addinfo
            "post_description": "This week's Trade Commission information:",  # After addinfo
            "ping_role_id": None,  # Role to ping when posting message
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

        embed = discord.Embed(
            title=config["message_title"],
            description=config["initial_description"],
            color=discord.Color.blue(),
        )

        # Prepare content with ping if role is configured
        content = None
        if config["ping_role_id"]:
            role = guild.get_role(config["ping_role_id"])
            if role:
                content = role.mention

        try:
            message = await channel.send(content=content, embed=embed)
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

        # Get global trade info
        trade_info = await self.config.trade_info()
        active_options = await self.config.guild(ctx.guild).active_options()

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

        # Show current options
        options_text = []
        for key, info in trade_info.items():
            status = "✅" if key in active_options else "⬜"
            options_text.append(f"{status} {info['emoji']} **{info['title']}**")

        embed.add_field(
            name="Available Options",
            value="\n".join(options_text),
            inline=False
        )

        embed.set_footer(text=f"Selected: {len(active_options)}/3")

        # Send the message and add reactions
        control_msg = await ctx.send(embed=embed)

        # Store the control message ID
        await self.config.guild(ctx.guild).addinfo_message_id.set(control_msg.id)

        # Add reaction emotes
        for info in trade_info.values():
            if info["emoji"]:  # Only add if emoji is configured
                try:
                    await control_msg.add_reaction(info["emoji"])
                except (discord.HTTPException, discord.InvalidArgument):
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
        trade_info = await self.config.trade_info()
        option_key = None

        for key, info in trade_info.items():
            if str(reaction.emoji) == info["emoji"]:
                option_key = key
                break

        if not option_key:
            return

        # Toggle the option
        async with self.config.guild(guild).active_options() as active_options:
            if option_key in active_options:
                # Remove option
                active_options.remove(option_key)
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
                active_options.append(option_key)

        # Update the Trade Commission message
        await self.update_commission_message(guild)

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
        trade_info = await self.config.trade_info()
        option_key = None

        for key, info in trade_info.items():
            if str(reaction.emoji) == info["emoji"]:
                option_key = key
                break

        if not option_key:
            return

        # Remove the option if it's active
        async with self.config.guild(guild).active_options() as active_options:
            if option_key in active_options:
                active_options.remove(option_key)

        # Update the Trade Commission message
        await self.update_commission_message(guild)

        # Update the control message
        await self._update_addinfo_message(guild, reaction.message)

    async def _update_addinfo_message(self, guild: discord.Guild, message: discord.Message):
        """Update the addinfo control message."""
        trade_info = await self.config.trade_info()
        active_options = await self.config.guild(guild).active_options()

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

        # Show current options
        options_text = []
        for key, info in trade_info.items():
            status = "✅" if key in active_options else "⬜"
            options_text.append(f"{status} {info['emoji']} **{info['title']}**")

        embed.add_field(
            name="Available Options",
            value="\n".join(options_text),
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
        option_number: int,
        emoji: str,
        title: str,
        *,
        description: str
    ):
        """
        Configure an option's information (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Arguments:**
        - `option_number`: Option number (1, 2, or 3)
        - `emoji`: Emoji to use for reactions (unicode emoji or custom server emoji)
        - `title`: Title for this option
        - `description`: Description/information to show when this option is selected

        **Examples:**
        - `[p]tc setoption 1 🔥 "Silk Road" This week's trade route is the Silk Road with 20% bonus on silk items.`
        - `[p]tc setoption 2 :custom_emoji: "Tea Trade" Premium tea trading available.`

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

        if option_number not in [1, 2, 3]:
            await ctx.send("❌ Option number must be 1, 2, or 3!")
            return

        # Validate emoji by testing if it can be added as a reaction
        # This works for both unicode emojis and custom Discord emojis
        test_emoji = emoji

        # Try to add it as a reaction to verify it's valid
        try:
            await ctx.message.add_reaction(test_emoji)
            await ctx.message.clear_reaction(test_emoji)
        except (discord.HTTPException, discord.InvalidArgument):
            await ctx.send(
                "❌ Invalid emoji! Make sure the emoji is:\n"
                "• A valid unicode emoji (🔥, 💎, ⚔️)\n"
                "• A custom emoji from this server or a server the bot is in\n"
                "• Properly formatted"
            )
            return

        option_key = f"option{option_number}"
        async with self.config.trade_info() as trade_info:
            trade_info[option_key]["emoji"] = emoji
            trade_info[option_key]["title"] = title
            trade_info[option_key]["description"] = description

        await ctx.send(
            f"✅ Option {option_number} configured!\n"
            f"**Emoji:** {emoji}\n"
            f"**Title:** {title}\n"
            f"**Description:** {description[:100]}{'...' if len(description) > 100 else ''}"
        )

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
        for key, info in global_config["trade_info"].items():
            options_text.append(
                f"{info['emoji']} **{info['title']}**\n"
                f"└ {info['description'][:80]}{'...' if len(info['description']) > 80 else ''}"
            )

        embed.add_field(
            name="Configured Options (Global)",
            value="\n\n".join(options_text) if options_text else "No options configured",
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

        # Build embed with active options
        embed = discord.Embed(
            title=guild_config["message_title"],
            color=discord.Color.gold(),
        )

        active_options = guild_config["active_options"]
        trade_info = global_config["trade_info"]
        image_url = global_config["image_url"]

        if active_options:
            description_parts = [guild_config["post_description"] + "\n"]
            for option_key in active_options:
                info = trade_info[option_key]
                description_parts.append(f"\n{info['emoji']} **{info['title']}**\n{info['description']}")

            embed.description = "\n".join(description_parts)

            # Add image when information is present
            if image_url:
                embed.set_image(url=image_url)
        else:
            embed.description = guild_config["initial_description"]

        try:
            await message.edit(embed=embed)
        except discord.Forbidden:
            pass
