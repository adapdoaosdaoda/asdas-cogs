"""Utility methods for Trade Commission cog."""
import discord
import asyncio
import logging
from typing import List, Dict

from .ui_components import extract_final_emoji

log = logging.getLogger("red.tradecommission")


class UtilsMixin:
    """Mixin containing utility methods for Trade Commission."""

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

    async def _delete_notification_after_delay(self, guild: discord.Guild, channel: discord.TextChannel, message_id: int, delay_hours: int = 3):
        """Delete a notification message after a specified delay."""
        try:
            await asyncio.sleep(delay_hours * 3600)  # Convert hours to seconds
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
        else:
            embed.description = guild_config["initial_description"]

        # Always add image if configured (regardless of whether options are selected)
        if image_url:
            embed.set_image(url=image_url)

        try:
            await message.edit(embed=embed)
        except discord.Forbidden:
            pass
