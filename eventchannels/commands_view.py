import logging

import discord
from redbot.core import commands

log = logging.getLogger("red.eventchannels")


class CommandsViewMixin:
    """Mixin class containing view/list commands for EventChannels cog."""

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def vieweventsettings(self, ctx):
        """View current event channel settings."""
        category_id = await self.config.guild(ctx.guild).category_id()
        timezone = await self.config.guild(ctx.guild).timezone()
        creation_minutes = await self.config.guild(ctx.guild).creation_minutes()
        deletion_hours = await self.config.guild(ctx.guild).deletion_hours()
        role_format = await self.config.guild(ctx.guild).role_format()
        channel_format = await self.config.guild(ctx.guild).channel_format()
        space_replacer = await self.config.guild(ctx.guild).space_replacer()
        announcement_message = await self.config.guild(ctx.guild).announcement_message()
        event_start_message = await self.config.guild(ctx.guild).event_start_message()
        deletion_warning_message = await self.config.guild(ctx.guild).deletion_warning_message()
        divider_enabled = await self.config.guild(ctx.guild).divider_enabled()
        divider_name = await self.config.guild(ctx.guild).divider_name()
        channel_name_limit = await self.config.guild(ctx.guild).channel_name_limit()
        channel_name_limit_char = await self.config.guild(ctx.guild).channel_name_limit_char()
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()
        voice_minimum_roles = await self.config.guild(ctx.guild).voice_minimum_roles()
        whitelisted_role_ids = await self.config.guild(ctx.guild).whitelisted_roles()

        category = ctx.guild.get_channel(category_id) if category_id else None
        category_name = category.name if category else "Not set"
        announcement_display = f"`{announcement_message}`" if announcement_message else "Disabled"
        event_start_display = f"`{event_start_message}`" if event_start_message else "Disabled"
        deletion_warning_display = f"`{deletion_warning_message}`" if deletion_warning_message else "Disabled"
        divider_display = f"Enabled (`{divider_name}`)" if divider_enabled else "Disabled"

        # Format voice multipliers display
        if voice_multipliers:
            multiplier_list = []
            for keyword, multiplier in sorted(voice_multipliers.items()):
                multiplier_list.append(f"`{keyword}`: {multiplier} (limit: {multiplier + 1})")
            voice_multiplier_display = ", ".join(multiplier_list)
        else:
            voice_multiplier_display = "Disabled"

        # Format voice minimum roles display
        if voice_minimum_roles:
            minimum_list = []
            for keyword, minimum in sorted(voice_minimum_roles.items()):
                minimum_list.append(f"`{keyword}`: {minimum} members")
            voice_minimum_display = ", ".join(minimum_list)
        else:
            voice_minimum_display = "None"

        # Format whitelisted roles display
        if whitelisted_role_ids:
            whitelist_list = []
            for role_id in whitelisted_role_ids:
                role = ctx.guild.get_role(role_id)
                if role:
                    whitelist_list.append(f"`{role.name}`")
                else:
                    whitelist_list.append(f"`Deleted Role (ID: {role_id})`")
            whitelisted_display = ", ".join(whitelist_list)
        else:
            whitelisted_display = "None"

        # Display channel name limit setting
        if channel_name_limit_char:
            name_limit_display = f"Truncate before `{channel_name_limit_char}` (character-based)"
        else:
            name_limit_display = f"{channel_name_limit} characters (numeric)"

        embed = discord.Embed(title="Event Channels Settings", color=discord.Color.blue())
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="Timezone", value=timezone, inline=False)
        embed.add_field(name="Creation Time", value=f"{creation_minutes} minutes before start", inline=False)
        embed.add_field(name="Archiving Time", value=f"{deletion_hours} hours after start", inline=False)
        embed.add_field(name="Role Format", value=f"`{role_format}`", inline=False)
        embed.add_field(name="Channel Format", value=f"`{channel_format}`", inline=False)
        embed.add_field(name="Space Replacer", value=f"`{space_replacer}`", inline=False)
        embed.add_field(name="Channel Name Limit", value=name_limit_display, inline=False)
        embed.add_field(name="Voice Multiplier", value=voice_multiplier_display, inline=False)
        embed.add_field(name="Minimum Roles Required", value=voice_minimum_display, inline=False)
        embed.add_field(name="Whitelisted Roles", value=whitelisted_display, inline=False)
        embed.add_field(name="Announcement", value=announcement_display, inline=False)
        embed.add_field(name="Event Start Message", value=event_start_display, inline=False)
        embed.add_field(name="Archiving Warning", value=deletion_warning_display, inline=False)
        embed.add_field(name="Divider Channel", value=divider_display, inline=False)

        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            # Fallback to plain text if bot lacks embed permissions
            message = (
                f"**Event Channels Settings**\n"
                f"**Category:** {category_name}\n"
                f"**Timezone:** {timezone}\n"
                f"**Creation Time:** {creation_minutes} minutes before start\n"
                f"**Archiving Time:** {deletion_hours} hours after start\n"
                f"**Role Format:** `{role_format}`\n"
                f"**Channel Format:** `{channel_format}`\n"
                f"**Space Replacer:** `{space_replacer}`\n"
                f"**Channel Name Limit:** {name_limit_display}\n"
                f"**Voice Multiplier:** {voice_multiplier_display}\n"
                f"**Minimum Roles Required:** {voice_minimum_display}\n"
                f"**Whitelisted Roles:** {whitelisted_display}\n"
                f"**Announcement:** {announcement_display}\n"
                f"**Event Start Message:** {event_start_display}\n"
                f"**Archiving Warning:** {deletion_warning_display}\n"
                f"**Divider Channel:** {divider_display}"
            )
            await ctx.send(message)

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def listvoicemultipliers(self, ctx):
        """List all configured voice multipliers.

        Shows all keywords and their associated multipliers.
        """
        voice_multipliers = await self.config.guild(ctx.guild).voice_multipliers()

        if not voice_multipliers:
            await ctx.send(f"❌ No voice multipliers configured. Use `{ctx.clean_prefix}eventchannels setvoicemultiplier <keyword> <multiplier>` to add one.")
            return

        # Build the list
        multiplier_list = []
        for keyword, multiplier in sorted(voice_multipliers.items()):
            multiplier_list.append(
                f"• **{keyword}**: multiplier={multiplier}, limit={multiplier + 1} users/channel"
            )

        await ctx.send(
            f"**Configured Voice Multipliers:**\n" + "\n".join(multiplier_list) + "\n\n"
            f"Use `{ctx.clean_prefix}eventchannels removevoicemultiplier <keyword>` to remove a multiplier."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def listminimumroles(self, ctx):
        """List all configured minimum role requirements.

        Shows all keywords and their associated minimum member counts.
        """
        voice_minimum_roles = await self.config.guild(ctx.guild).voice_minimum_roles()

        if not voice_minimum_roles:
            await ctx.send(f"❌ No minimum role requirements configured. Use `{ctx.clean_prefix}eventchannels setminimumroles <keyword> <minimum>` to add one.")
            return

        # Build the list
        minimum_list = []
        for keyword, minimum in sorted(voice_minimum_roles.items()):
            minimum_list.append(
                f"• **{keyword}**: minimum {minimum} role members required"
            )

        await ctx.send(
            f"**Configured Minimum Role Requirements:**\n" + "\n".join(minimum_list) + "\n\n"
            f"Use `{ctx.clean_prefix}eventchannels removeminimumroles <keyword>` to remove a requirement."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def listwhitelistedroles(self, ctx):
        """List all whitelisted roles.

        Shows all roles that automatically receive permissions in event channels.
        """
        whitelisted_roles = await self.config.guild(ctx.guild).whitelisted_roles()

        if not whitelisted_roles:
            await ctx.send(
                f"❌ No whitelisted roles configured.\n"
                f"Use `{ctx.clean_prefix}eventchannels addwhitelistedrole <role>` to add one."
            )
            return

        # Build the list
        role_list = []
        for role_id in whitelisted_roles:
            role = ctx.guild.get_role(role_id)
            if role:
                role_list.append(f"• **{role.name}** (ID: {role_id})")
            else:
                role_list.append(f"• *Deleted Role* (ID: {role_id})")

        await ctx.send(
            f"**Whitelisted Roles:**\n" + "\n".join(role_list) + "\n\n"
            f"These roles automatically receive view, read, connect, and speak permissions in all event channels.\n"
            f"Use `{ctx.clean_prefix}eventchannels removewhitelistedrole <role>` to remove a role."
        )
