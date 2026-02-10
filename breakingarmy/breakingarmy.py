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
            "new_boss_emote": "✨",
            "max_bosses_in_run": 5,
            "min_vote_threshold": 3,
            "active_poll": {
                "message_id": None,
                "channel_id": None,
                "votes": {}, 
            },
            "active_run": {
                "message_id": None,
                "channel_id": None,
                "boss_order": [], 
                "current_index": -1,
                "is_running": False,
                "start_time": None,
                "last_auto_trigger": None
            },
            "season_data": {
                "current_week": 1,
                "anchors": [], 
                "guests": [],
                "priority_bosses": [], # Bosses that get the 'new' emote this season
                "is_active": False,
                "live_season_message": {} 
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
        tally = {}
        for choices in votes.values():
            if not isinstance(choices, list) or len(choices) < 3: continue
            anchors = choices[0]
            if isinstance(anchors, list):
                for a in anchors:
                    if a: tally[a] = tally.get(a, 0) + 2.5
            elif isinstance(anchors, str):
                tally[anchors] = tally.get(anchors, 0) + 2.5
            e = choices[1]
            if e: tally[e] = tally.get(e, 0) + 1
            gs = choices[2]
            if isinstance(gs, list):
                for g in gs:
                    if g: tally[g] = tally.get(g, 0) + 1
        return tally

    async def _update_poll_embed(self, guild: discord.Guild):
        poll = await self.config.guild(guild).active_poll()
        if not poll["message_id"]: return
        try:
            channel = guild.get_channel(poll["channel_id"])
            if not channel: return
            msg = await channel.fetch_message(poll["message_id"])
            embed = await self._generate_poll_embed(guild)
            await msg.edit(embed=embed)
        except Exception as e:
            log.error(f"Error updating poll embed: {e}")

    async def _generate_poll_embed(self, guild: discord.Guild) -> discord.Embed:
        poll_data = await self.config.guild(guild).active_poll()
        boss_pool = await self.config.guild(guild).boss_pool()
        seen_bosses = await self.config.guild(guild).seen_bosses()
        new_emote = await self.config.guild(guild).new_boss_emote()
        
        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))
        sorted_names = [b[0] for b in sorted(tally.items(), key=lambda x: x[1], reverse=True)]
        embed = discord.Embed(title="⚔️ Breaking Army: Boss Poll", color=discord.Color.gold())
        embed.description = "Vote for your favorite bosses to determine the next 6-week season roster!"
        sample = (
            "**Week 1**: Anchor 1 & Guest 1\n"
            "**Week 2**: Anchor 2 & Guest 2\n"
            "**Week 3**: Anchor 3 & Guest 3\n"
            "**Week 4**: Anchor 1 & Guest 1 (Encore)\n"
            "**Week 5**: Anchor 2 & Guest 4\n"
            "**Week 6**: Anchor 3 & Guest 5"
        )
        embed.add_field(name="📋 Season Structure (Rotation)", value=sample, inline=False)
        
        if len(sorted_names) < 8:
            leaders = f"⚠️ *Not enough votes to form a season ({len(sorted_names)}/8 bosses)*"
        else:
            def get_n(n): 
                name = sorted_names[n]
                emote = boss_pool.get(name, '⚔️')
                suffix = f" {new_emote}" if name not in seen_bosses else ""
                return f"{emote} {name}{suffix}"
                
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

    async def _refresh_live_season_view(self, guild: discord.Guild):
        season = await self.config.guild(guild).season_data()
        live = season.get("live_season_message", {})
        if not live.get("message_id"): return
        try:
            channel = guild.get_channel(live["channel_id"])
            if not channel: return
            msg = await channel.fetch_message(live["message_id"])
            embeds = await self._generate_season_status_embeds(guild)
            
            # Add Link Button
            poll_data = await self.config.guild(guild).active_poll()
            view = None
            if poll_data.get("message_id"):
                url = f"https://discord.com/channels/{guild.id}/{poll_data['channel_id']}/{poll_data['message_id']}"
                view = SeasonLiveView(url)
                
            await msg.edit(embeds=embeds, view=view)
        except: pass

    async def _generate_season_status_embeds(self, guild: discord.Guild) -> List[discord.Embed]:
        season = await self.config.guild(guild).season_data()
        run = await self.config.guild(guild).active_run()
        boss_pool = await self.config.guild(guild).boss_pool()
        new_emote = await self.config.guild(guild).new_boss_emote()
        priority = season.get("priority_bosses", [])
        
        color = discord.Color.green() if season["is_active"] else discord.Color.purple()
        sched_embed = discord.Embed(title="📅 Breaking Army Season Status", color=color)
        
        a = season["anchors"]; g = season["guests"]
        if not a: 
            sched_embed.description = "No season initialized."
            return [sched_embed]

        def get_fmt_name(n):
            e = boss_pool.get(n, "⚔️")
            suffix = f" {new_emote}" if n in priority else ""
            return f"{e} {n}{suffix}"

        sched = ""
        matrix = [(a[0],g[0]), (a[1],g[1]), (a[2],g[2]), (a[0],g[0]), (a[1],g[3]), (a[2],g[4])]
        for i, (b1, b2) in enumerate(matrix):
            w = i+1; enc = " (Encore)" if w == 4 else ""
            n1 = get_fmt_name(b1); n2 = get_fmt_name(b2)
            if w < season["current_week"]:
                sched += f"💀 ~~**Week {w}**: {n1} & {n2}{enc}~~\n"
            elif w == season["current_week"] and season["is_active"]:
                sched += f"⚔️ **__Week {w}__: {n1} & {n2}{enc}** (Active)\n"
            else:
                sched += f"⏳ **Week {w}**: {n1} & {n2}{enc}\n"
        sched_embed.description = sched
        
        embeds = [sched_embed]
        if run["is_running"]:
            run_embed = await self._generate_run_embed(guild, run["boss_order"], run["current_index"], True)
            run_embed.title = "🔥 Current Active Run"
            embeds.append(run_embed)
        return embeds

    @tasks.loop(minutes=1)
    async def schedule_checker(self):
        try:
            for guild_id in await self.config.all_guilds():
                guild = self.bot.get_guild(guild_id)
                if not guild: continue
                
                server_tz = timezone(timedelta(hours=1))
                now = datetime.now(server_tz)
                day_name = now.strftime("%A")
                time_str = now.strftime("%H:%M")

                # 1. Auto-Death (1 hour)
                run = await self.config.guild(guild).active_run()
                if run["is_running"] and run["current_index"] == 0 and run["start_time"]:
                    start = datetime.fromisoformat(run["start_time"])
                    if datetime.now(timezone.utc) >= start + timedelta(hours=1):
                        await self._advance_run(guild)

                # 2. Season Reset (Sunday 22:00)
                if day_name == "Sunday" and time_str == "22:00":
                    season = await self.config.guild(guild).season_data()
                    if not season["is_active"] and season.get("current_week", 1) > 6:
                        setup_embed = await self._setup_new_season_logic(guild)
                        if setup_embed:
                            poll_data = await self.config.guild(guild).active_poll()
                            channel = guild.get_channel(poll_data["channel_id"])
                            if channel: await channel.send(embed=setup_embed)
                            await self._refresh_live_season_view(guild)

                # 3. Schedule Trigger
                polling_cog = self.bot.get_cog("EventPolling")
                if not polling_cog: continue
                polls = await polling_cog.config.guild(guild).polls()
                if not polls: continue
                latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                poll_data = polls[latest_poll_id]
                snapshot = poll_data.get("weekly_snapshot_winning_times")
                winners = snapshot if snapshot else polling_cog._calculate_winning_times_weighted(poll_data.get("selections", {}))
                
                ba_winners = winners.get("Breaking Army", {})
                trigger = False
                for slot in ba_winners.values():
                    if slot[0][0] == day_name and slot[0][1] == time_str:
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
        new_emote = await self.config.guild(guild).new_boss_emote()
        
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
            s["priority_bosses"] = new_b[:3]
            
        async with self.config.guild(guild).seen_bosses() as seen:
            for b in used: 
                if b not in seen: seen.append(b)
        
        embed = discord.Embed(title="🚀 New Season Initialized", color=discord.Color.green())
        def fmt(name): return f"{boss_pool.get(name, '⚔️')} **{name}**" + (f" {new_emote}" if name in new_b[:3] else "")
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
        
        now_utc = datetime.now(timezone.utc).isoformat()
        await self.config.guild(guild).active_run.set({"boss_order": boss_list, "current_index": 0, "is_running": True, "start_time": now_utc})
        
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
        await self._refresh_live_season_view(guild)

    async def _advance_run(self, guild: discord.Guild):
        async with self.config.guild(guild).active_run() as run:
            if not run["is_running"]: return
            run["current_index"] += 1
            if run["current_index"] >= len(run["boss_order"]):
                run["is_running"] = False
            try:
                channel = guild.get_channel(run["channel_id"])
                msg = await channel.fetch_message(run["message_id"])
                embed = await self._generate_run_embed(guild, run["boss_order"], run["current_index"], run["is_running"])
                await msg.edit(embed=embed)
            except: pass
        await self._refresh_live_season_view(guild)

    @commands.group(name="ba")
    @commands.guild_only()
    async def ba(self, ctx: commands.Context):
        """Breaking Army Management"""
        pass

    @ba.command(name="refresh")
    async def ba_refresh(self, ctx: commands.Context):
        """Force update all active embeds (Poll, Season Live View, and Run Dashboard)."""
        if not await self.is_ba_admin(ctx.author):
            return await ctx.send("Permission denied.")

        # 1. Refresh Poll
        await self._update_poll_embed(ctx.guild)

        # 2. Refresh Season Live View
        await self._refresh_live_season_view(ctx.guild)

        # 3. Refresh Standalone Run Dashboard
        run = await self.config.guild(ctx.guild).active_run()
        if run.get("message_id") and run.get("is_running"):
            try:
                channel = ctx.guild.get_channel(run["channel_id"])
                if channel:
                    msg = await channel.fetch_message(run["message_id"])
                    embed = await self._generate_run_embed(ctx.guild, run["boss_order"], run["current_index"], run["is_running"])
                    await msg.edit(embed=embed)
            except: pass

        await ctx.send("✅ **Refreshed:** All active embeds have been updated with the latest data.")

    @ba.command(name="clearall")
    async def ba_clear_all(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): return await ctx.send("Permission denied.")
        await self.config.guild(ctx.guild).active_poll.set({"message_id": None, "channel_id": None, "votes": {}})
        await self.config.guild(ctx.guild).active_run.set({"message_id": None, "channel_id": None, "boss_order": [], "current_index": -1, "is_running": False, "start_time": None, "last_auto_trigger": None})
        async with self.config.guild(ctx.guild).season_data() as s: 
            s["live_season_message"] = {}
            s["is_active"] = False
            s["current_week"] = 1
            s["priority_bosses"] = []
        await ctx.send("✅ **Success:** All sessions cleared.")

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

    @ba_config.command(name="newemote")
    async def config_new_emote(self, ctx: commands.Context, emote: str):
        """Set the emote used to indicate a New Priority boss."""
        await self.config.guild(ctx.guild).new_boss_emote.set(emote)
        await ctx.send(f"New priority boss emote set to: {emote}")

    @ba_config.command(name="editboss")
    async def config_edit_boss(self, ctx: commands.Context, old_name: str, new_name: str, new_emoji: Optional[str] = None):
        """Edit a boss's name and/or emote."""
        async with self.config.guild(ctx.guild).boss_pool() as pool:
            if old_name not in pool:
                return await ctx.send(f"Boss '{old_name}' not found.")
            
            emote = new_emoji if new_emoji else pool[old_name]
            del pool[old_name]
            pool[new_name] = emote

        # Migrate seen_bosses
        async with self.config.guild(ctx.guild).seen_bosses() as seen:
            if old_name in seen:
                seen[seen.index(old_name)] = new_name

        # Migrate votes
        async with self.config.guild(ctx.guild).active_poll.votes() as votes:
            for uid, ballot in votes.items():
                if not isinstance(ballot, list): continue
                # Anchors
                if isinstance(ballot[0], list):
                    votes[uid][0] = [new_name if b == old_name else b for b in ballot[0]]
                elif ballot[0] == old_name:
                    votes[uid][0] = new_name
                # Encore
                if ballot[1] == old_name: votes[uid][1] = new_name
                # Guests
                if isinstance(ballot[2], list):
                    votes[uid][2] = [new_name if b == old_name else b for b in ballot[2]]

        # Migrate Season Data
        async with self.config.guild(ctx.guild).season_data() as s:
            s["anchors"] = [new_name if b == old_name else b for b in s["anchors"]]
            s["guests"] = [new_name if b == old_name else b for b in s["guests"]]
            s["priority_bosses"] = [new_name if b == old_name else b for b in s["priority_bosses"]]

        # Migrate Active Run
        async with self.config.guild(ctx.guild).active_run() as r:
            r["boss_order"] = [new_name if b == old_name else b for b in r["boss_order"]]

        await ctx.send(f"✅ **Updated:** '{old_name}' is now {emote} '{new_name}'. All records migrated.")
        await self._update_poll_embed(ctx.guild)
        await self._refresh_live_season_view(ctx.guild)

    @ba.group(name="season")
    async def ba_season(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_season.command(name="setup")
    async def season_setup(self, ctx: commands.Context):
        embed = await self._setup_new_season_logic(ctx.guild)
        if embed: 
            await ctx.send(embed=embed)
            await self._refresh_live_season_view(ctx.guild)
        else: await ctx.send("Failed setup. Need 8 unique bosses with votes.")

    @ba_season.command(name="setweek")
    async def season_set_week(self, ctx: commands.Context, week: int):
        if not (1 <= week <= 6): return await ctx.send("Week must be between 1 and 6.")
        async with self.config.guild(ctx.guild).season_data() as s:
            s["current_week"] = week; s["is_active"] = True
        await ctx.send(f"✅ **Success:** Current week set to **Week {week}**.")
        await self._refresh_live_season_view(ctx.guild)

    @ba_season.command(name="show")
    async def season_show(self, ctx: commands.Context):
        embeds = await self._generate_season_status_embeds(ctx.guild)
        await ctx.send(embeds=embeds)

    @ba_season.command(name="live")
    async def season_live(self, ctx: commands.Context):
        embeds = await self._generate_season_status_embeds(ctx.guild)
        poll_data = await self.config.guild(ctx.guild).active_poll()
        view = None
        if poll_data.get("message_id"):
            url = f"https://discord.com/channels/{ctx.guild.id}/{poll_data['channel_id']}/{poll_data['message_id']}"
            view = SeasonLiveView(url)
        msg = await ctx.send(embeds=embeds, view=view)
        async with self.config.guild(ctx.guild).season_data() as s:
            s["live_season_message"] = {"message_id": msg.id, "channel_id": msg.channel.id}

    @ba.group(name="run")
    async def ba_run(self, ctx: commands.Context):
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_run.command(name="start")
    async def run_manual_start(self, ctx: commands.Context):
        await self._auto_start_run(ctx.guild); await ctx.send("Manual run triggered.")

    @ba_run.command(name="next", aliases=["bossdown"])
    async def run_next(self, ctx: commands.Context):
        await self._advance_run(ctx.guild)
        await ctx.tick()

    @ba_run.command(name="cancel")
    async def run_cancel(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).active_run.is_running.set(False); await ctx.send("Run cancelled.")
        await self._refresh_live_season_view(ctx.guild)

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
        await self.config.guild(ctx.guild).active_run.set({"boss_order": flist, "current_index": -1, "is_running": False, "start_time": None})
        await self._start_run_display(ctx, flist)

    @ba_poll.command(name="close")
    async def poll_close(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).active_poll.set({"message_id": None, "channel_id": None, "votes": {}})
        await ctx.send("Poll closed.")

    @ba_poll.command(name="resetvotes")
    async def poll_reset_votes(self, ctx: commands.Context):
        async with self.config.guild(ctx.guild).active_poll() as p: p["votes"] = {}
        await self._update_poll_embed(ctx.guild); await ctx.send("Votes cleared.")

    async def _start_run_display(self, ctx, boss_list):
        embed = await self._generate_run_embed(ctx.guild, boss_list, -1, False)
        msg = await ctx.send(embed=embed)
        async with self.config.guild(ctx.guild).active_run() as r:
            r["message_id"] = msg.id; r["channel_id"] = msg.channel.id

    async def _generate_run_embed(self, guild, boss_list, current_index, is_running):
        pool = await self.config.guild(guild).boss_pool(); desc = ""
        new_emote = await self.config.guild(guild).new_boss_emote()
        season = await self.config.guild(guild).season_data()
        priority = season.get("priority_bosses", [])
        for i, b in enumerate(boss_list):
            e = pool.get(b, "⚔️")
            suffix = f" {new_emote}" if b in priority else ""
            if i < current_index: desc += f"💀 ~~{e} {b}{suffix}~~\n"
            elif i == current_index and is_running: desc += f"⚔️ **__ {e} {b}{suffix} __** (Target)\n"
            else: desc += f"⏳ {e} {b}{suffix}\n"
        return discord.Embed(title=f"Breaking Army Run - {'Active' if is_running else 'Queued'}", description=desc, color=discord.Color.green())

class SeasonLiveView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Go to Poll", style=discord.ButtonStyle.link, url=url))

class BossVoteModal(Modal, title="Hybrid Boss Ballot"):
    def __init__(self, cog, guild, user_id, pool, current_votes):
        super().__init__()
        self.cog = cog; self.guild = guild; self.user_id = user_id
        Label_cls = Label or getattr(discord.ui, "Label", None)
        cur_anchors = current_votes[0] if current_votes and isinstance(current_votes[0], list) else []
        cur_encore = current_votes[1] if current_votes and len(current_votes) > 1 else None
        cur_guests = current_votes[2] if current_votes and len(current_votes) > 2 and isinstance(current_votes[2], list) else []
        anchor_opts = [discord.SelectOption(label=n, value=n, emoji=e, default=(n in cur_anchors)) for n, e in list(pool.items())[:25]]
        self.anchor = StringSelect(placeholder="Select up to 3 Anchors...", min_values=0, max_values=3, options=anchor_opts, custom_id="anchor")
        encore_opts = [discord.SelectOption(label=n, value=n, emoji=e, default=(n == cur_encore)) for n, e in list(pool.items())[:25]]
        self.encore = StringSelect(placeholder="Select Encore Preference...", min_values=0, options=encore_opts, custom_id="encore")
        guest_opts = [discord.SelectOption(label=n, value=n, emoji=e, default=(n in cur_guests)) for n, e in list(pool.items())[:25]]
        self.guests = StringSelect(placeholder="Select up to 4 other bosses...", min_values=0, max_values=4, options=guest_opts, custom_id="guests")
        if Label_cls:
            self.add_item(Label_cls("Anchor Votes (2.5 pts ea, max 3)", self.anchor))
            self.add_item(Label_cls("Encore Vote (1 pt)", self.encore))
            self.add_item(Label_cls("Guest Votes (1 pt ea, max 4)", self.guests))
        else:
            self.add_item(self.anchor); self.add_item(self.encore); self.add_item(self.guests)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        choices = [self.anchor.values if self.anchor.values else [], self.encore.values[0] if self.encore.values else None, self.guests.values if self.guests.values else []]
        async with self.cog.config.guild(interaction.guild).active_poll() as p: p["votes"][str(interaction.user.id)] = choices
        await self.cog._update_poll_embed(interaction.guild); await interaction.followup.send("Ballot Saved!", ephemeral=True)

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
        new_emote = await self.cog.config.guild(interaction.guild).new_boss_emote()
        seen_bosses = await self.cog.config.guild(interaction.guild).seen_bosses()
        tally = self.cog._calculate_weighted_tally(poll.get("votes", {}))
        ranked = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        if not ranked: return await interaction.response.send_message("No votes yet.", ephemeral=True)
        res = "**Current Ranked Totals:**\n"
        for i, (name, pts) in enumerate(ranked):
            role = ""
            if i == 0: role = " (Anchor 1)"
            elif i == 1: role = " (Anchor 2)"
            elif i == 2: role = " (Anchor 3)"
            elif i == 3: role = " (Guest 1 - Encore)"
            elif i <= 7: role = f" (Guest {i-2})"
            suffix = f" {new_emote}" if name not in seen_bosses else ""
            res += f"{i+1}. {boss_pool.get(name, '⚔️')} **{name}**{suffix}: {pts:g} pts{role}\n"
        await interaction.response.send_message(res, ephemeral=True)
