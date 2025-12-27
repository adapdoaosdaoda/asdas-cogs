import asyncio
import logging
import re
from typing import Optional

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.eventrolereadd")


class EventRoleReadd(commands.Cog):
    """Automatically re-adds event roles based on keywords in log channel messages."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817263541)
        self.config.register_guild(
            log_channel_id=None,  # Channel ID to monitor for log messages
            role_readd_keywords=[],  # Keywords to match in log messages for role re-adding
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

    @rolereadd.command(name="addkeyword")
    async def add_keyword(self, ctx, *, keyword: str):
        """Add a keyword to trigger automatic role re-adding.

        When a log message contains a configured keyword and includes a Discord user ID,
        the bot will automatically re-add event roles to that user.

        Examples:
        - `[p]rolereadd addkeyword signed up` - Re-add roles when users sign up
        - `[p]rolereadd addkeyword Tank` - Re-add roles for Tank signups
        - `[p]rolereadd addkeyword Absence` - Re-add roles for Absence notifications
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
        """List all configured role re-add keywords.

        These keywords are matched against log messages to determine
        if event roles should be automatically re-added.
        """
        keywords = await self.config.guild(ctx.guild).role_readd_keywords()

        if not keywords:
            await ctx.send("No role re-add keywords configured. Role re-adding is currently disabled.")
            return

        keyword_list = "\n".join(f"• `{k}`" for k in keywords)
        embed = discord.Embed(
            title="Role Re-add Keywords",
            description=f"Roles will be re-added if log messages contain any of these keywords:\n\n{keyword_list}",
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
        keywords = await self.config.guild(ctx.guild).role_readd_keywords()

        log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
        channel_display = log_channel.mention if log_channel else "Not set"
        keywords_display = ", ".join(f"`{k}`" for k in keywords) if keywords else "None"

        embed = discord.Embed(title="Event Role Re-add Settings", color=discord.Color.blue())
        embed.add_field(name="Log Channel", value=channel_display, inline=False)
        embed.add_field(name="Keywords", value=keywords_display, inline=False)
        embed.add_field(
            name="Status",
            value="Active" if log_channel and keywords else "Inactive (missing channel or keywords)",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor log channel for messages and re-add roles based on keywords."""
        # Ignore DMs and bot messages
        if not message.guild or message.author.bot:
            return

        # Check if this is the configured log channel
        log_channel_id = await self.config.guild(message.guild).log_channel_id()
        if not log_channel_id or message.channel.id != log_channel_id:
            return

        # Check if feature is enabled (non-empty keywords list)
        keywords = await self.config.guild(message.guild).role_readd_keywords()
        if not keywords:
            return

        # Extract text from message content and embeds
        text_to_search = message.content

        # If message has embeds, extract text from them
        if message.embeds:
            for embed in message.embeds:
                # Add embed title
                if embed.title:
                    text_to_search += "\n" + embed.title
                # Add embed description
                if embed.description:
                    text_to_search += "\n" + embed.description
                # Add embed fields
                if embed.fields:
                    for field in embed.fields:
                        if field.name:
                            text_to_search += "\n" + field.name
                        if field.value:
                            text_to_search += "\n" + field.value
                # Add footer text
                if embed.footer and embed.footer.text:
                    text_to_search += "\n" + embed.footer.text
                # Add author name
                if embed.author and embed.author.name:
                    text_to_search += "\n" + embed.author.name

        # Check if message contains any configured keywords
        text_to_search_lower = text_to_search.lower()
        matched_keyword = None
        for keyword in keywords:
            if keyword.lower() in text_to_search_lower:
                matched_keyword = keyword
                break

        if not matched_keyword:
            return

        # Extract Discord user ID from the combined text
        # Format: "Username (123456789012345678) signed up as..."
        user_id_match = re.search(r'\((\d{17,19})\)', text_to_search)
        if not user_id_match:
            log.debug(f"No user ID found in log message: {text_to_search[:100]}")
            return

        user_id = int(user_id_match.group(1))
        member = message.guild.get_member(user_id)

        if not member:
            log.debug(f"Member {user_id} not found in guild {message.guild.name}")
            return

        # Find event roles to re-add
        # We'll use the EventChannels cog's configuration to identify event roles
        event_channels_config = Config.get_conf(None, identifier=817263540, cog_name="EventChannels")
        stored = await event_channels_config.guild(message.guild).event_channels()

        roles_to_readd = []
        for event_id, data in stored.items():
            role_id = data.get("role")
            if not role_id:
                continue

            role = message.guild.get_role(role_id)
            if role and role not in member.roles:
                roles_to_readd.append(role)

        # Re-add all identified event roles
        if roles_to_readd:
            for role in roles_to_readd:
                try:
                    await member.add_roles(role, reason=f"EventRoleReadd: Auto re-add (keyword: {matched_keyword})")
                    log.info(
                        f"Re-added event role '{role.name}' to {member.name} (ID: {member.id}) "
                        f"due to keyword '{matched_keyword}' in log message"
                    )
                except discord.Forbidden:
                    log.warning(f"Failed to re-add event role '{role.name}' to {member.name} - insufficient permissions")
                except discord.HTTPException as e:
                    log.error(f"Failed to re-add event role '{role.name}' to {member.name}: {e}")
        else:
            log.debug(f"No event roles to re-add for {member.name} (ID: {member.id})")
