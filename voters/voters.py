import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
import logging
from typing import Dict, List, Optional
import datetime

log = logging.getLogger("red.asdas-cogs.voters")

class Voters(commands.Cog):
    """
    Displays lists of voters for EventPoll and BreakingArmy.
    """
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2024030401, force_registration=True)
        default_guild = {
            "allowed_roles": []
        }
        self.config.register_guild(**default_guild)
        
        # Start the periodic check
        self.check_cogs_loaded.start()

    def cog_unload(self):
        self.check_cogs_loaded.cancel()

    @tasks.loop(time=datetime.time(hour=2, minute=0))
    async def check_cogs_loaded(self):
        """Check daily at 2 AM if required cogs are loaded."""
        required_cogs = ["EventPolling", "BreakingArmy"]
        missing_cogs = []

        for cog_name in required_cogs:
            if not self.bot.get_cog(cog_name):
                missing_cogs.append(cog_name)

        if missing_cogs:
            log.warning(f"Voters Auto-Check: Missing cogs {missing_cogs}")
            
            # Construct alert message
            msg = (
                f"⚠️ **Voters Auto-Check Alert**\n"
                f"The following cogs were found unloaded at the daily check:\n"
                f"**{', '.join(missing_cogs)}**\n"
                f"Please check your bot console or try to reload them."
            )

            # Send to all owners
            owners = self.bot.owner_ids
            if not owners:
                # Fallback if owner_ids not set yet (rare)
                try:
                    info = await self.bot.application_info()
                    owners = [info.owner.id]
                except Exception:
                    log.error("Could not retrieve bot owners to send alert.")
                    return

            for owner_id in owners:
                try:
                    owner = await self.bot.get_or_fetch_user(owner_id)
                    if owner:
                        await owner.send(msg)
                except Exception as e:
                    log.error(f"Failed to DM owner {owner_id}: {e}")

    @check_cogs_loaded.before_loop
    async def before_check_cogs_loaded(self):
        await self.bot.wait_until_ready()

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def voters(self, ctx: commands.Context):
        """Show list of voters or manage settings."""
        if ctx.invoked_subcommand is None:
             await self._show_voters(ctx)

    async def _show_voters(self, ctx: commands.Context):
        """Logic to show list of all users who voted in active polls."""
        
        # Access Check
        allowed_roles = await self.config.guild(ctx.guild).allowed_roles()
        has_allowed_role = any(role.id in allowed_roles for role in ctx.author.roles)
        
        if not (ctx.author.guild_permissions.manage_guild or has_allowed_role):
            return await ctx.send("❌ You do not have permission to use this command.")

        # --- 1. Collect Data ---
        
        # Breaking Army Votes
        ba_voters = set()
        ba_cog = self.bot.get_cog("BreakingArmy")
        if ba_cog:
            try:
                # Use raw config access if needed, or cog methods if available
                # Looking at BreakingArmy code: active_poll -> votes
                active_poll = await ba_cog.config.guild(ctx.guild).active_poll()
                votes = active_poll.get("votes", {})
                for user_id_str in votes.keys():
                    try:
                        member = ctx.guild.get_member(int(user_id_str))
                        name = f"{member.display_name} ({member.name})" if member else f"Unknown User ({user_id_str})"
                        ba_voters.add(name)
                    except ValueError:
                        continue
            except Exception as e:
                log.error(f"Error fetching BreakingArmy voters: {e}")

        # EventPolling Votes
        ep_voters_by_event: Dict[str, set] = {}
        ep_cog = self.bot.get_cog("EventPolling")
        if ep_cog:
            try:
                polls = await ep_cog.config.guild(ctx.guild).polls()
                if polls:
                    # Get the latest poll (assuming active)
                    latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                    poll_data = polls[latest_poll_id]
                    selections = poll_data.get("selections", {})
                    
                    for user_id_str, user_choices in selections.items():
                        try:
                            member = ctx.guild.get_member(int(user_id_str))
                            name = f"{member.display_name} ({member.name})" if member else f"Unknown User ({user_id_str})"
                            
                            for event_name, choice_data in user_choices.items():
                                # Verify if choice is valid (not None or empty)
                                is_valid = False
                                if isinstance(choice_data, list):
                                    if any(x is not None for x in choice_data):
                                        is_valid = True
                                elif choice_data is not None:
                                    is_valid = True
                                
                                if is_valid:
                                    if event_name not in ep_voters_by_event:
                                        ep_voters_by_event[event_name] = set()
                                    ep_voters_by_event[event_name].add(name)
                        except ValueError:
                            continue
            except Exception as e:
                log.error(f"Error fetching EventPolling voters: {e}")

        # --- 2. Build Output ---
        
        if not ba_voters and not ep_voters_by_event:
            return await ctx.send("❌ No active votes found in either system.")

        embeds = []
        current_embed = discord.Embed(
            title="🗳️ Voter Participation Report", 
            description="List of users who voted in current active polls.",
            color=discord.Color.blue()
        )
        
        # Helper to add fields with pagination logic
        def add_field_safe(name, value, inline=False):
            nonlocal current_embed
            # Check if adding this field would exceed limits
            # Field value limit: 1024
            # Embed total limit: 6000
            
            # Truncate value if too long for a single field
            if len(value) > 1024:
                value = value[:1000] + "\n... (truncated)"
            
            # Calculate new size
            current_len = len(current_embed.title or "") + len(current_embed.description or "")
            for f in current_embed.fields:
                current_len += len(f.name) + len(f.value)
            
            if current_len + len(name) + len(value) > 5900 or len(current_embed.fields) >= 25:
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title="🗳️ Voter Participation Report (Cont.)", 
                    color=discord.Color.blue()
                )
            
            current_embed.add_field(name=name, value=value, inline=inline)

        # Breaking Army Field
        if ba_voters:
            ba_list = sorted(list(ba_voters))
            ba_text = "\n".join(ba_list)
            add_field_safe(f"⚡ Breaking Army ({len(ba_list)})", ba_text)
        
        # EventPolling Fields
        for event_name in sorted(ep_voters_by_event.keys()):
            voters = sorted(list(ep_voters_by_event[event_name]))
            voters_text = "\n".join(voters)
            add_field_safe(f"📅 {event_name} ({len(voters)})", voters_text)

        embeds.append(current_embed)

        # Send all embeds
        for embed in embeds:
            await ctx.send(embed=embed)

    @voters.group(name="settings", aliases=["set"])
    @commands.admin_or_permissions(manage_guild=True)
    async def voters_settings(self, ctx: commands.Context):
        """Manage Voters configuration."""
        pass

    @voters_settings.command(name="addrole")
    async def add_allowed_role(self, ctx: commands.Context, role: discord.Role):
        """Add a role to the allowed list for the !voters command."""
        async with self.config.guild(ctx.guild).allowed_roles() as roles:
            if role.id in roles:
                return await ctx.send(f"❌ {role.name} is already in the allowed list.")
            roles.append(role.id)
        await ctx.send(f"✅ Added {role.name} to allowed voters roles.")

    @voters_settings.command(name="removerole")
    async def remove_allowed_role(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from the allowed list."""
        async with self.config.guild(ctx.guild).allowed_roles() as roles:
            if role.id not in roles:
                return await ctx.send(f"❌ {role.name} is not in the allowed list.")
            roles.remove(role.id)
        await ctx.send(f"✅ Removed {role.name} from allowed voters roles.")

    @voters_settings.command(name="listroles")
    async def list_allowed_roles(self, ctx: commands.Context):
        """List all allowed roles."""
        roles_ids = await self.config.guild(ctx.guild).allowed_roles()
        if not roles_ids:
            return await ctx.send("No roles configured. Only admins can use the command.")
        
        role_mentions = []
        for rid in roles_ids:
            role = ctx.guild.get_role(rid)
            if role:
                role_mentions.append(role.name)
            else:
                role_mentions.append(f"Deleted Role ({rid})")
                
        await ctx.send(f"**Allowed Roles:** {', '.join(role_mentions)}")
