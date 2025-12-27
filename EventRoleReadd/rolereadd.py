import asyncio
import logging
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.eventrolereadd")


class EventRoleReadd(commands.Cog):
    """Automatically re-adds event roles by monitoring log channel embeds.

    Monitors a log channel for bot-posted embeds containing:
    - Embed title with format: "Event Name (DD Month YYYY HH:MM)"
      Example: "Weekly Raid (27 December 2015 21:00)"
    - Embed description with a user ID and keyword/emoji

    The embed title is parsed and matched to the corresponding event role name
    (e.g., "Weekly Raid Wed 27. Dec 21:00") based on EventChannels role_format.

    When a matching keyword is found, the bot will re-add the event role to the user
    if they don't already have it.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817263541)
        self.config.register_guild(
            log_channel_id=None,  # Channel ID to monitor for log messages
            role_readd_keywords=[],  # Keywords to match in log messages for role re-adding
            report_channel_id=None,  # Channel ID to send role re-add reports
        )

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def rolereadd(self, ctx):
        """Manage automatic event role re-adding based on log messages."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @rolereadd.command(name="setchannel")
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel to monitor for event log messages.

        Examples:
        - `[p]rolereadd setchannel #event-logs` - Monitor #event-logs channel
        """
        await self.config.guild(ctx.guild).log_channel_id.set(channel.id)
        await ctx.send(f"✅ Now monitoring {channel.mention} for event log messages.")

    @rolereadd.command(name="setreport")
    async def set_report_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel to send role re-add reports.

        Examples:
        - `[p]rolereadd setreport #bot-logs` - Send reports to #bot-logs channel
        """
        await self.config.guild(ctx.guild).report_channel_id.set(channel.id)
        await ctx.send(f"✅ Role re-add reports will be sent to {channel.mention}.")

    @rolereadd.command(name="addkeyword")
    async def add_keyword(self, ctx, *, keyword: str):
        """Add a keyword or emoji to trigger automatic role re-adding.

        When a log embed contains a configured keyword/emoji in the description and includes
        a Discord user ID, the bot will automatically re-add the event role to that user.

        The embed title must match an existing event role name.

        Examples:
        - `[p]rolereadd addkeyword signed up` - Re-add roles when users sign up
        - `[p]rolereadd addkeyword Tank` - Re-add roles for Tank signups
        - `[p]rolereadd addkeyword <:emoji:123>` - Re-add roles when custom emoji is found
        """
        keywords = await self.config.guild(ctx.guild).role_readd_keywords()
        if keyword.lower() in [k.lower() for k in keywords]:
            await ctx.send(f"❌ Keyword `{keyword}` is already configured.")
            return

        keywords.append(keyword)
        await self.config.guild(ctx.guild).role_readd_keywords.set(keywords)
        await ctx.send(f"✅ Added role re-add keyword: `{keyword}`")

    @rolereadd.command(name="removekeyword")
    async def remove_keyword(self, ctx, *, keyword: str):
        """Remove a role re-add keyword.

        Examples:
        - `[p]rolereadd removekeyword Tank` - Remove the Tank keyword
        """
        keywords = await self.config.guild(ctx.guild).role_readd_keywords()
        # Case-insensitive removal
        original_keyword = next((k for k in keywords if k.lower() == keyword.lower()), None)

        if not original_keyword:
            await ctx.send(f"❌ Keyword `{keyword}` not found in configuration.")
            return

        keywords.remove(original_keyword)
        await self.config.guild(ctx.guild).role_readd_keywords.set(keywords)
        await ctx.send(f"✅ Removed role re-add keyword: `{original_keyword}`")

    @rolereadd.command(name="listkeywords")
    async def list_keywords(self, ctx):
        """List all configured role re-add keywords/emojis.

        These keywords/emojis are matched against log embed descriptions to determine
        if event roles should be automatically re-added.
        """
        keywords = await self.config.guild(ctx.guild).role_readd_keywords()

        if not keywords:
            await ctx.send("No role re-add keywords configured. Role re-adding is currently disabled.")
            return

        keyword_list = "\n".join(f"• {k}" for k in keywords)
        embed = discord.Embed(
            title="Role Re-add Keywords/Emojis",
            description=f"Roles will be re-added if log embeds contain any of these keywords:\n\n{keyword_list}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @rolereadd.command(name="clearkeywords")
    async def clear_keywords(self, ctx):
        """Clear all role re-add keywords.

        This will disable automatic role re-adding.
        """
        await self.config.guild(ctx.guild).role_readd_keywords.set([])
        await ctx.send("✅ Cleared all role re-add keywords. Role re-adding is now disabled.")

    @rolereadd.command(name="settings")
    async def view_settings(self, ctx):
        """View current role re-add settings."""
        log_channel_id = await self.config.guild(ctx.guild).log_channel_id()
        report_channel_id = await self.config.guild(ctx.guild).report_channel_id()
        keywords = await self.config.guild(ctx.guild).role_readd_keywords()

        log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
        report_channel = ctx.guild.get_channel(report_channel_id) if report_channel_id else None
        log_channel_display = log_channel.mention if log_channel else "Not set"
        report_channel_display = report_channel.mention if report_channel else "Not set"
        keywords_display = ", ".join(f"`{k}`" for k in keywords) if keywords else "None"

        embed = discord.Embed(title="Event Role Re-add Settings", color=discord.Color.blue())
        embed.add_field(name="Log Channel", value=log_channel_display, inline=False)
        embed.add_field(name="Report Channel", value=report_channel_display, inline=False)
        embed.add_field(name="Keywords", value=keywords_display, inline=False)
        embed.add_field(
            name="Status",
            value="Active" if log_channel and keywords else "Inactive (missing channel or keywords)",
            inline=False
        )

        if not report_channel_id:
            embed.add_field(
                name="⚠️ Warning",
                value="No report channel configured. Reports will not be sent. Use `!rolereadd setreport #channel` to configure.",
                inline=False
            )

        await ctx.send(embed=embed)

    @rolereadd.command(name="test")
    async def test_report(self, ctx):
        """Send a test report to verify the report channel is working."""
        report_channel_id = await self.config.guild(ctx.guild).report_channel_id()

        if not report_channel_id:
            await ctx.send("❌ No report channel configured. Use `!rolereadd setreport #channel` first.")
            return

        report_channel = ctx.guild.get_channel(report_channel_id)
        if not report_channel:
            await ctx.send("❌ Report channel not found. It may have been deleted.")
            return

        # Send test success report
        embed = discord.Embed(
            title="Role Re-add Report (TEST)",
            color=discord.Color.green(),
            timestamp=ctx.message.created_at
        )
        embed.add_field(name="User", value=f"{ctx.author.mention} ({ctx.author.name})", inline=False)
        embed.add_field(name="Trigger Keyword", value="`TEST`", inline=False)
        embed.add_field(name="Roles Re-added", value="• @TestRole1\n• @TestRole2", inline=False)
        embed.add_field(name="Source Message", value=f"[Jump to message]({ctx.message.jump_url})", inline=False)
        embed.set_footer(text="This is a test report")

        try:
            await report_channel.send(embed=embed)
            await ctx.send(f"✅ Test report sent to {report_channel.mention}")
        except discord.Forbidden:
            await ctx.send(f"❌ Failed to send test report - bot lacks permission to send messages in {report_channel.mention}")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to send test report: {e}")

    @rolereadd.command(name="debug")
    async def debug_message(self, ctx, message_id: str):
        """Debug a specific message to see why rolereadd isn't triggering.

        Provide a message ID from the log channel to analyze.
        Example: `[p]rolereadd debug 1234567890123456789`
        """
        log_channel_id = await self.config.guild(ctx.guild).log_channel_id()
        if not log_channel_id:
            await ctx.send("❌ No log channel configured. Use `!rolereadd setchannel #channel` first.")
            return

        log_channel = ctx.guild.get_channel(log_channel_id)
        if not log_channel:
            await ctx.send("❌ Log channel not found.")
            return

        try:
            message = await log_channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            await ctx.send("❌ Message not found in the log channel.")
            return
        except discord.Forbidden:
            await ctx.send("❌ Bot lacks permission to read messages in the log channel.")
            return

        # Analyze the message
        debug_info = []
        debug_info.append(f"**Message Author:** {message.author.name} (Bot: {message.author.bot})")
        debug_info.append(f"**Is Bot Message:** {'✅ Yes' if message.author.bot else '❌ No (WILL BE IGNORED)'}")
        debug_info.append(f"**Has Embeds:** {'✅ Yes' if message.embeds else '❌ No (WILL BE IGNORED)'}")

        if message.embeds:
            for i, embed in enumerate(message.embeds, 1):
                debug_info.append(f"\n**Embed #{i}:**")
                debug_info.append(f"• Title: `{embed.title if embed.title else 'None'}`")
                debug_info.append(f"• Has Description: {'✅ Yes' if embed.description else '❌ No'}")

                if embed.title:
                    # Try to parse the title
                    expected_role = await self._parse_embed_title_to_role_name(ctx.guild, embed.title)
                    if expected_role:
                        debug_info.append(f"• Parsed Role Name: `{expected_role}`")
                        role = discord.utils.get(ctx.guild.roles, name=expected_role)
                        debug_info.append(f"• Role Exists: {'✅ Yes' if role else '❌ No (ROLE NOT FOUND)'}")
                    else:
                        debug_info.append(f"• ❌ Failed to parse title (wrong format)")

                if embed.description:
                    # Check for keywords
                    keywords = await self.config.guild(ctx.guild).role_readd_keywords()
                    debug_info.append(f"• Description (first 200 chars): ```{embed.description[:200]}```")

                    matched = []
                    for keyword in keywords:
                        if keyword.lower() in embed.description.lower():
                            matched.append(keyword)

                    if matched:
                        debug_info.append(f"• ✅ Matched Keywords: {', '.join(f'`{k}`' for k in matched)}")
                    else:
                        debug_info.append(f"• ❌ No keywords matched")
                        debug_info.append(f"• Configured keywords: {', '.join(f'`{k}`' for k in keywords) if keywords else 'None'}")

                    # Check for user ID
                    user_id_match = re.search(r'\((\d{17,19})\)', embed.description)
                    if user_id_match:
                        user_id = int(user_id_match.group(1))
                        member = ctx.guild.get_member(user_id)
                        debug_info.append(f"• ✅ User ID Found: `{user_id}`")
                        debug_info.append(f"• User in Server: {'✅ Yes' if member else '❌ No'}")
                    else:
                        debug_info.append(f"• ❌ No user ID found in format (123456789012345678)")

        await ctx.send("\n".join(debug_info))

    async def _parse_embed_title_to_role_name(self, guild: discord.Guild, embed_title: str) -> Optional[str]:
        """Parse embed title and convert to expected role name format.

        Embed title format: "Event Name (27 December 2015 21:00)"
        Role format: "{name} {day_abbrev} {day}. {month_abbrev} {time}"
        Example: "Event Name Wed 27. Dec 21:00"
        """
        # Extract event name and date string from embed title
        # Format: "Event Name (DD Month YYYY HH:MM)"
        match = re.match(r'^(.+?)\s*\((\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{2}:\d{2})\)$', embed_title.strip())
        if not match:
            log.debug(f"Embed title does not match expected format: '{embed_title}'")
            return None

        event_name = match.group(1).strip()
        day = match.group(2)
        month_name = match.group(3)
        year = match.group(4)
        time_str = match.group(5)

        try:
            # Parse the date to get day of week abbreviation and month abbreviation
            # Example: "27 December 2015 21:00"
            date_string = f"{day} {month_name} {year} {time_str}"
            parsed_date = datetime.strptime(date_string, "%d %B %Y %H:%M")

            # Get the role_format from EventChannels config
            event_channels_config = Config.get_conf(None, identifier=817263540, cog_name="EventChannels")
            role_format = await event_channels_config.guild(guild).role_format()

            # Format according to role_format
            day_abbrev = parsed_date.strftime("%a")  # Sun, Mon, etc.
            day_num = parsed_date.strftime("%d").lstrip("0")  # 27 (no leading zero)
            month_abbrev = parsed_date.strftime("%b")  # Dec, Jan, etc.
            time_formatted = parsed_date.strftime("%H:%M")  # 21:00

            expected_role_name = role_format.format(
                name=event_name,
                day_abbrev=day_abbrev,
                day=day_num,
                month_abbrev=month_abbrev,
                time=time_formatted
            )

            log.debug(f"Converted embed title '{embed_title}' to expected role name '{expected_role_name}'")
            return expected_role_name

        except ValueError as e:
            log.warning(f"Failed to parse date from embed title '{embed_title}': {e}")
            return None
        except Exception as e:
            log.error(f"Error converting embed title to role name: {e}")
            return None

    async def _send_error_report(
        self,
        guild: discord.Guild,
        matched_keyword: str,
        error_reason: str,
        source_message: discord.Message,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None
    ):
        """Send an error report to the configured report channel."""
        report_channel_id = await self.config.guild(guild).report_channel_id()
        if not report_channel_id:
            return

        report_channel = guild.get_channel(report_channel_id)
        if not report_channel:
            return

        embed = discord.Embed(
            title="⚠️ Role Re-add Failed",
            color=discord.Color.red(),
            timestamp=source_message.created_at
        )

        if user_id and user_name:
            embed.add_field(name="User", value=f"{user_name} (ID: {user_id})", inline=False)
        elif user_id:
            embed.add_field(name="User ID", value=str(user_id), inline=False)

        embed.add_field(name="Trigger Keyword", value=f"`{matched_keyword}`", inline=False)
        embed.add_field(name="Reason", value=error_reason, inline=False)
        embed.add_field(name="Source Message", value=f"[Jump to message]({source_message.jump_url})", inline=False)

        try:
            await report_channel.send(embed=embed)
        except discord.Forbidden:
            log.warning(f"Failed to send error report to channel {report_channel.name} - insufficient permissions")
        except discord.HTTPException as e:
            log.error(f"Failed to send error report to channel {report_channel.name}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor log channel for bot-posted embeds and re-add event roles based on keywords."""
        # Ignore DMs and non-bot messages
        if not message.guild or not message.author.bot:
            return

        # Check if this is the configured log channel
        log_channel_id = await self.config.guild(message.guild).log_channel_id()
        if not log_channel_id or message.channel.id != log_channel_id:
            return

        # Check if feature is enabled (non-empty keywords list)
        keywords = await self.config.guild(message.guild).role_readd_keywords()
        if not keywords:
            return

        # Process only messages with embeds
        if not message.embeds:
            return

        # Process each embed in the message
        for embed in message.embeds:
            # Skip embeds without title or description
            if not embed.title or not embed.description:
                continue

            # Check if embed description contains any configured keywords (including custom emojis)
            matched_keyword = None
            for keyword in keywords:
                if keyword.lower() in embed.description.lower():
                    matched_keyword = keyword
                    break

            if not matched_keyword:
                continue

            log.info(f"Keyword '{matched_keyword}' detected in {message.guild.name} log channel embed")

            # Extract Discord user ID from embed description
            # Format: "Username (123456789012345678) signed up as..."
            user_id_match = re.search(r'\((\d{17,19})\)', embed.description)
            if not user_id_match:
                log.warning(f"Keyword detected but no user ID found in embed description: {embed.description[:100]}")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    "No Discord user ID found in the embed description. Expected format: `Username (123456789012345678)`",
                    message
                )
                continue

            user_id = int(user_id_match.group(1))
            member = message.guild.get_member(user_id)

            if not member:
                log.debug(f"Member {user_id} not found in guild {message.guild.name}")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    f"User is not a member of this server. They may have left or been removed.",
                    message,
                    user_id=user_id
                )
                continue

            # Parse the embed title and convert to expected role name format
            # Embed title: "Event Name (27 December 2015 21:00)"
            # Role name: "Event Name Wed 27. Dec 21:00"
            expected_role_name = await self._parse_embed_title_to_role_name(message.guild, embed.title)

            if not expected_role_name:
                log.debug(f"Failed to parse embed title: '{embed.title}'")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    f"Failed to parse embed title format. Expected: `Event Name (DD Month YYYY HH:MM)`, got: `{embed.title}`",
                    message,
                    user_id=member.id,
                    user_name=member.name
                )
                continue

            # Try to find the role with the converted name
            matching_role = discord.utils.get(message.guild.roles, name=expected_role_name)

            if not matching_role:
                log.debug(f"No role found matching expected name: '{expected_role_name}' (from embed title: '{embed.title}')")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    f"No role found matching the event. Expected role: `{expected_role_name}`",
                    message,
                    user_id=member.id,
                    user_name=member.name
                )
                continue

            # Check if member already has the role
            if matching_role in member.roles:
                log.debug(f"Member {member.name} already has role '{matching_role.name}'")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    f"User already has the role {matching_role.mention}",
                    message,
                    user_id=member.id,
                    user_name=member.name
                )
                continue

            # Re-add the role
            try:
                await member.add_roles(matching_role, reason=f"EventRoleReadd: Auto re-add (keyword: {matched_keyword})")
                log.info(
                    f"Re-added event role '{matching_role.name}' to {member.name} (ID: {member.id}) "
                    f"due to keyword '{matched_keyword}' in log embed"
                )

                # Send success report to report channel if configured
                report_channel_id = await self.config.guild(message.guild).report_channel_id()
                if report_channel_id:
                    report_channel = message.guild.get_channel(report_channel_id)
                    if report_channel:
                        report_embed = discord.Embed(
                            title="✅ Role Re-add Report",
                            color=discord.Color.green(),
                            timestamp=message.created_at
                        )
                        report_embed.add_field(name="User", value=f"{member.mention} ({member.name})", inline=False)
                        report_embed.add_field(name="Role Re-added", value=matching_role.mention, inline=False)
                        report_embed.add_field(name="Event", value=f"`{embed.title}`", inline=False)
                        report_embed.add_field(name="Trigger Keyword", value=f"`{matched_keyword}`", inline=False)
                        report_embed.add_field(name="Source Message", value=f"[Jump to message]({message.jump_url})", inline=False)

                        try:
                            await report_channel.send(embed=report_embed)
                            log.info(f"Sent role re-add report to {report_channel.name} for {member.name}")
                        except discord.Forbidden:
                            log.warning(f"Failed to send report to channel {report_channel.name} - insufficient permissions")
                        except discord.HTTPException as e:
                            log.error(f"Failed to send report to channel {report_channel.name}: {e}")
                    else:
                        log.warning(f"Report channel ID {report_channel_id} configured but channel not found")
                else:
                    log.debug(f"No report channel configured, skipping report for {member.name}")

            except discord.Forbidden:
                log.warning(f"Failed to re-add event role '{matching_role.name}' to {member.name} - insufficient permissions")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    f"Failed to re-add role {matching_role.mention} - Bot lacks permissions",
                    message,
                    user_id=member.id,
                    user_name=member.name
                )
            except discord.HTTPException as e:
                log.error(f"Failed to re-add event role '{matching_role.name}' to {member.name}: {e}")
                await self._send_error_report(
                    message.guild,
                    matched_keyword,
                    f"Failed to re-add role {matching_role.mention} - Discord error: {str(e)}",
                    message,
                    user_id=member.id,
                    user_name=member.name
                )
