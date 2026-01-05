"""UI Components for Trade Commission cog."""
import discord
import re
from typing import Optional, Dict, List
import asyncio


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


class AddInfoView(discord.ui.View):
    """View for adding Trade Commission information with dropdowns organized by category."""

    def __init__(self, cog: "TradeCommission", guild: discord.Guild, trade_options: List[Dict], active_options: List[int], emoji_titles: Dict[str, str], allowed_user_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.guild = guild
        self.trade_options = trade_options
        self.active_options = active_options
        self.allowed_user_id = allowed_user_id

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

                        # Send new notification (without role ping)
                        notification_content = guild_config["notification_message"]

                        notification_msg = await current_channel.send(notification_content)

                        # Store notification message ID
                        await self.cog.config.guild(self.guild).notification_message_id.set(notification_msg.id)

                        # Schedule deletion after 3 hours
                        asyncio.create_task(
                            self.cog._delete_notification_after_delay(
                                self.guild, current_channel, notification_msg.id, 3
                            )
                        )
                except (discord.Forbidden, discord.HTTPException):
                    pass  # Couldn't send notification

                # Delete the addinfo message
                try:
                    await interaction.message.delete()
                    await self.cog.config.guild(self.guild).addinfo_message_id.set(None)
                    await interaction.response.send_message("✅ All 3 options selected! The addinfo panel has been closed.", ephemeral=True)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                return
            else:
                # Recreate the view with updated selections
                emoji_titles = await self.cog.config.emoji_titles()
                new_view = AddInfoView(self.cog, self.guild, self.trade_options, self.active_options, emoji_titles, self.allowed_user_id)

                # Get updated embed
                embed = await self.cog._create_addinfo_embed(self.guild, self.trade_options, self.active_options)

                # Update the message
                try:
                    await interaction.response.edit_message(embed=embed, view=new_view)
                except discord.HTTPException:
                    pass

        return callback
