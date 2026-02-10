import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
from typing import Optional, List, Dict, Union, Any, Tuple
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
                "votes": {},  # user_id: [anchor, encore, [guests]]
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
        """Calculates points: Anchor=2.5ea (up to 3), Encore=1, Guests=1ea."""
        tally = {}
        for choices in votes.values():
            if not isinstance(choices, list) or len(choices) < 3: continue
            
            # Anchors (Index 0) - 2.5 pts ea
            anchors = choices[0]
            if isinstance(anchors, list):
                for a in anchors:
                    if a: tally[a] = tally.get(a, 0) + 2.5
            elif isinstance(anchors, str): # Backward compatibility
                tally[anchors] = tally.get(anchors, 0) + 2.5
            
            # Encore (Index 1) - 1 pt
            e = choices[1]
            if e: tally[e] = tally.get(e, 0) + 1
            
            # Guests (Index 2 - List) - 1 pt ea
            gs = choices[2]
            if isinstance(gs, list):
                for g in gs:
                    if g: tally[g] = tally.get(g, 0) + 1
        return tally

    async def _update_poll_embed(self, guild: discord.Guild):
        """Updates the main poll message with current leaders."""
        async with self.config.guild(guild).active_poll() as poll:
            if not poll["message_id"]: return
            try:
                channel = guild.get_channel(poll["channel_id"])
                msg = await channel.fetch_message(poll["message_id"])
                embed = await self._generate_poll_embed(guild)
                await msg.edit(embed=embed)
            except: pass

    async def _generate_poll_embed(self, guild: discord.Guild) -> discord.Embed:
        """Generates the main poll embed with sample and leaders."""
        poll_data = await self.config.guild(guild).active_poll()
        boss_pool = await self.config.guild(guild).boss_pool()
        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))
        sorted_names = [b[0] for b in sorted(tally.items(), key=lambda x: x[1], reverse=True)]
        
        embed = discord.Embed(title="⚔️ Breaking Army: Permanent Boss Poll", color=discord.Color.gold())
        embed.description = "Vote for your favorite bosses to determine the next 6-week season roster!"
        
        # 1. Sample Season
        sample = (
            "**W1**: Anchor 1 & Guest 1\n"
            "**W2**: Anchor 2 & Guest 2\n"
            "**W3**: Anchor 3 & Guest 3\n"
            "**W4**: Anchor 1 & Guest 1 (Encore)\n"
            "**W5**: Anchor 2 & Guest 4\n"
            "**W6**: Anchor 3 & Guest 5"
        )
        embed.add_field(name="📋 Season Structure (Rotation)", value=sample, inline=False)
        
        # 2. Current Leaders
        if len(sorted_names) < 8:
            leaders = f"⚠️ *Not enough votes to form a season ({len(sorted_names)}/8 bosses)*"
        else:
            def get_n(n): return f"{boss_pool.get(sorted_names[n], '⚔️')} {sorted_names[n]}"
            leaders = (
                f"1. {get_n(0)} (Anchor 1)\n"
                f"2. {get_n(1)} (Anchor 2)\n"
                f"3. {get_n(2)} (Anchor 3)\n"
                f"4. {get_n(3)} (Guest 1 - Encore)\n"
                f"5. {get_n(4)} (Guest 2)\n"
                f"6. {get_n(5)} (Guest 3)\n"
                f"7. {get_n(6)} (Guest 4)\n"
                f"8. {get_n(7)} (Guest 5)"
            )
        embed.add_field(name="📊 Current Leaders", value=leaders, inline=False)
        
        embed.set_footer(text=f"Total Voters: {len(poll_data.get('votes', {}))} | Updates live on vote")
        return embed

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
                winners = polling_cog._calculate_winning_times_weighted(polls[latest_poll_id].get("selections", {}))
                ba_winners = winners.get("Breaking Army", {})
                server_tz = timezone(timedelta(hours=1))
                now = datetime.now(server_tz)
                trigger = False
                for slot in ba_winners.values():
                    if slot[0][0] == now.strftime("%A") and slot[0][1] == now.strftime("%H:%M"):
                        trigger = True; break
                if trigger:
                    last = await self.config.guild(guild).active_run.last_auto_trigger()
                    if last != now.strftime("%Y-%m-%dT%H:%M"):
                        await self.config.guild(guild).active_run.last_auto_trigger.set(now.strftime("%Y-%m-%dT%H:%M"))
                        await self._auto_start_run(guild)
        except Exception as e: log.error(f"Checker error: {e}")

    async def _setup_new_season_logic(self, guild: discord.Guild) -> Optional[discord.Embed]:
        poll_data = await self.config.guild(guild).active_poll()
        boss_pool = await self.config.guild(guild).boss_pool()
        seen_bosses = await self.config.guild(guild).seen_bosses()
        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))
        ranked = [b[0] for b in sorted(tally.items(), key=lambda x: x[1], reverse=True)]
        if len(ranked) < 8: return None
        new_b = [b for b in ranked if b not in seen_bosses]
        a = [None]*3; g = [None]*5; used = []
        if len(new_b) >= 1: a[0] = new_b[0]; used.append(new_b[0])
        if len(new_b) >= 2: g[0] = new_b[1]; used.append(new_b[1])
        if len(new_b) >= 3: a[2] = new_b[2]; used.append(new_b[2])
        rem = [b for b in ranked if b not in used]
        for i in range(3):
            if a[i] is None: a[i] = rem.pop(0); used.append(a[i])
        for i in range(5):
            if g[i] is None: g[i] = rem.pop(0); used.append(g[i])
        async with self.config.guild(guild).season_data() as s:
            s["anchors"] = a; s["guests"] = g; s["current_week"] = 1; s["is_active"] = True
        async with self.config.guild(guild).seen_bosses() as s:
            for b in used: 
                if b not in s: s.append(b)
        embed = discord.Embed(title="🚀 New Season Initialized", color=discord.Color.green())
        def fmt(name): return f"{boss_pool.get(name, '⚔️')} **{name}**" + (" ✨" if name in new_b[:3] else "")
        embed.add_field(name="Anchors", value="\n".join([f"{i+1}. {fmt(x)}" for i, x in enumerate(a)]), inline=True)
        embed.add_field(name="Guests", value="\n".join([f"{i+1}. {fmt(x)}" for i, x in enumerate(g)]), inline=True)
        return embed

    async def _auto_start_run(self, guild):
        season = await self.config.guild(guild).season_data()
        if not season["is_active"]:
            setup_embed = await self._setup_new_season_logic(guild)
            if not setup_embed:
                poll_data = await self.config.guild(guild).active_poll()
                chan = guild.get_channel(poll_data["channel_id"])
                if chan: await chan.send("⚠️ **Season failed:** Need 8 bosses with votes.")
                return
            poll_data = await self.config.guild(guild).active_poll()
            chan = guild.get_channel(poll_data["channel_id"])
            if chan: await chan.send(embed=setup_embed)
            season = await self.config.guild(guild).season_data()
        week = season["current_week"]; a = season["anchors"]; g = season["guests"]
        if week == 1: boss_list = [a[0], g[0]]
        elif week == 2: boss_list = [a[1], g[1]]
        elif week == 3: boss_list = [a[2], g[2]]
        elif week == 4: boss_list = [a[0], g[0]]
        elif week == 5: boss_list = [a[1], g[3]]
        elif week == 6: boss_list = [a[2], g[4]]
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

    @ba.command(name="clearall")
    async def ba_clear_all(self, ctx: commands.Context):
        """
        Unload all active embeds and wipe session memory.
        
        This stops the current run and unlinks the active poll.
        Config (Boss Pool, Seen Bosses) is preserved.
        """
        if not await self.is_ba_admin(ctx.author):
            return await ctx.send("Permission denied.")

        # Wipe Poll Session
        await self.config.guild(ctx.guild).active_poll.set({
            "message_id": None,
            "channel_id": None,
            "votes": {}
        })

        # Wipe Run Session
        await self.config.guild(ctx.guild).active_run.set({
            "message_id": None,
            "channel_id": None,
            "boss_order": [],
            "current_index": -1,
            "is_running": False,
            "last_auto_trigger": None
        })

        await ctx.send("✅ **Success:** All active poll and run sessions have been cleared from memory.")

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

    @ba_poll.command(name="start")
    async def poll_start(self, ctx: commands.Context):
        if not await self.config.guild(ctx.guild).boss_pool(): return await ctx.send("Pool empty.")
        embed = await self._generate_poll_embed(ctx.guild)
        view = BossPollView(self)
        msg = await ctx.send(embed=embed, view=view)
        async with self.config.guild(ctx.guild).active_poll() as p:
            p["message_id"] = msg.id; p["channel_id"] = msg.channel.id

    @ba_poll.command(name="snapshot")
    async def poll_snapshot(self, ctx: commands.Context):
        poll = await self.config.guild(ctx.guild).active_poll()
        if not poll["message_id"]: return await ctx.send("No poll.")
        tally = self._calculate_weighted_tally(poll.get("votes", {}))
        thresh = await self.config.guild(ctx.guild).min_vote_threshold()
        limit = await self.config.guild(ctx.guild).max_bosses_in_run()
        cands = sorted([(b, c) for b, c in tally.items() if c >= thresh], key=lambda x: x[1], reverse=True)
        flist = [b for b, c in cands[:limit]]
        if not flist: return await ctx.send("No bosses met threshold.")
        await self.config.guild(ctx.guild).active_run.set({"boss_order": flist, "current_index": -1, "is_running": False})
        await self._start_run_display(ctx, flist)

    @ba_poll.command(name="close")
    async def poll_close(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).active_poll.set({"message_id": None, "channel_id": None, "votes": {}})
        await ctx.send("Poll closed.")

    @ba_poll.command(name="resetvotes")
    async def poll_reset_votes(self, ctx: commands.Context):
        async with self.config.guild(ctx.guild).active_poll() as p: p["votes"] = {}
        await self._update_poll_embed(ctx.guild)
        await ctx.send("Votes cleared.")

    async def _start_run_display(self, ctx, boss_list):
        embed = await self._generate_run_embed(ctx.guild, boss_list, -1, False)
        msg = await ctx.send(embed=embed)
        async with self.config.guild(ctx.guild).active_run() as r:
            r["message_id"] = msg.id; r["channel_id"] = msg.channel.id

    async def _generate_run_embed(self, guild, boss_list, current_index, is_running):
        pool = await self.config.guild(guild).boss_pool(); desc = ""
        for i, b in enumerate(boss_list):
            e = pool.get(b, "⚔️")
            if i < current_index: desc += f"💀 ~~{e} {b}~~\n"
            elif i == current_index and is_running: desc += f"⚔️ **__ {e} {b} __** (Target)\n"
            else: desc += f"⏳ {e} {b}\n"
        return discord.Embed(title=f"Breaking Army Run - {'Active' if is_running else 'Queued'}", description=desc, color=discord.Color.green())

class BossVoteModal(Modal, title="Hybrid Boss Ballot"):
    def __init__(self, cog, guild, user_id, pool, current_votes):
        super().__init__()
        self.cog = cog; self.guild = guild; self.user_id = user_id
        Label_cls = Label or getattr(discord.ui, "Label", None)
        
        # Parse current votes
        # current_votes = [anchors_list, encore_str, guests_list]
        cur_anchors = current_votes[0] if current_votes and isinstance(current_votes[0], list) else []
        cur_encore = current_votes[1] if current_votes and len(current_votes) > 1 else None
        cur_guests = current_votes[2] if current_votes and len(current_votes) > 2 and isinstance(current_votes[2], list) else []

        options = [discord.SelectOption(label=n, value=n, emoji=e) for n, e in list(pool.items())[:25]]
        
        # 3 Weighted Choice Dropdowns
        anchor_opts = [discord.SelectOption(label=n, value=n, emoji=e, default=(n in cur_anchors)) for n, e in list(pool.items())[:25]]
        self.anchor = StringSelect(placeholder="Select up to 3 Anchors...", min_values=0, max_values=3, options=anchor_opts, custom_id="anchor")
        
        encore_opts = [discord.SelectOption(label=n, value=n, emoji=e, default=(n == cur_encore)) for n, e in list(pool.items())[:25]]
        self.encore = StringSelect(placeholder="Select Encore Preference...", min_values=0, options=encore_opts, custom_id="encore")
        
        guest_opts = [discord.SelectOption(label=n, value=n, emoji=e, default=(n in cur_guests)) for n, e in list(pool.items())[:25]]
        self.guests = StringSelect(placeholder="Select up to 4 other bosses...", min_values=0, max_values=4, options=guest_opts, custom_id="guests")
        
        if Label_cls:
            self.add_item(Label_cls("Anchor Votes (2.5 pts ea, max 3)", self.anchor))
            self.add_item(Label_cls("Encore Vote (1 pt)", self.encore))
            self.add_item(Label_cls("Guest Votes (1 pt ea)", self.guests))
        else:
            self.add_item(self.anchor); self.add_item(self.encore); self.add_item(self.guests)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        choices = [
            self.anchor.values if self.anchor.values else [],
            self.encore.values[0] if self.encore.values else None,
            self.guests.values if self.guests.values else []
        ]
        async with self.cog.config.guild(interaction.guild).active_poll() as p:
            p["votes"][str(interaction.user.id)] = choices
        await self.cog._update_poll_embed(interaction.guild)
        await interaction.followup.send("Ballot Saved!", ephemeral=True)

class BossPollView(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog
    
    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="ba_vote")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = await self.cog.config.guild(interaction.guild).boss_pool()
        poll_data = await self.cog.config.guild(interaction.guild).active_poll()
        cur_votes = poll_data.get("votes", {}).get(str(interaction.user.id), [])
        await interaction.response.send_modal(BossVoteModal(self.cog, interaction.guild, interaction.user.id, pool, cur_votes))

    @discord.ui.button(label="Total Results", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="ba_results")
    async def results(self, interaction: discord.Interaction, button: discord.ui.Button):
        poll = await self.cog.config.guild(interaction.guild).active_poll()
        boss_pool = await self.cog.config.guild(interaction.guild).boss_pool()
        tally = self.cog._calculate_weighted_tally(poll.get("votes", {}))
        ranked = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        
        if not ranked:
            await interaction.response.send_message("No votes yet.", ephemeral=True); return
            
        res = "**Current Ranked Totals:**\n"
        for i, (name, pts) in enumerate(ranked):
            role = ""
            if i == 0: role = " (Anchor 1)"
            elif i == 1: role = " (Anchor 2)"
            elif i == 2: role = " (Anchor 3)"
            elif i == 3: role = " (Guest 1 - Encore)"
            elif i <= 7: role = f" (Guest {i-2})"
            
            res += f"{i+1}. {boss_pool.get(name, '⚔️')} **{name}**: {pts:g} pts{role}\n"
        await interaction.response.send_message(res, ephemeral=True)
