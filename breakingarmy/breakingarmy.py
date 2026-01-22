import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional, List, Dict, Union
import asyncio

class BreakingArmy(commands.Cog):
    """
    Boss polling and run management for the Breaking Army event.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=984328743209, force_registration=True)
        
        default_guild = {
            "boss_pool": [],
            "max_bosses_in_run": 5,
            "min_vote_threshold": 3,
            "active_poll": {
                "message_id": None,
                "channel_id": None,
                "votes": {},  # user_id: [boss_names]
                "live_view_message": None  # {channel_id, message_id}
            },
            "active_run": {
                "message_id": None,
                "channel_id": None,
                "boss_order": [], # List[str]
                "current_index": -1, # -1 = not started, 0 = first boss, etc.
                "is_running": False
            }
        }
        
        self.config.register_guild(**default_guild)

    async def cog_load(self):
        pass

    async def _update_live_view(self, guild):
        """Updates the live view message with current vote counts."""
        poll_data = await self.config.guild(guild).active_poll()
        live_view = poll_data.get("live_view_message")
        
        if not live_view or not live_view.get("message_id"):
            return

        # Tally votes
        votes = poll_data.get("votes", {})
        tally = {}
        for user_votes in votes.values():
            for boss in user_votes:
                tally[boss] = tally.get(boss, 0) + 1
        
        # Sort by count (desc)
        sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        
        # Build Description
        desc = ""
        total_voters = len(votes)
        
        if not sorted_tally:
            desc = "No votes yet."
        else:
            for boss, count in sorted_tally:
                desc += f"**{boss}**: {count} votes\n"
        
        embed = discord.Embed(
            title="📊 Live Poll Results",
            description=desc,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Total Voters: {total_voters}")

        # Update Message
        try:
            channel = guild.get_channel(live_view["channel_id"])
            if channel:
                msg = await channel.fetch_message(live_view["message_id"])
                await msg.edit(embed=embed)
            else:
                # Channel deleted? Clear config to stop trying
                async with self.config.guild(guild).active_poll() as p:
                    p["live_view_message"] = None
        except discord.NotFound:
            # Message deleted
            async with self.config.guild(guild).active_poll() as p:
                p["live_view_message"] = None
        except Exception as e:
            pass # Ignore other errors

    @commands.group(name="ba")
    @commands.guild_only()
    async def ba(self, ctx: commands.Context):
        """Breaking Army Management Commands"""
        pass

    @ba.group(name="config")
    @commands.admin_or_permissions(manage_guild=True)
    async def ba_config(self, ctx: commands.Context):
        """Configuration for Breaking Army"""
        pass

    @ba_config.command(name="addboss")
    async def config_add_boss(self, ctx: commands.Context, *, boss_name: str):
        """Add a boss to the available pool."""
        async with self.config.guild(ctx.guild).boss_pool() as pool:
            if boss_name in pool:
                await ctx.send(f"'{boss_name}' is already in the boss pool.")
                return
            if len(pool) >= 25:
                await ctx.send("Boss pool is full (max 25). Remove one first.")
                return
            pool.append(boss_name)
        await ctx.send(f"Added '{boss_name}' to the boss pool.")

    @ba_config.command(name="removeboss")
    async def config_remove_boss(self, ctx: commands.Context, *, boss_name: str):
        """Remove a boss from the pool."""
        async with self.config.guild(ctx.guild).boss_pool() as pool:
            if boss_name not in pool:
                await ctx.send(f"'{boss_name}' is not in the boss pool.")
                return
            pool.remove(boss_name)
        await ctx.send(f"Removed '{boss_name}' from the boss pool.")

    @ba_config.command(name="list")
    async def config_list_bosses(self, ctx: commands.Context):
        """List all configured bosses."""
        pool = await self.config.guild(ctx.guild).boss_pool()
        if not pool:
            await ctx.send("No bosses configured.")
            return
        
        pool_str = "\n".join([f"- {boss}" for boss in pool])
        embed = discord.Embed(title="Breaking Army Boss Pool", description=pool_str, color=discord.Color.blue())
        await ctx.send(embed=embed)

    @ba_config.command(name="limit")
    async def config_set_limit(self, ctx: commands.Context, limit: int):
        """Set the maximum number of bosses to include in a run."""
        if limit < 1:
            await ctx.send("Limit must be at least 1.")
            return
        await self.config.guild(ctx.guild).max_bosses_in_run.set(limit)
        await ctx.send(f"Max bosses per run set to {limit}.")

    @ba_config.command(name="threshold")
    async def config_set_threshold(self, ctx: commands.Context, threshold: int):
        """Set the minimum votes required for a boss to be included."""
        if threshold < 0:
            await ctx.send("Threshold cannot be negative.")
            return
        await self.config.guild(ctx.guild).min_vote_threshold.set(threshold)
        await ctx.send(f"Minimum vote threshold set to {threshold}.")

    @ba.group(name="poll")
    @commands.admin_or_permissions(manage_guild=True)
    async def ba_poll(self, ctx: commands.Context):
        """Poll management commands."""
        pass

    @ba_poll.command(name="live")
    async def poll_live(self, ctx: commands.Context):
        """
        Create a live-updating view of the poll results.
        """
        embed = discord.Embed(title="📊 Live Poll Results", description="Initializing...", color=discord.Color.blue())
        msg = await ctx.send(embed=embed)
        
        async with self.config.guild(ctx.guild).active_poll() as poll:
            poll["live_view_message"] = {
                "message_id": msg.id,
                "channel_id": msg.channel.id
            }
        
        # Force initial update
        await self._update_live_view(ctx.guild)

    @ba_poll.command(name="start")
    async def poll_start(self, ctx: commands.Context):
        """
        Start (or move) the persistent voting poll.
        
        If a poll is already active, this will create a NEW message linked to the SAME voting data.
        Use `[p]ba poll close` first if you want to wipe votes and start fresh.
        """
        pool = await self.config.guild(ctx.guild).boss_pool()
        if not pool:
            await ctx.send("Boss pool is empty! Add bosses via `[p]ba config addboss` first.")
            return

        # Check for existing poll
        current_poll = await self.config.guild(ctx.guild).active_poll()
        if current_poll["message_id"]:
            await ctx.send("A poll is already active. I will create a new message linked to the **existing** votes.\nIf you wanted a fresh poll, run `[p]ba poll close` first.")

        embed = discord.Embed(
            title="Breaking Army: Boss Selection Vote",
            description="**Live Poll:** Vote for the bosses you want to fight!\n\nThis poll is always open. Admins can snapshot the results at any time to start a run.\nSelect all that apply from the dropdown below.",
            color=discord.Color.gold()
        )
        
        view = BossPollView(self, pool)
        msg = await ctx.send(embed=embed, view=view)
        
        # Update config with new message location, preserving votes if they exist
        async with self.config.guild(ctx.guild).active_poll() as poll:
            poll["message_id"] = msg.id
            poll["channel_id"] = msg.channel.id
            # votes are preserved

    @ba_poll.command(name="snapshot")
    async def poll_snapshot(self, ctx: commands.Context):
        """
        Take a snapshot of the current votes and start a run.
        
        This does NOT close the poll or clear votes.
        """
        poll_data = await self.config.guild(ctx.guild).active_poll()
        if not poll_data["message_id"]:
            await ctx.send("No active poll found. Start one with `[p]ba poll start`.")
            return

        # Tally votes (Live Snapshot)
        votes = poll_data["votes"]
        tally = {}
        for user_votes in votes.values():
            for boss in user_votes:
                tally[boss] = tally.get(boss, 0) + 1

        # Apply logic
        threshold = await self.config.guild(ctx.guild).min_vote_threshold()
        limit = await self.config.guild(ctx.guild).max_bosses_in_run()

        # Filter by threshold and sort by votes (desc)
        candidates = [(boss, count) for boss, count in tally.items() if count >= threshold]
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Apply limit
        final_list = [boss for boss, count in candidates[:limit]]

        if not final_list:
            await ctx.send(f"No bosses met the threshold of {threshold} votes in this snapshot.")
            return

        # Check if a run is already active
        active_run = await self.config.guild(ctx.guild).active_run()
        if active_run["is_running"]:
            await ctx.send("⚠️ A run is already in progress! This will overwrite it. (Type `yes` to confirm)")
            try:
                msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=15)
                if msg.content.lower() != "yes":
                    await ctx.send("Snapshot cancelled.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("Timed out. Snapshot cancelled.")
                return

        # Save Run State (Poll remains open)
        await self.config.guild(ctx.guild).active_run.set({
            "message_id": None,
            "channel_id": None,
            "boss_order": final_list,
            "current_index": -1,
            "is_running": False
        })

        # Create Run View
        await self._start_run_display(ctx, final_list)
        await ctx.send(f"✅ **Run Generated!** The poll remains open for future snapshots.")

    @ba_poll.command(name="close")
    async def poll_close(self, ctx: commands.Context):
        """
        Close the active poll and wipe all votes.
        """
        poll_data = await self.config.guild(ctx.guild).active_poll()
        if not poll_data["message_id"]:
            await ctx.send("No active poll to close.")
            return

        # Try to disable the old view
        try:
            channel = ctx.guild.get_channel(poll_data["channel_id"])
            if channel:
                msg = await channel.fetch_message(poll_data["message_id"])
                await msg.edit(view=None, content="**Poll Closed**")
        except:
            pass
        
        # Clear live view if it exists
        live_view = poll_data.get("live_view_message")
        if live_view:
            try:
                c = ctx.guild.get_channel(live_view["channel_id"])
                if c:
                    m = await c.fetch_message(live_view["message_id"])
                    await m.delete()
            except:
                pass

        # Clear poll data
        await self.config.guild(ctx.guild).active_poll.set({
            "message_id": None,
            "channel_id": None,
            "votes": {},
            "live_view_message": None
        })
        await ctx.send("Poll closed, live view removed, and votes cleared.")

    @ba_poll.command(name="resetvotes")
    async def poll_reset_votes(self, ctx: commands.Context):
        """
        Clear all votes but keep the poll open.
        """
        async with self.config.guild(ctx.guild).active_poll() as poll:
            poll["votes"] = {}
        
        await self._update_live_view(ctx.guild)
        await ctx.send("All votes have been cleared. The poll remains open.")

    async def _start_run_display(self, ctx, boss_list):
        embed = self._generate_run_embed(boss_list, -1, False)
        view = RunManagerView(self)
        msg = await ctx.send(embed=embed, view=view)
        
        async with self.config.guild(ctx.guild).active_run() as run_data:
            run_data["message_id"] = msg.id
            run_data["channel_id"] = msg.channel.id

    def _generate_run_embed(self, boss_list, current_index, is_running):
        status_text = "Waiting to Start"
        color = discord.Color.light_grey()
        
        if is_running:
            status_text = "In Progress"
            color = discord.Color.green()
        if current_index >= len(boss_list):
            status_text = "Run Complete"
            color = discord.Color.purple()

        desc = ""
        for i, boss in enumerate(boss_list):
            if i < current_index:
                desc += f"💀 ~~{boss}~~\n"
            elif i == current_index and is_running:
                desc += f"⚔️ **__ {boss} __** (Current Target)\n"
            else:
                desc += f"⏳ {boss}\n"

        embed = discord.Embed(title=f"Breaking Army Run - {status_text}", description=desc, color=color)
        return embed

    @ba.group(name="run")
    @commands.admin_or_permissions(manage_guild=True)
    async def ba_run(self, ctx: commands.Context):
        """Manually manage the active run."""
        pass
    
    @ba_run.command(name="resend")
    async def run_resend(self, ctx: commands.Context):
        """Resend the run control panel if lost."""
        run_data = await self.config.guild(ctx.guild).active_run()
        if not run_data["boss_order"]:
            await ctx.send("No active run data.")
            return
            
        await self._start_run_display(ctx, run_data["boss_order"])

class BossPollView(discord.ui.View):
    def __init__(self, cog, boss_options: List[str]):
        super().__init__(timeout=None)
        self.cog = cog
        
        # Select Menu
        options = [discord.SelectOption(label=boss) for boss in boss_options]
        # Max 25 options
        options = options[:25]
        
        self.select = discord.ui.Select(
            placeholder="Select bosses to fight...",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id="ba_poll_select"
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        selected_bosses = self.select.values
        
        async with self.cog.config.guild(interaction.guild).active_poll() as poll:
            poll["votes"][str(interaction.user.id)] = selected_bosses
            
        await self.cog._update_live_view(interaction.guild)
        await interaction.followup.send(f"Votes saved for: {', '.join(selected_bosses)}", ephemeral=True)

class RunManagerView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Start Run", style=discord.ButtonStyle.green, custom_id="ba_run_start")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions? For now, assume anyone who can see the button can click (or add check)
        # Better to check if user has manage_guild or is a run leader. 
        # For simplicity, we'll allow it but you might want to restrict this.
        if not interaction.user.guild_permissions.manage_guild:
             await interaction.response.send_message("Only admins can manage the run.", ephemeral=True)
             return
             
        await interaction.response.defer()
        
        async with self.cog.config.guild(interaction.guild).active_run() as run:
            if run["is_running"]:
                return # Already running
            
            run["is_running"] = True
            run["current_index"] = 0
            
            await self.update_message(interaction, run)

    @discord.ui.button(label="Boss Down / Next", style=discord.ButtonStyle.blurple, custom_id="ba_run_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
             await interaction.response.send_message("Only admins can manage the run.", ephemeral=True)
             return

        await interaction.response.defer()

        async with self.cog.config.guild(interaction.guild).active_run() as run:
            if not run["is_running"]:
                await interaction.followup.send("Run is not active.", ephemeral=True)
                return
            
            run["current_index"] += 1
            
            if run["current_index"] >= len(run["boss_order"]):
                run["is_running"] = False # Finished
                
            await self.update_message(interaction, run)

    @discord.ui.button(label="End/Cancel", style=discord.ButtonStyle.danger, custom_id="ba_run_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
             await interaction.response.send_message("Only admins can manage the run.", ephemeral=True)
             return

        await interaction.response.defer()
        
        async with self.cog.config.guild(interaction.guild).active_run() as run:
            run["is_running"] = False
            # We don't clear the order, just stop it.
            await self.update_message(interaction, run)

    async def update_message(self, interaction, run_data):
        embed = self.cog._generate_run_embed(
            run_data["boss_order"], 
            run_data["current_index"], 
            run_data["is_running"]
        )
        try:
            await interaction.message.edit(embed=embed, view=self)
        except:
            pass
