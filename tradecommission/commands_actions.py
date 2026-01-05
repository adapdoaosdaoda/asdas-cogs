"""Action commands for Trade Commission cog."""
import discord
import logging
from typing import Optional
from redbot.core import commands

from .ui_components import AddInfoView

log = logging.getLogger("red.tradecommission")


class CommandsActionsMixin:
    """Mixin containing action commands for Trade Commission."""

    @commands.command(name="post")
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

    @commands.command(name="addinfo")
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

    @commands.command(name="info")
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

        # Notification message info
        notification_text = (
            f"**Message:** {guild_config['notification_message'][:100]}{'...' if len(guild_config['notification_message']) > 100 else ''}\n"
            f"**Auto-delete:** After 3 hours"
        )
        embed.add_field(name="🔔 Notification (when 3 options selected)", value=notification_text, inline=False)

        # Sunday pre-shop restock notification
        sunday_role = ctx.guild.get_role(guild_config["sunday_ping_role_id"]) if guild_config["sunday_ping_role_id"] else None
        sunday_role_text = sunday_role.mention if sunday_role else "None"
        sunday_text = (
            f"**Enabled:** {'✅ Yes' if guild_config['sunday_enabled'] else '❌ No'}\n"
            f"**Time:** {guild_config['sunday_hour']:02d}:{guild_config['sunday_minute']:02d}\n"
            f"**Ping Role:** {sunday_role_text}\n"
            f"**Message:** {guild_config['sunday_message'][:80]}{'...' if len(guild_config['sunday_message']) > 80 else ''}"
        )
        embed.add_field(name="📅 Sunday Pre-Shop Restock", value=sunday_text, inline=False)

        # Wednesday sell recommendation notification
        wednesday_role = ctx.guild.get_role(guild_config["wednesday_ping_role_id"]) if guild_config["wednesday_ping_role_id"] else None
        wednesday_role_text = wednesday_role.mention if wednesday_role else "None"
        wednesday_text = (
            f"**Enabled:** {'✅ Yes' if guild_config['wednesday_enabled'] else '❌ No'}\n"
            f"**Time:** {guild_config['wednesday_hour']:02d}:{guild_config['wednesday_minute']:02d}\n"
            f"**Ping Role:** {wednesday_role_text}\n"
            f"**Message:** {guild_config['wednesday_message'][:80]}{'...' if len(guild_config['wednesday_message']) > 80 else ''}"
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

    @commands.command(name="testnow")
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
