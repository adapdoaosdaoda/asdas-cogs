import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional, List, Dict, Union
import asyncio
import logging

# Import modalpatch components
try:
    from discord.ui import Modal, TextDisplay, StringSelect, Label
except ImportError:
    # Fallback if modalpatch not loaded
    from discord.ui import Modal
    try:
        from discord.ui import StringSelect
    except ImportError:
        from discord.ui import Select as StringSelect
    TextDisplay = None
    Label = None

log = logging.getLogger("red.asdas-cogs.breakingarmy")

class BreakingArmy(commands.Cog):
    """
    Boss polling and run management for the Breaking Army event.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        # Changed identifier to resolve Structural KeyError from List -> Dict migration
        self.config = Config.get_conf(self, identifier=202601221001, force_registration=True)
        
        default_guild = {
            "boss_pool": {}, # Dict[name, emote]
            "admin_roles": [],
            "seen_bosses": [],
            "max_bosses_in_run": 5,
            "min_vote_threshold": 3,
            "active_poll": {
                "message_id": None,
                "channel_id": None,
                "votes": {},  # user_id: [boss_names]
                "live_view_message": {} # {channel_id, message_id}
            },
            "active_run": {
                "message_id": None,
                "channel_id": None,
                "boss_order": [], 
                "current_index": -1,
                "is_running": False
            },
            "season_data": {
                "current_week": 1,
                "anchors": [], 
                "guests": [],
                "is_active": False
            }
        }
        
        self.config.register_guild(**default_guild)

    async def cog_load(self):
        pass

    async def is_ba_admin(self, member: discord.Member) -> bool:
        """Checks if a member is a BA admin (Manage Guild or specific role)."""
        if member.guild_permissions.manage_guild:
            return True
        
        admin_roles = await self.config.guild(member.guild).admin_roles()
        for role in member.roles:
            if role.id in admin_roles:
                return True
        
        return False

    async def _update_live_view(self, guild):
        """Updates the live view message with current vote counts."""
        poll_data = await self.config.guild(guild).active_poll()
        live_view = poll_data.get("live_view_message", {})
        boss_pool = await self.config.guild(guild).boss_pool()
        
        if not live_view.get("message_id"):
            return

        # Tally votes
        votes = poll_data.get("votes", {})
        tally = {}
        for user_votes in votes.values():
            for boss in user_votes:
                tally[boss] = tally.get(boss, 0) + 1
        
        sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        desc = ""
        total_voters = len(votes)
        
        if not sorted_tally:
            desc = "No votes yet."
        else:
            for boss, count in sorted_tally:
                emote = boss_pool.get(boss, "⚔️")
                desc += f"{emote} **{boss}**: {count} votes\n"
        
        embed = discord.Embed(title="📊 Live Poll Results", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Total Voters: {total_voters}")

        try:
            channel = guild.get_channel(live_view["channel_id"])
            if channel:
                msg = await channel.fetch_message(live_view["message_id"])
                await msg.edit(embed=embed)
        except:
            pass

    @commands.group(name="ba")
    @commands.guild_only()
    async def ba(self, ctx: commands.Context):
        """Breaking Army Management Commands"""
        pass

    @ba.group(name="config")
    @commands.guild_only()
    async def ba_config(self, ctx: commands.Context):
        """Configuration for Breaking Army"""
        if not await self.is_ba_admin(ctx.author):
            raise commands.CheckFailure("You do not have permission to manage Breaking Army.")
        pass

    @ba_config.group(name="adminrole")
    async def config_admin_role(self, ctx: commands.Context):
        """Manage roles allowed to use BA admin commands."""
        pass

    @config_admin_role.command(name="add")
    async def admin_role_add(self, ctx: commands.Context, role: discord.Role):
        """Add a role to BA admins."""
        async with self.config.guild(ctx.guild).admin_roles() as roles:
            if role.id in roles:
                await ctx.send("That role is already an admin role.")
                return
            roles.append(role.id)
        await ctx.send(f"Added {role.name} to Breaking Army admin roles.")

    @config_admin_role.command(name="remove")
    async def admin_role_remove(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from BA admins."""
        async with self.config.guild(ctx.guild).admin_roles() as roles:
            if role.id not in roles:
                await ctx.send("That role is not an admin role.")
                return
            roles.remove(role.id)
        await ctx.send(f"Removed {role.name} from Breaking Army admin roles.")

    @config_admin_role.command(name="list")
    async def admin_role_list(self, ctx: commands.Context):
        """List all BA admin roles."""
        role_ids = await self.config.guild(ctx.guild).admin_roles()
        if not role_ids:
            await ctx.send("No custom admin roles configured."); return
        roles = [ctx.guild.get_role(rid).name if ctx.guild.get_role(rid) else str(rid) for rid in role_ids]
        await ctx.send(f"**Breaking Army Admin Roles:**\n" + "\n".join([f"- {r}" for r in roles]))

    @ba_config.command(name="addboss")
    async def config_add_boss(self, ctx: commands.Context, boss_name: str, emoji: str = "⚔️"):
        """Add a boss to the available pool with an optional emote."""
        async with self.config.guild(ctx.guild).boss_pool() as pool:
            if boss_name in pool:
                await ctx.send(f"'{boss_name}' is already in the boss pool."); return
            if len(pool) >= 25:
                await ctx.send("Boss pool is full (max 25)."); return
            pool[boss_name] = emoji
        await ctx.send(f"Added {emoji} '{boss_name}' to the boss pool.")

    @ba_config.command(name="setemote")
    async def config_set_emote(self, ctx: commands.Context, boss_name: str, emoji: str):
        """Set or update the emote for an existing boss."""
        async with self.config.guild(ctx.guild).boss_pool() as pool:
            if boss_name not in pool:
                await ctx.send(f"'{boss_name}' not found."); return
            pool[boss_name] = emoji
        await ctx.send(f"Updated {boss_name} emote to: {emoji}")

    @ba_config.command(name="removeboss")
    async def config_remove_boss(self, ctx: commands.Context, *, boss_name: str):
        """Remove a boss from the pool."""
        async with self.config.guild(ctx.guild).boss_pool() as pool:
            if boss_name not in pool:
                await ctx.send(f"'{boss_name}' not found."); return
            del pool[boss_name]
        await ctx.send(f"Removed '{boss_name}' from the boss pool.")

    @ba_config.command(name="list")
    async def config_list_bosses(self, ctx: commands.Context):
        """List all configured bosses."""
        pool = await self.config.guild(ctx.guild).boss_pool()
        if not pool:
            await ctx.send("No bosses configured."); return
        pool_str = "\n".join([f"{emote} {name}" for name, emote in pool.items()])
        await ctx.send(embed=discord.Embed(title="Breaking Army Boss Pool", description=pool_str, color=discord.Color.blue()))

    @ba_config.command(name="limit")
    async def config_set_limit(self, ctx: commands.Context, limit: int):
        """Set the maximum number of bosses to include in a run."""
        await self.config.guild(ctx.guild).max_bosses_in_run.set(max(1, limit))
        await ctx.send(f"Max bosses per run set to {limit}.")

    @ba_config.command(name="threshold")
    async def config_set_threshold(self, ctx: commands.Context, threshold: int):
        """Set the minimum votes required for a boss to be included."""
        await self.config.guild(ctx.guild).min_vote_threshold.set(max(0, threshold))
        await ctx.send(f"Minimum vote threshold set to {threshold}.")

    @ba.group(name="season")
    @commands.guild_only()
    async def ba_season(self, ctx: commands.Context):
        """Season Management Commands"""
        if not await self.is_ba_admin(ctx.author):
             raise commands.CheckFailure("Permission denied.")
        pass

    @ba_season.command(name="setup")
    async def season_setup(self, ctx: commands.Context):
        """Setup a new season automatically using the Top 8 bosses."""
        poll_data = await self.config.guild(ctx.guild).active_poll()
        boss_pool = await self.config.guild(ctx.guild).boss_pool()
        votes = poll_data.get("votes", {})
        seen_bosses = await self.config.guild(ctx.guild).seen_bosses()
        
        if not votes:
            await ctx.send("No votes found in the active poll!"); return

        tally = {}
        for user_votes in votes.values():
            for boss in user_votes: tally[boss] = tally.get(boss, 0) + 1
        ranked_names = [b[0] for b in sorted(tally.items(), key=lambda x: x[1], reverse=True)]
        
        if len(ranked_names) < 8:
            await ctx.send(f"Need at least 8 unique bosses with votes. (Currently: {len(ranked_names)})"); return

        new_bosses = [b for b in ranked_names if b not in seen_bosses]
        anchors = [None, None, None, None]; guests = [None, None, None, None]; used = []

        if len(new_bosses) >= 1: anchors[0] = new_bosses[0]; used.append(new_bosses[0])
        if len(new_bosses) >= 2: anchors[1] = new_bosses[1]; used.append(new_bosses[1])
        if len(new_bosses) >= 3: anchors[3] = new_bosses[2]; used.append(new_bosses[2])
            
        remaining = [b for b in ranked_names if b not in used]
        for i in range(4):
            if anchors[i] is None: anchors[i] = remaining.pop(0); used.append(anchors[i])
        for i in range(4):
            if guests[i] is None: guests[i] = remaining.pop(0); used.append(guests[i])
        
        async with self.config.guild(ctx.guild).season_data() as season:
            season["anchors"] = anchors; season["guests"] = guests
            season["current_week"] = 1; season["is_active"] = True
            
        async with self.config.guild(ctx.guild).seen_bosses() as seen:
            for boss in used:
                if boss not in seen: seen.append(boss)
            
        embed = discord.Embed(title="Breaking Army Season Setup", color=discord.Color.green())
        def fmt(name): return f"{boss_pool.get(name, '⚔️')} **{name}**" + (" ✨" if name in new_bosses[:3] else "")
        embed.add_field(name="Anchors (Used Twice)", value="\n".join([f"{i+1}. {fmt(a)}" for i, a in enumerate(anchors)]), inline=True)
        embed.add_field(name="Guests (Used Once)", value="\n".join([f"{i+1}. {fmt(g)}" for i, g in enumerate(guests)]), inline=True)
        await ctx.send(embed=embed)

    @ba_season.command(name="show")
    async def season_show(self, ctx: commands.Context):
        """Display the 6-week schedule."""
        season = await self.config.guild(ctx.guild).season_data()
        boss_pool = await self.config.guild(ctx.guild).boss_pool()
        if not season["is_active"] and not season["anchors"]:
            await ctx.send("No active season."); return

        anchors = season["anchors"]; guests = season["guests"]
        current_week = season["current_week"]
        embed = discord.Embed(title="📅 Season Schedule (Anchor Rotation)", color=discord.Color.blue())
        schedule_text = ""
        for week in range(1, 7):
            if week == 1: boss_list = [anchors[0], anchors[1]]
            elif week == 2: boss_list = [anchors[2], guests[0]]
            elif week == 3: boss_list = [anchors[3], guests[1]]
            elif week == 4: boss_list = [anchors[0], anchors[1]]
            elif week == 5: boss_list = [anchors[2], guests[2]]
            elif week == 6: boss_list = [anchors[3], guests[3]]
            
            def get_name(n): return f"{boss_pool.get(n, '⚔️')} {n}"
            prefix = "▶️ " if week == current_week and season["is_active"] else ""
            status = " (Complete)" if week < current_week else ""
            label = " (Encore)" if week == 4 else ""
            schedule_text += f"{prefix}**Week {week}**: {get_name(boss_list[0])} & {get_name(boss_list[1])}{label}{status}\n"
            
        embed.add_field(name="Weekly Lineup", value=schedule_text, inline=False)
        await ctx.send(embed=embed)

    @ba_season.command(name="next")
    async def season_next(self, ctx: commands.Context):
        """Generate the run for the current week."""
        season = await self.config.guild(ctx.guild).season_data()
        if not season["is_active"]: await ctx.send("No active season!"); return
        week = season["current_week"]
        anchors = season["anchors"]; guests = season["guests"]
        if week > 6: await ctx.send("Season complete!"); return

        if week == 1: boss_list = [anchors[0], anchors[1]]
        elif week == 2: boss_list = [anchors[2], guests[0]]
        elif week == 3: boss_list = [anchors[3], guests[1]]
        elif week == 4: boss_list = [anchors[0], anchors[1]]
        elif week == 5: boss_list = [anchors[2], guests[2]]
        elif week == 6: boss_list = [anchors[3], guests[3]]
            
        await ctx.send(f"**Generating Run for Week {week}**")
        await self.config.guild(ctx.guild).active_run.set({"boss_order": boss_list, "current_index": -1, "is_running": False})
        await self._start_run_display(ctx, boss_list)
        async with self.config.guild(ctx.guild).season_data() as s:
            s["current_week"] += 1
            if s["current_week"] > 6: s["is_active"] = False

    @ba.group(name="poll")
    @commands.guild_only()
    async def ba_poll(self, ctx: commands.Context):
        """Poll management commands."""
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure("Permission denied.")
        pass

    @ba_poll.command(name="live")
    async def poll_live(self, ctx: commands.Context):
        """Create a live-updating view of the poll results."""
        msg = await ctx.send(embed=discord.Embed(title="📊 Live Poll Results", description="Initializing..."))
        async with self.config.guild(ctx.guild).active_poll() as poll:
            poll["live_view_message"] = {"message_id": msg.id, "channel_id": msg.channel.id}
        await self._update_live_view(ctx.guild)

    @ba_poll.command(name="start")
    async def poll_start(self, ctx: commands.Context):
        """Start (or move) the persistent voting poll."""
        if not await self.config.guild(ctx.guild).boss_pool(): await ctx.send("Boss pool is empty!"); return
        view = BossPollView(self)
        msg = await ctx.send(embed=discord.Embed(title="Breaking Army: Boss Selection Vote", description="**Live Poll:** Vote for the bosses you want to fight!\n\nThis poll is always open. Click the button below to open the ballot.", color=discord.Color.gold()), view=view)
        async with self.config.guild(ctx.guild).active_poll() as poll:
            poll["message_id"] = msg.id; poll["channel_id"] = msg.channel.id

    @ba_poll.command(name="snapshot")
    async def poll_snapshot(self, ctx: commands.Context):
        """Snapshot current votes and start a run."""
        poll_data = await self.config.guild(ctx.guild).active_poll()
        if not poll_data["message_id"]: await ctx.send("No active poll."); return
        votes = poll_data["votes"]; tally = {}
        for uv in votes.values():
            for b in uv: tally[b] = tally.get(b, 0) + 1
        threshold = await self.config.guild(ctx.guild).min_vote_threshold()
        limit = await self.config.guild(ctx.guild).max_bosses_in_run()
        cands = sorted([(b, c) for b, c in tally.items() if c >= threshold], key=lambda x: x[1], reverse=True)
        flist = [b for b, c in cands[:limit]]
        if not flist: await ctx.send(f"No bosses met the threshold."); return
        await self.config.guild(ctx.guild).active_run.set({"boss_order": flist, "current_index": -1, "is_running": False})
        await self._start_run_display(ctx, flist)

    @ba_poll.command(name="close")
    async def poll_close(self, ctx: commands.Context):
        """Close poll and wipe votes."""
        await self.config.guild(ctx.guild).active_poll.set({"message_id": None, "channel_id": None, "votes": {}, "live_view_message": {}})
        await ctx.send("Poll closed and votes cleared.")

    @ba_poll.command(name="resetvotes")
    async def poll_reset_votes(self, ctx: commands.Context):
        """Clear all votes but keep poll open."""
        async with self.config.guild(ctx.guild).active_poll() as poll: poll["votes"] = {}
        await self._update_live_view(ctx.guild); await ctx.send("Votes cleared.")

    async def _start_run_display(self, ctx, boss_list):
        embed = await self._generate_run_embed(ctx.guild, boss_list, -1, False)
        view = RunManagerView(self)
        msg = await ctx.send(embed=embed, view=view)
        async with self.config.guild(ctx.guild).active_run() as run_data:
            run_data["message_id"] = msg.id; run_data["channel_id"] = msg.channel.id

    async def _generate_run_embed(self, guild, boss_list, current_index, is_running):
        status_text = "Waiting to Start"; color = discord.Color.light_grey()
        if is_running: status_text = "In Progress"; color = discord.Color.green()
        if current_index >= len(boss_list): status_text = "Run Complete"; color = discord.Color.purple()
        boss_pool = await self.config.guild(guild).boss_pool()
        desc = ""
        for i, boss in enumerate(boss_list):
            e = boss_pool.get(boss, "⚔️")
            if i < current_index: desc += f"💀 ~~{e} {boss}~~\n"
            elif i == current_index and is_running: desc += f"⚔️ **__ {e} {boss} __** (Target)\n"
            else: desc += f"⏳ {e} {boss}\n"
        return discord.Embed(title=f"Breaking Army Run - {status_text}", description=desc, color=color)

    @ba.group(name="run")
    @commands.guild_only()
    async def ba_run(self, ctx: commands.Context):
        """Manage active run."""
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure("Permission denied.")
        pass
    
    @ba_run.command(name="resend")
    async def run_resend(self, ctx: commands.Context):
        run_data = await self.config.guild(ctx.guild).active_run()
        if not run_data["boss_order"]: await ctx.send("No active run."); return
        await self._start_run_display(ctx, run_data["boss_order"])

class BossVoteModal(Modal, title="Vote for Bosses"):
    def __init__(self, cog, guild: discord.Guild, user_id: int, current_votes: List[str], pool: Dict[str, str]):
        super().__init__()
        self.cog = cog; self.guild = guild; self.user_id = user_id
        Label_cls = Label or getattr(discord.ui, "Label", None)
        options = [discord.SelectOption(label=n, value=n, emoji=e, default=(n in current_votes)) for n, e in list(pool.items())[:25]]
        self.select = StringSelect(placeholder="Select bosses...", min_values=0, max_values=len(options), options=options, custom_id="boss_select_modal")
        if Label_cls: self.add_item(Label_cls("Select Bosses", self.select))
        else: self.add_item(self.select)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with self.cog.config.guild(interaction.guild).active_poll() as poll: poll["votes"][str(interaction.user.id)] = self.select.values
        await self.cog._update_live_view(interaction.guild); await interaction.followup.send(f"Votes saved: {', '.join(self.select.values)}", ephemeral=True)

class BossPollView(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog
    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="ba_open_vote_modal")
    async def open_vote_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = await self.cog.config.guild(interaction.guild).boss_pool()
        if not pool: await interaction.response.send_message("Pool empty!", ephemeral=True); return
        poll_data = await self.cog.config.guild(interaction.guild).active_poll()
        votes = poll_data.get("votes", {}).get(str(interaction.user.id), [])
        await interaction.response.send_modal(BossVoteModal(self.cog, interaction.guild, interaction.user.id, votes, pool))

class RunManagerView(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog
    @discord.ui.button(label="Start Run", style=discord.ButtonStyle.green, custom_id="ba_run_start")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.is_ba_admin(interaction.user): await interaction.response.send_message("Admins only.", ephemeral=True); return
        await interaction.response.defer()
        async with self.cog.config.guild(interaction.guild).active_run() as run:
            if run["is_running"]: return
            run["is_running"] = True; run["current_index"] = 0; await self.update_message(interaction, run)
    @discord.ui.button(label="Boss Down / Next", style=discord.ButtonStyle.blurple, custom_id="ba_run_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.is_ba_admin(interaction.user): await interaction.response.send_message("Admins only.", ephemeral=True); return
        await interaction.response.defer()
        async with self.cog.config.guild(interaction.guild).active_run() as run:
            if not run["is_running"]: return
            run["current_index"] += 1
            if run["current_index"] >= len(run["boss_order"]): run["is_running"] = False
            await self.update_message(interaction, run)
    @discord.ui.button(label="End/Cancel", style=discord.ButtonStyle.danger, custom_id="ba_run_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.is_ba_admin(interaction.user): await interaction.response.send_message("Admins only.", ephemeral=True); return
        await interaction.response.defer()
        async with self.cog.config.guild(interaction.guild).active_run() as run: run["is_running"] = False; await self.update_message(interaction, run)
    async def update_message(self, interaction, run_data):
        embed = await self.cog._generate_run_embed(interaction.guild, run_data["boss_order"], run_data["current_index"], run_data["is_running"])
        try: await interaction.message.edit(embed=embed, view=self)
        except: pass