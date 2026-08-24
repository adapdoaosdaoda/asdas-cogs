"""Trade Commission weekly message cog for Where Winds Meet."""
import asyncio
import discord
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list
from discord.ext import tasks
import pytz
import re

log = logging.getLogger("red.asdas-cogs.tradecommission")

# Unicode emoji pattern - matches standard emoji characters
EMOJI_PATTERN = re.compile(
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

def extract_final_emoji(text: str) -> Optional[str]:
    """Extract the final emoji from a text string.

    Args:
        text: The text to extract emoji from

    Returns:
        The final emoji found in the text, or None if no emoji found
    """
    # Find all emojis in the text
    emojis = EMOJI_PATTERN.findall(text)

    # Return the last emoji found, or None if no emojis
    return emojis[-1] if emojis else None


class AddInfoView(discord.ui.View):
    """View for adding Trade Commission information with dropdowns organized by category."""

    def __init__(self, cog: "TradeCommission", guild: discord.Guild, trade_options: List[Dict], active_options: List[int], emoji_titles: Dict[str, str], allowed_user_id: int, track_message: bool = True):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.guild = guild
        self.trade_options = trade_options
        self.active_options = active_options
        self.allowed_user_id = allowed_user_id
        # Whether this view's message is the single tracked "official" addinfo panel
        # (addinfo_message_id). Ephemeral copies (e.g. from the notifier button) must not
        # participate in that tracking, since Discord won't let the bot delete/fetch an
        # ephemeral message from another interaction context.
        self.track_message = track_message

        # Group options by their final emoji for organized display
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

        # Create 3 dropdowns for the 3 option slots
        for slot_num in range(3):
            # Create select options organized by category (vertically)
            select_options = [
                discord.SelectOption(
                    label="(Empty)",
                    value="-1",
                    emoji="❌"
                )
            ]

            # Add options grouped by category (emoji groups first, sorted)
            for category_emoji in sorted(emoji_groups.keys()):
                options_list = emoji_groups[category_emoji]
                for idx, option in options_list:
                    # Don't include description - only label and emoji
                    select_options.append(
                        discord.SelectOption(
                            label=option['title'][:100],  # Discord label limit
                            value=str(idx),
                            emoji=option['emoji'],
                            default=(idx == active_options[slot_num] if slot_num < len(active_options) else False)
                        )
                    )

            # Add options without category emoji last
            for idx, option in no_emoji_options:
                select_options.append(
                    discord.SelectOption(
                        label=option['title'][:100],
                        value=str(idx),
                        emoji=option['emoji'],
                        default=(idx == active_options[slot_num] if slot_num < len(active_options) else False)
                    )
                )

            # Limit to 25 options (Discord limit)
            select_options = select_options[:25]

            # Create the select menu
            select = discord.ui.Select(
                placeholder=f"Option {slot_num + 1}: " + (
                    trade_options[active_options[slot_num]]['title'][:80]
                    if slot_num < len(active_options) and active_options[slot_num] < len(trade_options)
                    else "Not selected"
                ),
                options=select_options,
                custom_id=f"tc_slot_{slot_num}",
                row=slot_num
            )
            select.callback = self._create_select_callback(slot_num)
            self.add_item(select)

        # Add cancel button in row 3
        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id="tc_cancel",
            row=3
        )
        cancel_button.callback = self._cancel_callback
        self.add_item(cancel_button)

    async def _cancel_callback(self, interaction: discord.Interaction):
        """Handle cancel button click."""
        # Check if user is allowed to interact
        if interaction.user.id != self.allowed_user_id:
            await interaction.response.send_message("❌ Only the user who called this command can use these controls!", ephemeral=True)
            return

        # Check permissions
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ This can only be used in a server!", ephemeral=True)
            return

        if not await self.cog._has_addinfo_permission(member):
            await interaction.response.send_message("❌ You don't have permission to use this!", ephemeral=True)
            return

        if not self.track_message:
            # Ephemeral copy: nothing tracked in config, just dismiss this message.
            await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)
            return

        # Delete the addinfo message
        try:
            await self.cog.config.guild(self.guild).addinfo_message_id.set(None)
            await interaction.message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("❌ Failed to close the panel.", ephemeral=True)

    def _create_select_callback(self, slot_num: int):
        """Create a callback function for a specific dropdown slot."""
        async def callback(interaction: discord.Interaction):
            # Check if user is allowed to interact
            if interaction.user.id != self.allowed_user_id:
                await interaction.response.send_message("❌ Only the user who called this command can use these controls!", ephemeral=True)
                return

            # Check permissions
            member = interaction.user
            if not isinstance(member, discord.Member):
                await interaction.response.send_message("❌ This can only be used in a server!", ephemeral=True)
                return

            if not await self.cog._has_addinfo_permission(member):
                await interaction.response.send_message("❌ You don't have permission to use this!", ephemeral=True)
                return

            # Get the selected value
            select = interaction.data.get('values', [])[0] if interaction.data.get('values') else None
            if select is None:
                return

            selected_idx = int(select)

            # Update active options
            async with self.cog.config.guild(self.guild).active_options() as active_options:
                # Ensure the list has enough slots
                while len(active_options) <= slot_num:
                    active_options.append(-1)

                if selected_idx == -1:
                    # Clear this slot
                    active_options[slot_num] = -1
                else:
                    # Check if this option is already selected in another slot
                    if selected_idx in active_options and active_options.index(selected_idx) != slot_num:
                        await interaction.response.send_message(
                            f"❌ This option is already selected in Slot {active_options.index(selected_idx) + 1}!",
                            ephemeral=True
                        )
                        return

                    # Set this slot
                    active_options[slot_num] = selected_idx

                # Remove any -1 values and keep only valid selections
                self.active_options = [opt for opt in active_options if opt != -1]
                # Update config with cleaned list
                active_options.clear()
                active_options.extend(self.active_options)

            # Update the Trade Commission message
            await self.cog.update_commission_message(self.guild)

            # Check if we now have 3 options selected
            if len(self.active_options) == 3:
                # Send notification message
                try:
                    guild_config = await self.cog.config.guild(self.guild).all()
                    current_channel = self.guild.get_channel(guild_config["current_channel_id"])

                    if current_channel:
                        # Delete old notification if it exists
                        old_notification_id = guild_config["notification_message_id"]
                        if old_notification_id:
                            try:
                                old_notification = await current_channel.fetch_message(old_notification_id)
                                await old_notification.delete()
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                pass

                        # Send new notification
                        notification_content = guild_config["notification_message"]

                        notification_msg = await current_channel.send(notification_content, allowed_mentions=discord.AllowedMentions(roles=True))

                        # Notify owners
                        await self.cog._send_log(
                            self.guild,
                            f"📢 **Weekly Trade Commission** announcement posted in **{self.guild.name}** ({current_channel.mention})"
                        )

                        # Store notification message ID
                        await self.cog.config.guild(self.guild).notification_message_id.set(notification_msg.id)

                        # Schedule deletion after 3 hours
                        asyncio.create_task(
                            self.cog._delete_notification_after_delay(
                                self.guild, current_channel, notification_msg.id, 3 * 3600
                            )
                        )
                except (discord.Forbidden, discord.HTTPException):
                    pass  # Couldn't send notification

                # Close the addinfo panel
                if self.track_message:
                    try:
                        await interaction.message.delete()
                        await self.cog.config.guild(self.guild).addinfo_message_id.set(None)
                        await interaction.response.send_message("✅ All 3 options selected! The addinfo panel has been closed.", ephemeral=True)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                else:
                    try:
                        await interaction.response.edit_message(
                            content="✅ All 3 options selected! The Trade Commission message has been updated.",
                            embed=None, view=None
                        )
                    except discord.HTTPException:
                        pass

                # Data has replaced the placeholder - stop nagging
                await self.cog.config.guild(self.guild).placeholder_posted_at.set(None)
                await self.cog.config.guild(self.guild).addinfo_reminders_sent.set(0)
                await self.cog._clear_addinfo_log_button(self.guild)
                return
            else:
                # Recreate the view with updated selections
                emoji_titles = await self.cog.config.emoji_titles()
                new_view = AddInfoView(self.cog, self.guild, self.trade_options, self.active_options, emoji_titles, self.allowed_user_id, track_message=self.track_message)

                # Get updated embed
                embed = await self.cog._create_addinfo_embed(self.guild, self.trade_options, self.active_options)

                # Update the message
                try:
                    await interaction.response.edit_message(embed=embed, view=new_view)
                except discord.HTTPException:
                    pass

        return callback


class AddInfoLogButtonView(discord.ui.View):
    """Attached to the placeholder-posted / reminder log messages so admins can fill in
    addinfo directly from the log channel, without needing to run `[p]tc addinfo` in the
    Trade Commission channel itself. Opens the addinfo panel as an ephemeral message,
    private to whoever clicks."""

    def __init__(self, cog: "TradeCommission", guild: discord.Guild):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild

    @discord.ui.button(label="Add Info", style=discord.ButtonStyle.primary, emoji="📝", custom_id="tc_log_addinfo")
    async def add_info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            member = self.guild.get_member(interaction.user.id)
        if not member or not await self.cog._has_addinfo_permission(member):
            await interaction.response.send_message("❌ You don't have permission to use addinfo!", ephemeral=True)
            return

        current_msg_id = await self.cog.config.guild(self.guild).current_message_id()
        current_ch_id = await self.cog.config.guild(self.guild).current_channel_id()
        if not current_msg_id or not current_ch_id:
            await interaction.response.send_message("❌ No current Trade Commission message found! Use `[p]tc post` first.", ephemeral=True)
            return

        trade_options = await self.cog.config.trade_options()
        if not trade_options:
            await interaction.response.send_message("❌ No trade options configured! Use `[p]tc setoption` to add options first.", ephemeral=True)
            return

        active_options = await self.cog.config.guild(self.guild).active_options()
        emoji_titles = await self.cog.config.emoji_titles()

        embed = await self.cog._create_addinfo_embed(self.guild, trade_options, active_options)
        view = AddInfoView(self.cog, self.guild, trade_options, active_options, emoji_titles, member.id, track_message=False)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


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
            "log_channel_id": None,
            "addinfo_log_message": None,  # {"channel_id": int, "message_id": int} of the latest log message with a live Add Info button
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
            "last_sent": None,
            "last_sunday_notification": None,
            "last_wednesday_notification": None,

            # Addinfo reminder nagging (pesters owners until placeholder is replaced with real data)
            "placeholder_posted_at": None,  # ISO timestamp of when the current placeholder was posted
            "addinfo_reminders_sent": 3,  # How many of the (up to 3) reminders have been sent for the current placeholder

            # Sunday pre-shop restock notification
            "sunday_enabled": False,
            "sunday_hour": 19,
            "sunday_minute": 0,
            "sunday_message": "🔔 **Pre-Shop Restock Reminder!**\n\nThe shop will be restocking {timestamp}! Get ready!",
            "sunday_ping_role_id": None,
            "sunday_event_hour": 21,  # Hour when the actual event happens (in configured timezone, default 21:00 for shop restock)

            # Wednesday sell recommendation notification
            "wednesday_enabled": False,
            "wednesday_hour": 19,
            "wednesday_minute": 0,
            "wednesday_message": "📈 **Recommended to Sell Now!**\n\nIt's Wednesday! Best time to sell is {timestamp}!",
            "wednesday_ping_role_id": None,
            "wednesday_event_hour": 22,  # Hour when the actual event happens (in configured timezone, default 22:00 for sell time)
        }

        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self._ready = False

    async def cog_load(self):
        """Start the background task when cog loads."""
        self._ready = True
        self.check_schedule_loop.start()

    async def cog_unload(self):
        """Cancel background task when cog unloads."""
        self.check_schedule_loop.cancel()

    async def _send_log(self, guild: discord.Guild, msg: str, view: Optional[discord.ui.View] = None):
        """Send a bot-status message to the owners (DM) and the configured log channel, if any.

        `view` (if given) is only attached to the log-channel post, not the owner DM. If it's an
        AddInfoLogButtonView, the button is stripped from the previous such message first, so only
        the newest reminder ever has a live Add Info button.
        """
        try:
            await self.bot.send_to_owners(msg)
        except Exception:
            pass
        log_channel_id = await self.config.guild(guild).log_channel_id()
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if channel:
                if isinstance(view, AddInfoLogButtonView):
                    await self._clear_addinfo_log_button(guild)
                try:
                    sent = await channel.send(msg, view=view)
                    if isinstance(view, AddInfoLogButtonView):
                        await self.config.guild(guild).addinfo_log_message.set(
                            {"channel_id": channel.id, "message_id": sent.id}
                        )
                except discord.HTTPException:
                    log.warning(f"Failed to send log message to configured log channel in {guild.name}")

    async def _clear_addinfo_log_button(self, guild: discord.Guild):
        """Strip the Add Info button from the currently tracked log message, if any."""
        tracked = await self.config.guild(guild).addinfo_log_message()
        if not tracked:
            return
        await self.config.guild(guild).addinfo_log_message.set(None)
        channel = guild.get_channel(tracked["channel_id"])
        if not channel:
            return
        try:
            message = await channel.fetch_message(tracked["message_id"])
            await message.edit(view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

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

    async def _get_embed_color(self, guild: discord.Guild, ping_role_id: Optional[int]) -> discord.Color:
        """Get the embed color based on priority: ping role -> bot color -> default color.

        Priority:
        1. Ping role color (if set and not default)
        2. Bot's color (if set and not default)
        3. Default fallback color (#58b99c)
        """
        # Try ping role color first
        if ping_role_id:
            ping_role = guild.get_role(ping_role_id)
            if ping_role and ping_role.color != discord.Color.default():
                return ping_role.color

        # Try bot's color
        bot_member = guild.get_member(self.bot.user.id)
        if bot_member and bot_member.color != discord.Color.default():
            return bot_member.color

        # Fallback to default color
        return discord.Color(0x58b99c)

    async def _delete_notification_after_delay(self, guild: discord.Guild, channel: discord.TextChannel, message_id: int, delay_seconds: int):
        """Delete a notification message after a specified delay in seconds."""
        try:
            await asyncio.sleep(delay_seconds)
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
                await self.config.guild(guild).notification_message_id.set(None)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or no permission
        except asyncio.CancelledError:
            pass  # Task was cancelled

    async def _create_addinfo_embed(self, guild: discord.Guild, trade_options: List[Dict], active_options: List[int]) -> discord.Embed:
        """Create the embed for the addinfo message."""
        emoji_titles = await self.config.emoji_titles()

        embed = discord.Embed(
            title="📝 Add Trade Commission Information",
            description=(
                "Use the **3 dropdowns** below to select options for this week's Trade Commission message.\n\n"
                "Options are organized by category within each dropdown.\n\n"
                "Select an option from each dropdown to fill all 3 slots.\n\n"
                "**Note:** Only you can interact with these controls."
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

        # Build all option lines grouped by category
        all_groups = []

        # Add emoji groups first (sorted)
        for category_emoji in sorted(emoji_groups.keys()):
            options_list = emoji_groups[category_emoji]
            group_title = emoji_titles.get(category_emoji, f"{category_emoji} Options")

            group_data = {
                'title': group_title,
                'lines': []
            }

            for idx, option in options_list:
                status = "✅" if idx in active_options else "⬜"
                group_data['lines'].append(f"{status} {option['emoji']} **{option['title']}**")

            all_groups.append(group_data)

        # Add options without emoji last
        if no_emoji_options:
            group_data = {
                'title': "Other Options",
                'lines': []
            }

            for idx, option in no_emoji_options:
                status = "✅" if idx in active_options else "⬜"
                group_data['lines'].append(f"{status} {option['emoji']} **{option['title']}**")

            all_groups.append(group_data)

        # Split groups into 2 columns
        if all_groups:
            # Calculate split point for roughly equal columns
            total_groups = len(all_groups)
            mid_point = (total_groups + 1) // 2

            # Column 1 (left)
            column1_content = []
            for group in all_groups[:mid_point]:
                column1_content.append(f"**{group['title']}**")
                column1_content.extend(group['lines'])
                column1_content.append("")  # Spacing between groups

            # Column 2 (right)
            column2_content = []
            for group in all_groups[mid_point:]:
                column2_content.append(f"**{group['title']}**")
                column2_content.extend(group['lines'])
                column2_content.append("")  # Spacing between groups

            # Add fields for 2 columns
            if column1_content:
                embed.add_field(
                    name="Available Options (1/2)",
                    value="\n".join(column1_content).strip() or "No options",
                    inline=True
                )

            if column2_content:
                embed.add_field(
                    name="Available Options (2/2)",
                    value="\n".join(column2_content).strip() or "No options",
                    inline=True
                )
        else:
            embed.add_field(
                name="Available Options",
                value="No options configured",
                inline=False
            )

        embed.set_footer(text=f"Selected: {len(active_options)}/3")

        return embed

    @tasks.loop(minutes=1)
    async def check_schedule_loop(self):
        """Background loop to check for scheduled messages."""
        for guild in self.bot.guilds:
            try:
                await self._check_guild_schedule(guild)
            except Exception as e:
                print(f"Error in Trade Commission schedule check for guild {guild.id}: {e}")

    @check_schedule_loop.before_loop
    async def before_check_schedule_loop(self):
        await self.bot.wait_until_ready()

    async def _check_guild_schedule(self, guild: discord.Guild):
        """Check if it's time to send the weekly message or scheduled notifications for a guild."""
        config = await self.config.guild(guild).all()

        if not config["channel_id"]:
            return

        channel = guild.get_channel(config["channel_id"])
        if not channel:
            return

        # Get timezone
        try:
            tz = pytz.timezone(config["timezone"])
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC

        now = datetime.now(tz)

        # 1. Check weekly message (only if enabled)
        if config["enabled"]:
            # Find the most recent scheduled time
            target_day = config["schedule_day"]
            target_hour = config["schedule_hour"]
            target_minute = config["schedule_minute"]
            
            target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            days_back = (now.weekday() - target_day) % 7
            if days_back == 0 and now < target_time:
                days_back = 7
            target_time -= timedelta(days=days_back)

            last_sent_str = config["last_sent"]
            should_send = False
            if not last_sent_str:
                # If never sent, only send if we are in the scheduled minute window now
                if now.weekday() == target_day and now.hour == target_hour and abs(now.minute - target_minute) < 2:
                    should_send = True
                else:
                    # Just initialize last_sent to prevent double posting on first setup
                    await self.config.guild(guild).last_sent.set(target_time.isoformat())
            else:
                last_sent = datetime.fromisoformat(last_sent_str)
                if last_sent.tzinfo is None:
                    last_sent = tz.localize(last_sent)
                
                # If the most recent target_time hasn't been met yet
                if last_sent < target_time:
                    # Catch-up logic: only auto-post if it's within 24 hours of the scheduled time
                    if now < target_time + timedelta(hours=24):
                        should_send = True
                    else:
                        # Too late to auto-post, just update last_sent to target_time to skip this week
                        await self.config.guild(guild).last_sent.set(target_time.isoformat())

            if should_send:
                await self._send_weekly_message(guild, channel)

            # Nag owners every 12 hours (up to 3 times) until the placeholder is replaced with real data
            await self._check_addinfo_reminder(guild)

        # 2. Check Sunday pre-shop restock notification (weekday 6 = Sunday)
        if config["sunday_enabled"]:
            target_hour = config["sunday_hour"]
            target_minute = config["sunday_minute"]
            
            # Use same logic to find most recent target Sunday
            target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            days_back = (now.weekday() - 6) % 7
            if days_back == 0 and now < target_time:
                days_back = 7
            target_time -= timedelta(days=days_back)

            last_sunday_str = config["last_sunday_notification"]
            should_notify = False
            if not last_sunday_str:
                if now.weekday() == 6 and now.hour == target_hour and abs(now.minute - target_minute) < 2:
                    should_notify = True
                else:
                    await self.config.guild(guild).last_sunday_notification.set(target_time.isoformat())
            else:
                last_sunday = datetime.fromisoformat(last_sunday_str)
                if last_sunday.tzinfo is None: last_sunday = tz.localize(last_sunday)
                if last_sunday < target_time and now < target_time + timedelta(hours=4):
                    should_notify = True

            if should_notify:
                # Calculate event timestamp (hard set to 21:00 UTC as requested)
                event_time = pytz.UTC.localize(datetime(now.year, now.month, now.day, 21, 0, 0))
                if event_time < now:
                    event_time += timedelta(days=1)
                    event_time = pytz.UTC.normalize(event_time)
                event_timestamp = int(event_time.timestamp())

                await self._send_scheduled_notification(
                    channel,
                    config["sunday_message"],
                    config["sunday_ping_role_id"],
                    guild,
                    event_timestamp
                )
                await self.config.guild(guild).last_sunday_notification.set(target_time.isoformat())

        # 3. Check Wednesday sell recommendation notification (weekday 2 = Wednesday)
        if config["wednesday_enabled"]:
            target_hour = config["wednesday_hour"]
            target_minute = config["wednesday_minute"]
            
            target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            days_back = (now.weekday() - 2) % 7
            if days_back == 0 and now < target_time:
                days_back = 7
            target_time -= timedelta(days=days_back)

            last_wednesday_str = config["last_wednesday_notification"]
            should_notify = False
            if not last_wednesday_str:
                if now.weekday() == 2 and now.hour == target_hour and abs(now.minute - target_minute) < 2:
                    should_notify = True
                else:
                    await self.config.guild(guild).last_wednesday_notification.set(target_time.isoformat())
            else:
                last_wednesday = datetime.fromisoformat(last_wednesday_str)
                if last_wednesday.tzinfo is None: last_wednesday = tz.localize(last_wednesday)
                if last_wednesday < target_time and now < target_time + timedelta(hours=4):
                    should_notify = True

            if should_notify:
                # Calculate event timestamp (hard set to 22:00 UTC as requested)
                event_time = pytz.UTC.localize(datetime(now.year, now.month, now.day, 22, 0, 0))
                if event_time < now:
                    event_time += timedelta(days=1)
                    event_time = pytz.UTC.normalize(event_time)
                event_timestamp = int(event_time.timestamp())

                await self._send_scheduled_notification(
                    channel,
                    config["wednesday_message"],
                    config["wednesday_ping_role_id"],
                    guild,
                    event_timestamp
                )
                await self.config.guild(guild).last_wednesday_notification.set(target_time.isoformat())

    async def _send_weekly_message(self, guild: discord.Guild, channel: discord.TextChannel):
        """Send the weekly Trade Commission message."""
        # Clear active options for new week
        await self.config.guild(guild).active_options.clear()

        config = await self.config.guild(guild).all()

        # Delete previous week's message (which is currently stored as current_message_id)
        if config["current_message_id"]:
            try:
                prev_channel = guild.get_channel(config["current_channel_id"]) or channel
                prev_message = await prev_channel.fetch_message(config["current_message_id"])
                await prev_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or no permission

        # Determine embed color using priority: ping role -> bot color -> default
        embed_color = await self._get_embed_color(guild, config["ping_role_id"])


        embed = discord.Embed(
            title=config["message_title"],
            description=config["initial_description"],
            color=embed_color,
        )

        # Add configured image if available
        image_url = await self.config.image_url()
        if image_url:
            embed.set_image(url=image_url)

        # Prepare content with ping if role is configured
        content = None
        if config["ping_role_id"]:
            role = guild.get_role(config["ping_role_id"])
            if role:
                content = role.mention

        try:
            message = await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))

            # Notify owners
            await self._send_log(
                guild,
                f"📢 **Weekly Trade Commission** placeholder posted in **{guild.name}** ({channel.mention})",
                view=AddInfoLogButtonView(self, guild)
            )

            # Store current message as previous for next week
            await self.config.guild(guild).previous_message_id.set(config["current_message_id"])
            # Set new current message
            await self.config.guild(guild).current_message_id.set(message.id)
            await self.config.guild(guild).current_channel_id.set(channel.id)
            
            # Update last_sent to prevent double-posting
            try:
                tz = pytz.timezone(config["timezone"])
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC
            now = datetime.now(tz)
            await self.config.guild(guild).last_sent.set(now.isoformat())

            # Reset addinfo reminder nagging for this new placeholder
            await self.config.guild(guild).placeholder_posted_at.set(now.isoformat())
            await self.config.guild(guild).addinfo_reminders_sent.set(0)
        except discord.Forbidden:
            pass

    async def _check_addinfo_reminder(self, guild: discord.Guild):
        """Pester the owners every 12 hours (up to 3 times) until addinfo replaces the placeholder."""
        placeholder_posted_at = await self.config.guild(guild).placeholder_posted_at()
        if not placeholder_posted_at:
            return

        reminders_sent = await self.config.guild(guild).addinfo_reminders_sent()
        if reminders_sent >= 3:
            return

        posted_at = datetime.fromisoformat(placeholder_posted_at)
        now = datetime.now(posted_at.tzinfo) if posted_at.tzinfo else datetime.now()

        due_reminders = int((now - posted_at).total_seconds() // (12 * 3600))
        if due_reminders <= reminders_sent:
            return

        await self._send_log(
            guild,
            f"⏰ **Reminder:** The Trade Commission placeholder in **{guild.name}** still needs "
            f"`addinfo` to fill in this week's options! (Reminder {reminders_sent + 1}/3)",
            view=AddInfoLogButtonView(self, guild)
        )

        await self.config.guild(guild).addinfo_reminders_sent.set(reminders_sent + 1)

    async def _send_scheduled_notification(
        self,
        channel: discord.TextChannel,
        message: str,
        ping_role_id: Optional[int],
        guild: discord.Guild,
        event_timestamp: Optional[int] = None
    ):
        """Send a scheduled notification message to the channel.

        Args:
            channel: The channel to send the notification to
            message: The message text (can include {timestamp} placeholder)
            ping_role_id: Optional role ID to ping
            guild: The guild
            event_timestamp: Optional Unix timestamp for the event (used for {timestamp} replacement and deletion timing)
        """
        try:
            content = message

            # Replace {timestamp} placeholder with Discord timestamp format
            if event_timestamp and "{timestamp}" in content:
                # Use relative time format (<t:timestamp:R>)
                discord_timestamp = f"<t:{event_timestamp}:R>"
                content = content.replace("{timestamp}", discord_timestamp)

            # Add role ping if configured
            if ping_role_id:
                role = guild.get_role(ping_role_id)
                if role:
                    content = f"{role.mention}\n\n{content}"

            notification_msg = await channel.send(content, allowed_mentions=discord.AllowedMentions(roles=True))

            # Schedule deletion at event time
            if event_timestamp:
                # Calculate delay in seconds until event time
                current_timestamp = int(datetime.now().timestamp())
                delay_seconds = max(0, event_timestamp - current_timestamp)
            else:
                # Fallback to 3 hours if no event timestamp provided
                delay_seconds = 3 * 3600

            asyncio.create_task(
                self._delete_notification_after_delay(
                    guild, channel, notification_msg.id, delay_seconds
                )
            )
        except discord.Forbidden:
            print(f"Missing permissions to send notification in {channel.name}")
        except discord.HTTPException as e:
            print(f"Error sending notification: {e}")

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
        timezone: str = "UTC+1"
    ):
        """
        Schedule weekly Trade Commission messages.

        **Arguments:**
        - `channel`: The channel to send messages to
        - `day`: Day of week (Monday, Tuesday, etc.)
        - `hour`: Hour in 24h format (0-23)
        - `minute`: Minute (0-59), default 0
        - `timezone`: Timezone (e.g., UTC+1, America/New_York), default UTC+1

        **Example:**
        - `[p]tc schedule #trade-info Monday 9 0 Europe/Berlin`
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
            await ctx.send(f"Invalid timezone! Use a valid timezone like UTC+1 or Europe/Berlin.")
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

    @tradecommission.command(name="setlogchannel")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_setlogchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel that receives owner-status log messages (posted/reminder notices). Leave empty to disable."""
        if channel:
            await self.config.guild(ctx.guild).log_channel_id.set(channel.id)
            await ctx.send(f"✅ Log messages will also be sent to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).log_channel_id.set(None)
            await ctx.send("✅ Log channel disabled. Messages will only be sent to the bot owner(s).")

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

    @tradecommission.command(name="setnotification")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
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
        Add information to the current week's Trade Commission message via buttons.

        This will create a message with dropdowns in the current channel.
        Only you can interact with the dropdowns to select up to 3 options.
        """
        # Check if user has permission
        if not await self._has_addinfo_permission(ctx.author):
            await ctx.send("❌ You don't have permission to use addinfo!")
            return

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

        # Get global trade options
        trade_options = await self.config.trade_options()
        active_options = await self.config.guild(ctx.guild).active_options()

        if not trade_options:
            await ctx.send("❌ No trade options configured! Use `[p]tc setoption` to add options first.")
            return

        # Create the embed
        embed = await self._create_addinfo_embed(ctx.guild, trade_options, active_options)

        # Get emoji titles for the view
        emoji_titles = await self.config.emoji_titles()

        # Create the view with buttons (limited to the command caller)
        view = AddInfoView(self, ctx.guild, trade_options, active_options, emoji_titles, ctx.author.id)

        # Send the addinfo panel to the current channel
        control_msg = await ctx.send(embed=embed, view=view)

        # Store the control message ID
        await self.config.guild(ctx.guild).addinfo_message_id.set(control_msg.id)

        # React to the command with a checkmark
        await ctx.message.add_reaction("✅")

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
    async def tc_setimage(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Set the image to display in Trade Commission messages (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Usage:**
        1. Attach an image to your message (no URL needed)
        2. Provide a direct image URL as an argument
        3. Use "none" to remove the current image

        **Examples:**
        - `[p]tc setimage` (with image attached)
        - `[p]tc setimage https://example.com/trade-commission.png`
        - `[p]tc setimage none` (to remove)

        **Note:** The image will be displayed on both the initial post and when options are added.
        """
        # Check if user wants to remove the image
        if image_url and image_url.lower() == "none":
            await self.config.image_url.set(None)
            await ctx.send("✅ Trade Commission image removed.")
            return

        # Check for image attachment first
        final_url = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]

            # Validate that it's an image
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                await ctx.send(
                    "❌ The attached file is not an image!\n"
                    "Please attach a valid image file (PNG, JPG, GIF, or WebP)."
                )
                return

            # Use the attachment URL
            final_url = attachment.url

        # If no attachment, check for URL parameter
        elif image_url:
            # Basic URL validation
            valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

            if not image_url.startswith(('http://', 'https://')):
                await ctx.send("❌ Image URL must start with http:// or https://")
                return

            # Check if URL ends with valid extension (less strict - query params are ok)
            url_lower = image_url.lower().split('?')[0]  # Remove query params for extension check
            if not any(url_lower.endswith(ext) for ext in valid_extensions):
                await ctx.send(
                    f"❌ Invalid image URL! URL should point to an image file.\n"
                    f"Supported formats: {', '.join(valid_extensions)}\n\n"
                    f"**Tip:** You can also attach an image directly to this command instead of using a URL."
                )
                return

            final_url = image_url

        # If neither attachment nor URL provided
        else:
            await ctx.send(
                "❌ No image provided!\n\n"
                "**Usage:**\n"
                "• Attach an image file to your message, or\n"
                "• Provide an image URL as an argument\n\n"
                "**Examples:**\n"
                "• `[p]tc setimage` (with image attached)\n"
                "• `[p]tc setimage https://example.com/image.png`\n"
                "• `[p]tc setimage none` (to remove current image)"
            )
            return

        # Test the URL by trying to set it in an embed
        test_embed = discord.Embed(title="Testing image...")
        try:
            test_embed.set_image(url=final_url)
        except Exception as e:
            await ctx.send(f"❌ Invalid image URL: {e}")
            return

        # Save the image URL
        await self.config.image_url.set(final_url)

        # Show preview
        embed = discord.Embed(
            title="✅ Trade Commission Image Set",
            description=(
                "This image will be displayed in Trade Commission messages.\n\n"
                "**Image will appear:**\n"
                "• In the initial weekly post\n"
                "• When options are added via addinfo"
            ),
            color=discord.Color.green()
        )
        embed.set_image(url=final_url)

        if ctx.message.attachments:
            embed.set_footer(text="⚠️ Warning: Discord attachment URLs may expire. Consider using a permanent image host.")

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
    async def tc_info(self, ctx: commands.Context, full: bool = False):
        """Show current Trade Commission configuration.

        **Arguments:**
        - `full`: Show full Sunday/Wednesday messages (default: False)

        **Examples:**
        - `[p]tc info` - Show config with truncated messages
        - `[p]tc info true` - Show config with full messages
        
        **Note:** For a cleaner view of just Sunday or Wednesday settings, use:
        - `[p]tc sunday info`
        - `[p]tc wednesday info`
        """
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

        # Notification message info
        notification_text = (
            f"**Message:** {guild_config['notification_message'][:100]}{'...' if len(guild_config['notification_message']) > 100 else ''}\n"
            f"**Auto-delete:** After 3 hours"
        )
        embed.add_field(name="🔔 Notification (when 3 options selected)", value=notification_text, inline=False)

        # Sunday pre-shop restock notification
        sunday_role = ctx.guild.get_role(guild_config["sunday_ping_role_id"]) if guild_config["sunday_ping_role_id"] else None
        sunday_role_text = sunday_role.mention if sunday_role else "None"

        # Show full or truncated message based on 'full' parameter
        sunday_message = guild_config['sunday_message']
        if not full and len(sunday_message) > 80:
            sunday_message_display = sunday_message[:80] + '...'
        else:
            sunday_message_display = sunday_message

        sunday_text = (
            f"**Enabled:** {'✅ Yes' if guild_config['sunday_enabled'] else '❌ No'}\n"
            f"**Notification Time:** {guild_config['sunday_hour']:02d}:{guild_config['sunday_minute']:02d}\n"
            f"**Event Time:** {guild_config['sunday_event_hour']:02d}:00 {guild_config['timezone']}\n"
            f"**Ping Role:** {sunday_role_text}\n"
            f"**Message:** {sunday_message_display}"
        )
        embed.add_field(name="📅 Sunday Pre-Shop Restock", value=sunday_text, inline=False)

        # Wednesday sell recommendation notification
        wednesday_role = ctx.guild.get_role(guild_config["wednesday_ping_role_id"]) if guild_config["wednesday_ping_role_id"] else None
        wednesday_role_text = wednesday_role.mention if wednesday_role else "None"

        # Show full or truncated message based on 'full' parameter
        wednesday_message = guild_config['wednesday_message']
        if not full and len(wednesday_message) > 80:
            wednesday_message_display = wednesday_message[:80] + '...'
        else:
            wednesday_message_display = wednesday_message

        wednesday_text = (
            f"**Enabled:** {'✅ Yes' if guild_config['wednesday_enabled'] else '❌ No'}\n"
            f"**Notification Time:** {guild_config['wednesday_hour']:02d}:{guild_config['wednesday_minute']:02d}\n"
            f"**Event Time:** {guild_config['wednesday_event_hour']:02d}:00 {guild_config['timezone']}\n"
            f"**Ping Role:** {wednesday_role_text}\n"
            f"**Message:** {wednesday_message_display}"
        )
        embed.add_field(name="📅 Wednesday Sell Recommendation", value=wednesday_text, inline=False)

        # Image info (from global config)
        if global_config["image_url"]:
            embed.add_field(
                name="📸 Image",
                value=f"[View Image]({global_config['image_url']})",
                inline=False
            )

        # Global options count
        total_options = len(global_config["trade_options"])
        embed.add_field(
            name="📦 Available Options",
            value=f"**Total:** {total_options} options configured\nUse `[p]tc listoptions` to view all",
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

            # Build roles text with length check
            roles_lines = [f"• {role}" for role in roles]
            footer = "\n\n*Users with Manage Server permission also have access*"

            # Check if it exceeds the limit
            roles_text = "\n".join(roles_lines) + footer
            if len(roles_text) > 1024:
                # Truncate the list
                truncated_roles = []
                for i, role_line in enumerate(roles_lines):
                    test_text = "\n".join(truncated_roles + [role_line]) + f"\n_...and {len(roles_lines) - i - 1} more_" + footer
                    if len(test_text) > 1024:
                        truncated_roles.append(f"_...and {len(roles_lines) - i} more_")
                        break
                    truncated_roles.append(role_line)
                roles_text = "\n".join(truncated_roles) + footer

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

    @tradecommission.group(name="sunday")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_sunday(self, ctx: commands.Context):
        """Configure Sunday pre-shop restock notifications."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tc_sunday.command(name="enable")
    async def sunday_enable(self, ctx: commands.Context):
        """Enable Sunday pre-shop restock notifications."""
        await self.config.guild(ctx.guild).sunday_enabled.set(True)
        await ctx.send("✅ Sunday pre-shop restock notifications enabled!")

    @tc_sunday.command(name="disable")
    async def sunday_disable(self, ctx: commands.Context):
        """Disable Sunday pre-shop restock notifications."""
        await self.config.guild(ctx.guild).sunday_enabled.set(False)
        await ctx.send("✅ Sunday pre-shop restock notifications disabled.")

    @tc_sunday.command(name="time")
    async def sunday_time(self, ctx: commands.Context, hour: int, minute: int = 0):
        """Set the time for Sunday notifications.

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23)
        - `minute` - Minute (0-59), defaults to 0

        **Example:**
        - `[p]tradecommission sunday time 19 0` - Set to 19:00
        """
        if not 0 <= hour <= 23:
            await ctx.send("❌ Hour must be between 0 and 23")
            return
        if not 0 <= minute <= 59:
            await ctx.send("❌ Minute must be between 0 and 59")
            return

        await self.config.guild(ctx.guild).sunday_hour.set(hour)
        await self.config.guild(ctx.guild).sunday_minute.set(minute)
        await ctx.send(f"✅ Sunday notification time set to {hour:02d}:{minute:02d}")

    @tc_sunday.command(name="message")
    async def sunday_message(self, ctx: commands.Context, *, message: str):
        """Set the message for Sunday notifications.

        **Arguments:**
        - `message` - The message to send

        **Example:**
        - `[p]tradecommission sunday message Pre-shop restock happening soon!`
        """
        await self.config.guild(ctx.guild).sunday_message.set(message)
        await ctx.send("✅ Sunday notification message updated!")

    @tc_sunday.command(name="pingrole")
    async def sunday_pingrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set a role to ping with Sunday notifications.

        **Arguments:**
        - `role` - The role to ping (leave empty to remove)
        """
        if role:
            await self.config.guild(ctx.guild).sunday_ping_role_id.set(role.id)
            await ctx.send(f"✅ Sunday notifications will ping {role.mention}")
        else:
            await self.config.guild(ctx.guild).sunday_ping_role_id.set(None)
            await ctx.send("✅ Sunday notifications will not ping any role")

    @tc_sunday.command(name="eventhour")
    async def sunday_eventhour(self, ctx: commands.Context, hour: int):
        """Set the hour when the Sunday event actually happens (for timestamp display).

        This is the hour shown in the {timestamp} variable in your message.
        The hour is in your configured timezone, not UTC.
        Default is 21 (9 PM in your server's timezone).

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23) in your configured timezone

        **Example:**
        - `[p]tradecommission sunday eventhour 21` - Shop restocks at 21:00 in your server's timezone
        """
        if not 0 <= hour <= 23:
            await ctx.send("❌ Hour must be between 0 and 23")
            return

        await self.config.guild(ctx.guild).sunday_event_hour.set(hour)
        tz = await self.config.guild(ctx.guild).timezone()
        await ctx.send(f"✅ Sunday event hour set to {hour:02d}:00 {tz}\n*This will be used for the {{timestamp}} variable in your message.*")

    @tc_sunday.command(name="test")
    async def sunday_test(self, ctx: commands.Context, use_configured: bool = False):
        """Test the Sunday notification by sending it immediately.

        **Arguments:**
        - `use_configured`: Send to configured announcement channel instead of current channel (default: False)

        **Examples:**
        - `[p]tc sunday test` - Send test to current channel
        - `[p]tc sunday test true` - Send test to configured announcement channel
        """
        guild_config = await self.config.guild(ctx.guild).all()

        # Determine which channel to use
        if use_configured:
            channel_id = guild_config["channel_id"]
            if not channel_id:
                await ctx.send("❌ No channel configured. Use `[p]tradecommission schedule` first.")
                return

            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                await ctx.send("❌ Configured channel not found.")
                return
        else:
            channel = ctx.channel

        # Calculate event timestamp for testing (in configured timezone)
        tz = pytz.timezone(guild_config["timezone"])
        now = datetime.now(tz)
        # Use hardcoded 21:00 UTC for consistency with the background loop
        event_time = pytz.UTC.localize(datetime(now.year, now.month, now.day, 21, 0, 0))
        # If event time has passed, use tomorrow
        if event_time < now:
            event_time += timedelta(days=1)
            event_time = pytz.UTC.normalize(event_time)
        event_timestamp = int(event_time.timestamp())

        await self._send_scheduled_notification(
            channel,
            guild_config["sunday_message"],
            guild_config["sunday_ping_role_id"],
            ctx.guild,
            event_timestamp
        )
        await ctx.send(f"✅ Test Sunday notification sent to {channel.mention}")

    @tc_sunday.command(name="info")
    async def sunday_info(self, ctx: commands.Context):
        """Show full Sunday notification configuration."""
        guild_config = await self.config.guild(ctx.guild).all()
        
        sunday_role = ctx.guild.get_role(guild_config["sunday_ping_role_id"]) if guild_config["sunday_ping_role_id"] else None
        sunday_role_text = sunday_role.mention if sunday_role else "None"

        embed = discord.Embed(
            title="📅 Sunday Pre-Shop Restock Configuration",
            color=discord.Color.blue(),
        )
        
        sunday_text = (
            f"**Enabled:** {'✅ Yes' if guild_config['sunday_enabled'] else '❌ No'}\n"
            f"**Notification Time:** {guild_config['sunday_hour']:02d}:{guild_config['sunday_minute']:02d}\n"
            f"**Event Time:** 21:00 UTC\n"
            f"**Ping Role:** {sunday_role_text}"
        )
        embed.add_field(name="Settings", value=sunday_text, inline=False)
        embed.add_field(name="Full Message", value=guild_config['sunday_message'], inline=False)
        
        await ctx.send(embed=embed)

    @tradecommission.group(name="wednesday")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tc_wednesday(self, ctx: commands.Context):
        """Configure Wednesday sell recommendation notifications."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tc_wednesday.command(name="enable")
    async def wednesday_enable(self, ctx: commands.Context):
        """Enable Wednesday sell recommendation notifications."""
        await self.config.guild(ctx.guild).wednesday_enabled.set(True)
        await ctx.send("✅ Wednesday sell recommendation notifications enabled!")

    @tc_wednesday.command(name="disable")
    async def wednesday_disable(self, ctx: commands.Context):
        """Disable Wednesday sell recommendation notifications."""
        await self.config.guild(ctx.guild).wednesday_enabled.set(False)
        await ctx.send("✅ Wednesday sell recommendation notifications disabled.")

    @tc_wednesday.command(name="time")
    async def wednesday_time(self, ctx: commands.Context, hour: int, minute: int = 0):
        """Set the time for Wednesday notifications.

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23)
        - `minute` - Minute (0-59), defaults to 0

        **Example:**
        - `[p]tradecommission wednesday time 19 0` - Set to 19:00
        """
        if not 0 <= hour <= 23:
            await ctx.send("❌ Hour must be between 0 and 23")
            return
        if not 0 <= minute <= 59:
            await ctx.send("❌ Minute must be between 0 and 59")
            return

        await self.config.guild(ctx.guild).wednesday_hour.set(hour)
        await self.config.guild(ctx.guild).wednesday_minute.set(minute)
        await ctx.send(f"✅ Wednesday notification time set to {hour:02d}:{minute:02d}")

    @tc_wednesday.command(name="message")
    async def wednesday_message(self, ctx: commands.Context, *, message: str):
        """Set the message for Wednesday notifications.

        **Arguments:**
        - `message` - The message to send

        **Example:**
        - `[p]tradecommission wednesday message Time to sell! Check your prices!`
        """
        await self.config.guild(ctx.guild).wednesday_message.set(message)
        await ctx.send("✅ Wednesday notification message updated!")

    @tc_wednesday.command(name="pingrole")
    async def wednesday_pingrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set a role to ping with Wednesday notifications.

        **Arguments:**
        - `role` - The role to ping (leave empty to remove)
        """
        if role:
            await self.config.guild(ctx.guild).wednesday_ping_role_id.set(role.id)
            await ctx.send(f"✅ Wednesday notifications will ping {role.mention}")
        else:
            await self.config.guild(ctx.guild).wednesday_ping_role_id.set(None)
            await ctx.send("✅ Wednesday notifications will not ping any role")

    @tc_wednesday.command(name="eventhour")
    async def wednesday_eventhour(self, ctx: commands.Context, hour: int):
        """Set the hour when the Wednesday event actually happens (for timestamp display).

        This is the hour shown in the {timestamp} variable in your message.
        The hour is in your configured timezone, not UTC.
        Default is 22 (10 PM in your server's timezone).

        **Arguments:**
        - `hour` - Hour in 24-hour format (0-23) in your configured timezone

        **Example:**
        - `[p]tradecommission wednesday eventhour 22` - Best sell time at 22:00 in your server's timezone
        """
        if not 0 <= hour <= 23:
            await ctx.send("❌ Hour must be between 0 and 23")
            return

        await self.config.guild(ctx.guild).wednesday_event_hour.set(hour)
        tz = await self.config.guild(ctx.guild).timezone()
        await ctx.send(f"✅ Wednesday event hour set to {hour:02d}:00 {tz}\n*This will be used for the {{timestamp}} variable in your message.*")

    @tc_wednesday.command(name="test")
    async def wednesday_test(self, ctx: commands.Context, use_configured: bool = False):
        """Test the Wednesday notification by sending it immediately.

        **Arguments:**
        - `use_configured`: Send to configured announcement channel instead of current channel (default: False)

        **Examples:**
        - `[p]tc wednesday test` - Send test to current channel
        - `[p]tc wednesday test true` - Send test to configured announcement channel
        """
        guild_config = await self.config.guild(ctx.guild).all()

        # Determine which channel to use
        if use_configured:
            channel_id = guild_config["channel_id"]
            if not channel_id:
                await ctx.send("❌ No channel configured. Use `[p]tradecommission schedule` first.")
                return

            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                await ctx.send("❌ Configured channel not found.")
                return
        else:
            channel = ctx.channel

        # Calculate event timestamp for testing (hard set to 22:00 UTC as requested)
        now = datetime.now(pytz.UTC)
        event_time = pytz.UTC.localize(datetime(now.year, now.month, now.day, 22, 0, 0))
        # If event time has passed, use tomorrow
        if event_time < now:
            event_time += timedelta(days=1)
            event_time = pytz.UTC.normalize(event_time)
        event_timestamp = int(event_time.timestamp())

        await self._send_scheduled_notification(
            channel,
            guild_config["wednesday_message"],
            guild_config["wednesday_ping_role_id"],
            ctx.guild,
            event_timestamp
        )
        await ctx.send(f"✅ Test Wednesday notification sent to {channel.mention}")

    @tc_wednesday.command(name="info")
    async def wednesday_info(self, ctx: commands.Context):
        """Show full Wednesday notification configuration."""
        guild_config = await self.config.guild(ctx.guild).all()

        wednesday_role = ctx.guild.get_role(guild_config["wednesday_ping_role_id"]) if guild_config["wednesday_ping_role_id"] else None
        wednesday_role_text = wednesday_role.mention if wednesday_role else "None"

        embed = discord.Embed(
            title="📅 Wednesday Sell Recommendation Configuration",
            color=discord.Color.blue(),
        )

        wednesday_text = (
            f"**Enabled:** {'✅ Yes' if guild_config['wednesday_enabled'] else '❌ No'}\n"
            f"**Notification Time:** {guild_config['wednesday_hour']:02d}:{guild_config['wednesday_minute']:02d}\n"
            f"**Event Time:** 22:00 UTC\n"
            f"**Ping Role:** {wednesday_role_text}"
        )
        embed.add_field(name="Settings", value=wednesday_text, inline=False)
        embed.add_field(name="Full Message", value=guild_config['wednesday_message'], inline=False)

        await ctx.send(embed=embed)

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

        # Determine embed color using priority: ping role -> bot color -> default
        embed_color = await self._get_embed_color(guild, guild_config["ping_role_id"])

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
        else:
            embed.description = guild_config["initial_description"]

        # Always add image if configured (regardless of whether options are selected)
        if image_url:
            embed.set_image(url=image_url)

        try:
            await message.edit(embed=embed)
        except discord.Forbidden:
            pass

# Force update
