import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
from typing import Optional, List, Dict, Union, Any
import asyncio
import logging
from datetime import datetime, timedelta, timezone

# Import modalpatch components
try:
    from discord.ui import Modal, TextDisplay, StringSelect, Label
except ImportError:
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
    Integrated with EventPolling schedule.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=202601221001, force_registration=True)
        
        default_guild = {
            "boss_pool": {}, 
            "admin_roles": [],
            "seen_bosses": [],
            "max_bosses_in_run": 5,
            "min_vote_threshold": 3,
            "active_poll": {
                "message_id": None,
                "channel_id": None,
                "votes": {},  # user_id: [rank1, rank2, rank3, [guests]]
                "live_view_message": {} 
            },
            "active_run": {
                "message_id": None,
                "channel_id": None,
                "boss_order": [], 
                "current_index": -1,
                "is_running": False,
                "last_auto_trigger": None
            },
            "season_data": {
                "current_week": 1,
                "anchors": [], 
                "guests": [],
                "is_active": False
            }
        }
        
        self.config.register_guild(**default_guild)
        self.schedule_checker.start()

    def cog_unload(self):
        self.schedule_checker.cancel()

    async def is_ba_admin(self, member: discord.Member) -> bool:
        if member.guild_permissions.manage_guild: return True
        admin_roles = await self.config.guild(member.guild).admin_roles()
        for role in member.roles:
            if role.id in admin_roles: return True
        return False

    def _calculate_weighted_tally(self, votes: Dict[str, Any]) -> Dict[str, float]:
        """Calculates points: R1=3, R2=2.5, R3=2, Guests=1ea."""
        tally = {}
        for choices in votes.values():
            if not isinstance(choices, list): continue
            
            # Rank 1-3
            weights = [3, 2.5, 2]
            for i in range(min(3, len(choices))):
                boss = choices[i]
                if boss and isinstance(boss, str):
                    tally[boss] = tally.get(boss, 0) + weights[i]
            
            # Guests (Stored in 4th element as a list)
            if len(choices) > 3 and isinstance(choices[3], list):
                for guest in choices[3]:
                    if guest and isinstance(guest, str):
                        tally[guest] = tally.get(guest, 0) + 1
        return tally

    async def _update_live_view(self, guild):
        poll_data = await self.config.guild(guild).active_poll()
        live_view = poll_data.get("live_view_message", {})
        boss_pool = await self.config.guild(guild).boss_pool()
        if not live_view.get("message_id"): return
        
        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))
        sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        
        desc = ""
        if not sorted_tally: desc = "No votes yet."
        else:
            for boss, points in sorted_tally:
                emote = boss_pool.get(boss, "⚔️")
                pts_str = f"{points:g}" # Clean float display
                desc += f"{emote} **{boss}**: {pts_str} pts\n"
        
        embed = discord.Embed(title="📊 Live Poll Results (Weighted)", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Total Voters: {len(poll_data.get('votes', {}))}")
        try:
            channel = guild.get_channel(live_view["channel_id"])
            if channel:
                msg = await channel.fetch_message(live_view["message_id"])
                await msg.edit(embed=embed)
        except: pass

    @tasks.loop(minutes=1)
    async def schedule_checker(self):
        try:
            for guild_id in await self.config.all_guilds():
                guild = self.bot.get_guild(guild_id)
                if not guild: continue
                polling_cog = self.bot.get_cog("EventPolling")
                if not polling_cog: continue
                polls = await polling_cog.config.guild(guild).polls()
                if not polls: continue
                latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                poll_data = polls[latest_poll_id]
                winners = polling_cog._calculate_winning_times_weighted(poll_data.get("selections", {}))
                ba_winners = winners.get("Breaking Army", {})
                server_tz = timezone(timedelta(hours=1))
                now = datetime.now(server_tz)
                day_name = now.strftime("%A")
                time_str = now.strftime("%H:%M")
                
                trigger = False
                for slot_data in ba_winners.values():
                    win_key, _, _ = slot_data 
                    if win_key[0] == day_name and win_key[1] == time_str:
                        trigger = True; break
                
                if trigger:
                    last_trigger = await self.config.guild(guild).active_run.last_auto_trigger()
                    current_key = now.strftime("%Y-%m-%dT%H:%M")
                    if last_trigger != current_key:
                        await self.config.guild(guild).active_run.last_auto_trigger.set(current_key)
                        await self._auto_start_run(guild)
        except Exception as e: log.error(f"Error in schedule_checker: {e}")

    async def _setup_new_season_logic(self, guild: discord.Guild) -> Optional[discord.Embed]:
        poll_data = await self.config.guild(guild).active_poll()
        boss_pool = await self.config.guild(guild).boss_pool()
        seen_bosses = await self.config.guild(guild).seen_bosses()
        votes = poll_data.get("votes", {})
        if not votes: return None
        
        tally = self._calculate_weighted_tally(votes)
        ranked_names = [b[0] for b in sorted(tally.items(), key=lambda x: x[1], reverse=True)]
        if len(ranked_names) < 8: return None
        
        new_bosses = [b for b in ranked_names if b not in seen_bosses]
        anchors = [None]*3; guests = [None]*5; used = []
        if len(new_bosses) >= 1: anchors[0] = new_bosses[0]; used.append(new_bosses[0])
        if len(new_bosses) >= 2: guests[0] = new_bosses[1]; used.append(new_bosses[1])
        if len(new_bosses) >= 3: anchors[2] = new_bosses[2]; used.append(new_bosses[2])
        
        rem = [b for b in ranked_names if b not in used]
        for i in range(3):
            if anchors[i] is None: anchors[i] = rem.pop(0); used.append(anchors[i])
        for i in range(5):
            if guests[i] is None: guests[i] = rem.pop(0); used.append(guests[i])
            
        async with self.config.guild(guild).season_data() as s:
            s["anchors"] = anchors; s["guests"] = guests; s["current_week"] = 1; s["is_active"] = True
        async with self.config.guild(guild).seen_bosses() as seen:
            for b in used: 
                if b not in seen: seen.append(b)
        
        embed = discord.Embed(title="🚀 New Season Initialized", color=discord.Color.green())
        def fmt(name): return f"{boss_pool.get(name, '⚔️')} **{name}**" + (" ✨" if name in new_bosses[:3] else "")
        embed.add_field(name="Anchors (Used Twice)", value="\n".join([f"{i+1}. {fmt(a)}" for i, a in enumerate(anchors)]), inline=True)
        embed.add_field(name="Guests (Used Once)", value="\n".join([f"{i+1}. {fmt(g)}" for i, g in enumerate(guests)]), inline=True)
        return embed

    async def _auto_start_run(self, guild):
        season = await self.config.guild(guild).season_data()
        if not season["is_active"]:
            setup_embed = await self._setup_new_season_logic(guild)
            if not setup_embed:
                poll_data = await self.config.guild(guild).active_poll()
                chan = guild.get_channel(poll_data["channel_id"])
                if chan: await chan.send("⚠️ **Failed to start season:** Need 8 bosses with votes.")
                return
            poll_data = await self.config.guild(guild).active_poll()
            chan = guild.get_channel(poll_data["channel_id"])
            if chan: await chan.send(embed=setup_embed)
            season = await self.config.guild(guild).season_data()
            
        week = season["current_week"]; anchors = season["anchors"]; guests = season["guests"]
        # Cycle: W1:A1+G1, W2:A2+G2, W3:A3+G3, W4:A1+G1, W5:A2+G4, W6:A3+G5
        if week == 1: boss_list = [anchors[0], guests[0]]
        elif week == 2: boss_list = [anchors[1], guests[1]]
        elif week == 3: boss_list = [anchors[2], guests[2]]
        elif week == 4: boss_list = [anchors[0], guests[0]]
        elif week == 5: boss_list = [anchors[1], guests[3]]
        elif week == 6: boss_list = [anchors[2], guests[4]]
        
        await self.config.guild(guild).active_run.set({"boss_order": boss_list, "current_index": 0, "is_running": True})
        poll_data = await self.config.guild(guild).active_poll()
        chan = guild.get_channel(poll_data["channel_id"])
        if chan:
            embed = await self._generate_run_embed(guild, boss_list, 0, True)
            msg = await chan.send(content=f"⚔️ **Breaking Army Active: Week {week}**", embed=embed)
            async with self.config.guild(guild).active_run() as run:
                run["message_id"] = msg.id; run["channel_id"] = chan.id
        async with self.config.guild(guild).season_data() as s:
            s["current_week"] += 1
            if s["current_week"] > 6: s["is_active"] = False

    @commands.group(name="ba")
    @commands.guild_only()
    async def ba(self, ctx: commands.Context):
        """Breaking Army Management"""
        pass

    @ba.group(name="config")
    async def ba_config(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_config.command(name="adminrole")
    async def admin_role_add(self, ctx: commands.Context, role: discord.Role):
        async with self.config.guild(ctx.guild).admin_roles() as r:
            if role.id not in r: r.append(role.id)
        await ctx.tick()

    @ba_config.command(name="addboss")
    async def config_add_boss(self, ctx: commands.Context, name: str, emote: str = "⚔️"):
        async with self.config.guild(ctx.guild).boss_pool() as p: p[name] = emote
        await ctx.tick()

    @ba.group(name="season")
    async def ba_season(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_season.command(name="setup")
    async def season_setup(self, ctx: commands.Context):
        embed = await self._setup_new_season_logic(ctx.guild)
        if embed: await ctx.send(embed=embed)
        else: await ctx.send("Failed setup. Need 8 unique bosses with votes.")

    @ba_season.command(name="show")
    async def season_show(self, ctx: commands.Context):
        season = await self.config.guild(ctx.guild).season_data()
        run = await self.config.guild(ctx.guild).active_run()
        if not season["anchors"]: return await ctx.send("No season data.")
        embed = discord.Embed(title="📅 Breaking Army Season Status", color=discord.Color.blue())
        a = season["anchors"]; g = season["guests"]
        sched = ""
        matrix = [(a[0],g[0]), (a[1],g[1]), (a[2],g[2]), (a[0],g[0]), (a[1],g[3]), (a[2],g[4])]
        for i, (b1, b2) in enumerate(matrix):
            w = i+1; pref = "▶️ " if w == season["current_week"] and season["is_active"] else ""
            stat = " (Complete)" if w < season["current_week"] else ""; enc = " (Encore)" if w == 4 else ""
            sched += f"{pref}**W{w}**: {b1} & {b2}{enc}{stat}\n"
        embed.add_field(name="6-Week Schedule", value=sched, inline=False)
        if run["is_running"]:
            run_embed = await self._generate_run_embed(ctx.guild, run["boss_order"], run["current_index"], True)
            await ctx.send(embed=embed); await ctx.send(content="🔥 **Current Active Run:**", embed=run_embed)
        else: await ctx.send(embed=embed)

    @ba.group(name="run")
    async def ba_run(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_run.command(name="start")
    async def run_manual_start(self, ctx: commands.Context):
        await self._auto_start_run(ctx.guild); await ctx.send("Manual run triggered.")

    @ba_run.command(name="next", aliases=["bossdown"])
    async def run_next(self, ctx: commands.Context):
        async with self.config.guild(ctx.guild).active_run() as run:
            if not run["is_running"]: return await ctx.send("No run active.")
            run["current_index"] += 1
            if run["current_index"] >= len(run["boss_order"]):
                run["is_running"] = False; await ctx.send("🏁 **Run Complete!**")
            else: await ctx.send(f"⚔️ Next Target: **{run['boss_order'][run['current_index']]}**")
            try:
                channel = ctx.guild.get_channel(run["channel_id"])
                msg = await channel.fetch_message(run["message_id"])
                embed = await self._generate_run_embed(ctx.guild, run["boss_order"], run["current_index"], run["is_running"])
                await msg.edit(embed=embed)
            except: pass

    @ba_run.command(name="cancel")
    async def run_cancel(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).active_run.is_running.set(False); await ctx.send("Run cancelled.")

    @ba.group(name="poll")
    async def ba_poll(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_poll.command(name="live")
    async def poll_live(self, ctx: commands.Context):
        msg = await ctx.send(embed=discord.Embed(title="📊 Live Poll Results", description="Initializing..."))
        async with self.config.guild(ctx.guild).active_poll() as poll:
            poll["live_view_message"] = {"message_id": msg.id, "channel_id": msg.channel.id}
        await self._update_live_view(ctx.guild)

    @ba_poll.command(name="start")
    async def poll_start(self, ctx: commands.Context):
        if not await self.config.guild(ctx.guild).boss_pool(): return await ctx.send("Pool empty.")
        view = BossPollView(self)
        msg = await ctx.send(embed=discord.Embed(title="Breaking Army Voting", description="Vote for your top choices below!", color=discord.Color.gold()), view=view)
        async with self.config.guild(ctx.guild).active_poll() as p:
            p["message_id"] = msg.id; p["channel_id"] = msg.channel.id

    @ba_poll.command(name="snapshot")
    async def poll_snapshot(self, ctx: commands.Context):
        """Snapshot current votes and start a run."""
        poll_data = await self.config.guild(ctx.guild).active_poll()
        if not poll_data["message_id"]: await ctx.send("No active poll."); return
        votes = poll_data["votes"]; tally = self._calculate_weighted_tally(votes)
        threshold = await self.config.guild(ctx.guild).min_vote_threshold()
        limit = await self.config.guild(ctx.guild).max_bosses_in_run()
        cands = sorted([(b, c) for b, c in tally.items() if c >= threshold], key=lambda x: x[1], reverse=True)
        flist = [b for b, c in cands[:limit]]
        if not flist: await ctx.send(f"No bosses met the threshold."); return
        await self.config.guild(ctx.guild).active_run.set({"boss_order": flist, "current_index": -1, "is_running": False})
        await self._start_run_display(ctx, flist)

    @ba_poll.command(name="close")
    async def poll_close(self, ctx: commands.Context):
        """Close poll and wipe votes/live views from memory."""
        await self.config.guild(ctx.guild).active_poll.set({
            "message_id": None, 
            "channel_id": None, 
            "votes": {}, 
            "live_view_message": {}
        })
        await ctx.send("Poll closed. All votes and live-update embeds have been removed from memory.")

    @ba_poll.command(name="resetvotes")
    async def poll_reset_votes(self, ctx: commands.Context):
        """Clear all votes and remove live views from memory, but keep poll message active."""
        async with self.config.guild(ctx.guild).active_poll() as poll: 
            poll["votes"] = {}
            poll["live_view_message"] = {}
        await ctx.send("Votes cleared. Live-update results have been removed from memory.")

    async def _generate_run_embed(self, guild, boss_list, current_index, is_running):
        pool = await self.config.guild(guild).boss_pool(); desc = ""
        for i, b in enumerate(boss_list):
            e = pool.get(b, "⚔️")
            if i < current_index: desc += f"💀 ~~{e} {b}~~\n"
            elif i == current_index and is_running: desc += f"⚔️ **__ {e} {b} __** (Target)\n"
            else: desc += f"⏳ {e} {b}\n"
        return discord.Embed(title=f"Breaking Army Run - {'In Progress' if is_running else 'Complete'}", description=desc, color=discord.Color.green() if is_running else discord.Color.purple())

class BossVoteModal(Modal, title="Weighted Boss Ballot"):
    def __init__(self, cog, guild, user_id, pool):
        super().__init__()
        self.cog = cog; self.guild = guild; self.user_id = user_id
        Label_cls = Label or getattr(discord.ui, "Label", None)
        options = [discord.SelectOption(label=n, value=n, emoji=e) for n, e in list(pool.items())[:25]]
        
        # 3 Weighted Choice Dropdowns
        self.ranked = []
        for i in range(1, 4):
            sel = StringSelect(placeholder=f"Choice {i}...", options=options, custom_id=f"rank_{i}")
            self.ranked.append(sel)
            label = f"{i}st Choice (3 pts)" if i==1 else f"{i}nd Choice (2.5 pts)" if i==2 else f"3rd Choice (2 pts)"
            if Label_cls: self.add_item(Label_cls(label, sel))
            else: self.add_item(sel)
            
        # 1 Multi-select Guest Dropdown
        self.guest_select = StringSelect(placeholder="Select up to 5 others...", min_values=0, max_values=5, options=options, custom_id="guests")
        if Label_cls: self.add_item(Label_cls("Guest Selections (1 pt each)", self.guest_select))
        else: self.add_item(self.guest_select)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # choices = [rank1, rank2, rank3, [guests]]
        choices = [s.values[0] if s.values else None for s in self.ranked]
        choices.append(self.guest_select.values if self.guest_select.values else [])
        
        async with self.cog.config.guild(interaction.guild).active_poll() as p:
            p["votes"][str(interaction.user.id)] = choices
        await self.cog._update_live_view(interaction.guild); await interaction.followup.send("Ballot Saved!", ephemeral=True)

class BossPollView(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog
    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="ba_vote")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = await self.cog.config.guild(interaction.guild).boss_pool()
        await interaction.response.send_modal(BossVoteModal(self.cog, interaction.guild, interaction.user.id, pool))