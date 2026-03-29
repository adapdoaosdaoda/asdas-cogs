import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
import asyncio
import logging
import pytz
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Union, Any

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
            "notification_channel": None,
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

    async def cog_load(self):
        """Called when the cog is loaded"""
        self.bot.add_view(BossPollView(self))

    def cog_unload(self):
        self.schedule_checker.cancel()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Remove votes when a user leaves the server"""
        async with self.config.guild(member.guild).active_poll.votes() as votes:
            user_id_str = str(member.id)
            if user_id_str in votes:
                del votes[user_id_str]
                log.info(f"Removed Breaking Army votes for user {member.id} because they left the server.")
                await self._update_poll_embed(member.guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Remove votes when a user loses the required roles (@Member or @Friend of the Guild)"""
        # Specific role IDs: @Member and @Friend of the Guild
        target_role_ids = {1439747785644703754, 1452430729115078850}
        
        def has_any_target_role(member):
            return any(role.id in target_role_ids for role in member.roles)

        if has_any_target_role(before) and not has_any_target_role(after):
            async with self.config.guild(after.guild).active_poll.votes() as votes:
                user_id_str = str(after.id)
                if user_id_str in votes:
                    del votes[user_id_str]
                    log.info(f"Removed Breaking Army votes for user {after.id} because they lost their member roles.")
                    await self._update_poll_embed(after.guild)

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
        """Update the active poll embed if one exists."""
        poll = await self.config.guild(guild).active_poll()
        if not poll.get("message_id"):
            log.debug(f"No active poll message tracked for guild {guild.id}")
            return

        channel_id = poll["channel_id"]
        message_id = poll["message_id"]

        try:
            channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.NotFound:
                    log.warning(f"Poll channel {channel_id} not found in guild {guild.id}. Clearing tracked poll.")
                    async with self.config.guild(guild).active_poll() as p:
                        p["message_id"] = None
                        p["channel_id"] = None
                    return
                except discord.Forbidden:
                    log.error(f"Permission denied fetching poll channel {channel_id} in guild {guild.id}")
                    return

            try:
                msg = await channel.fetch_message(message_id)
            except discord.NotFound:
                log.warning(f"Poll message {message_id} not found in channel {channel_id}. Clearing tracked poll.")
                async with self.config.guild(guild).active_poll() as p:
                    p["message_id"] = None
                    p["channel_id"] = None
                return
            except discord.Forbidden:
                log.error(f"Permission denied fetching poll message {message_id} in channel {channel_id}")
                return

            embed = await self._generate_poll_embed(guild)
            view = BossPollView(self)
            await msg.edit(embed=embed, view=view)
            log.debug(f"Successfully updated poll embed for guild {guild.id}")
        except Exception as e:
            log.error(f"Unexpected error updating poll embed for guild {guild.id}: {e}", exc_info=True)

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
        """Update the persistent live season status message if one exists."""
        season = await self.config.guild(guild).season_data()
        live = season.get("live_season_message", {})
        if not live.get("message_id"):
            log.debug(f"No live season message tracked for guild {guild.id}")
            return

        channel_id = live["channel_id"]
        message_id = live["message_id"]

        try:
            channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.NotFound:
                    log.warning(f"Live season channel {channel_id} not found in guild {guild.id}. Clearing tracked message.")
                    async with self.config.guild(guild).season_data() as s:
                        s["live_season_message"] = {}
                    return
                except discord.Forbidden:
                    log.error(f"Permission denied fetching live season channel {channel_id} in guild {guild.id}")
                    return

            try:
                msg = await channel.fetch_message(message_id)
            except discord.NotFound:
                log.warning(f"Live season message {message_id} not found in channel {channel_id}. Clearing tracked message.")
                async with self.config.guild(guild).season_data() as s:
                    s["live_season_message"] = {}
                return
            except discord.Forbidden:
                log.error(f"Permission denied fetching live season message {message_id} in channel {channel_id}")
                return

            embeds = await self._generate_season_status_embeds(guild)
            
            poll_data = await self.config.guild(guild).active_poll()
            view = None
            if poll_data.get("message_id"):
                url = f"https://discord.com/channels/{guild.id}/{poll_data['channel_id']}/{poll_data['message_id']}"
                view = SeasonLiveView(url)
                
            await msg.edit(embeds=embeds, view=view)
            log.debug(f"Successfully refreshed live season view for guild {guild.id}")
        except Exception as e:
            log.error(f"Unexpected error refreshing live season view for guild {guild.id}: {e}", exc_info=True)

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
                if run["is_running"]:
                    sched += f"⚔️ **__Week {w}__: {n1} & {n2}{enc}** (Active)\n"
                else:
                    sched += f"⏳ **Week {w}__: {n1} & {n2}{enc}** (Waiting)\n"
            else:
                sched += f"⏳ **Week {w}**: {n1} & {n2}{enc}\n"
        sched_embed.description = sched
        
        embeds = [sched_embed]
        # Always show run dashboard if season is active
        if season["is_active"] and (run["boss_order"] or run["is_running"]):
            run_embed = await self._generate_run_embed(guild, run["boss_order"], run["current_index"], run["is_running"])
            run_embed.title = f"🔥 Week {season['current_week']}"
            embeds.append(run_embed)
        return embeds

    def _get_bosses_for_week(self, season: Dict, week: int) -> List[str]:
        if not season["anchors"] or not season["guests"]: return []
        a = season["anchors"]; g = season["guests"]
        matrix = [(a[0],g[0]), (a[1],g[1]), (a[2],g[2]), (a[0],g[0]), (a[1],g[3]), (a[2],g[4])]
        if 1 <= week <= 6:
            return list(matrix[week-1])
        return []

    @tasks.loop(minutes=1)
    async def schedule_checker(self):
        try:
            for guild_id in await self.config.all_guilds():
                guild = self.bot.get_guild(guild_id)
                if not guild: continue
                
                from datetime import timezone
                server_tz = timezone(timedelta(hours=1))
                now = datetime.now(server_tz)
                day_name = now.strftime("%A")
                time_str = now.strftime("%H:%M")
                
                # Night logic: Times 00:00 - 02:59 are considered part of the "night" of the previous day
                # We use 03:00 as the cutoff to match EventPolling's next-day threshold
                is_next_day = now.hour < 3
                prev_day_name = (now - timedelta(days=1)).strftime("%A")

                # 1. Auto-Death (2 hours)
                run = await self.config.guild(guild).active_run()
                if run["is_running"] and run["current_index"] >= 0 and run["start_time"]:
                    start = datetime.fromisoformat(run["start_time"])
                    if datetime.now(timezone.utc) >= start + timedelta(hours=2):
                        await self._advance_run(guild)

                # 2. Season Reset / Week Advancement (Sunday 22:00)
                if day_name == "Sunday" and time_str == "22:00":
                    msg = ""
                    async with self.config.guild(guild).season_data() as s:
                        if s["is_active"]:
                            s["current_week"] += 1
                            if s["current_week"] > 6:
                                s["is_active"] = False
                                msg = f"🏁 **Breaking Army Season Ended** in {guild.name}."
                            else:
                                msg = f"📈 **Breaking Army Advanced to Week {s['current_week']}** in {guild.name}."
                        
                        # Trigger New Season Setup if cycle ended
                        if not s["is_active"] and s.get("current_week", 1) > 6:
                            setup_embed = await self._setup_new_season_logic(guild)
                            if setup_embed:
                                msg = f"🚀 **New Breaking Army Season Started** in {guild.name}!"
                                poll_data = await self.config.guild(guild).active_poll()
                                channel = guild.get_channel(poll_data["channel_id"])
                                if channel: await channel.send(embed=setup_embed)
                    
                    # Pre-populate active_run for the upcoming week
                    season = await self.config.guild(guild).season_data()
                    if season["is_active"]:
                        bosses = self._get_bosses_for_week(season, season["current_week"])
                        await self.config.guild(guild).active_run.set({
                            "boss_order": bosses, "current_index": -1, "is_running": False, "start_time": None
                        })
                        boss_info = await self._get_upcoming_boss_info(guild)
                        msg += f"\nScheduled Bosses: {boss_info}"
                    
                    if msg:
                        await self.bot.send_to_owners(msg)
                    
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
                    win_day = slot[0][0]
                    win_time = slot[0][1]
                    h = int(win_time.split(":")[0])
                    
                    # Stored win_time is UTC+1. In Summer (CEST), 17:00 Local is stored as 16:00 UTC+1.
                    # We only treat 00:00-02:59 as the next calendar day's night.
                    slot_is_next_day = h < 3
                    if slot_is_next_day:
                        if win_day == prev_day_name and time_str == win_time:
                            trigger = True; break
                    else:
                        if win_day == day_name and time_str == win_time:
                            trigger = True; break
                            
                if trigger:
                    last = await self.config.guild(guild).active_run.last_auto_trigger()
                    if last != now.strftime("%Y-%m-%dT%H:%M"):
                        await self.config.guild(guild).active_run.last_auto_trigger.set(now.strftime("%Y-%m-%dT%H:%M"))
                        
                        # Determine which day name triggered it (could be day_name or prev_day_name)
                        trigger_day = prev_day_name if slot_is_next_day else day_name
                        await self._auto_start_run(guild, day_name=trigger_day)
        except Exception as e: log.error(f"Checker error: {e}")

    @schedule_checker.before_loop
    async def before_schedule_checker(self):
        await self.bot.wait_until_red_ready()

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

    async def _get_boss_index_for_day(self, guild: discord.Guild, day_name: str) -> int:
        """Determines which boss index (0 or 1) corresponds to a given day name."""
        polling_cog = self.bot.get_cog("EventPolling")
        if not polling_cog: return 0
        
        polls = await polling_cog.config.guild(guild).polls()
        if not polls: return 0
        
        latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
        poll_data = polls[latest_poll_id]
        winners = poll_data.get("weekly_snapshot_winning_times")
        if not winners:
            winners = polling_cog._calculate_winning_times_weighted(poll_data.get("selections", {}))
            
        ba_winners = winners.get("Breaking Army", {})
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        # Get unique days and sort them chronologically
        win_days = sorted(list(set(s[0][0] for s in ba_winners.values())), key=lambda d: dow_order.index(d))
        
        try:
            return win_days.index(day_name)
        except ValueError:
            return 0

    async def _auto_start_run(self, guild, day_name: Optional[str] = None):
        season = await self.config.guild(guild).season_data()
        notif_channel_id = await self.config.guild(guild).notification_channel()
        channel = guild.get_channel(notif_channel_id) if notif_channel_id else None

        if not season["is_active"]:
            setup_embed = await self._setup_new_season_logic(guild)
            if not setup_embed:
                if channel:
                    await channel.send("⚠️ **Breaking Army:** Run scheduled but no active season/votes found. Please use `[p]ba season setup`!")
                return
            season = await self.config.guild(guild).season_data()
            
        boss_list = self._get_bosses_for_week(season, season["current_week"])
        
        # Determine starting index based on the day
        start_idx = 0
        if day_name:
            start_idx = await self._get_boss_index_for_day(guild, day_name)
            
        now_utc = datetime.now(timezone.utc).isoformat()
        await self.config.guild(guild).active_run.set({
            "boss_order": boss_list, "current_index": start_idx, "is_running": True, "start_time": now_utc
        })
        
        if channel:
            boss_info = await self._get_current_boss_info(guild)
            embed = discord.Embed(
                title="⚔️ Breaking Army Starting!", 
                description=f"Today's Boss: **{boss_info}**\nUse `[p]ba run next` when the boss is down!",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)

        await self._refresh_live_season_view(guild)

    async def _advance_run(self, guild: discord.Guild):
        async with self.config.guild(guild).active_run() as run:
            if not run["is_running"]: return
            run["current_index"] += 1
            if run["current_index"] >= len(run["boss_order"]):
                run["is_running"] = False
                run["start_time"] = None
            else:
                run["start_time"] = datetime.now(timezone.utc).isoformat()
        
        await self._refresh_live_season_view(guild)
        
        # Notify next boss if run is still going
        run = await self.config.guild(guild).active_run()
        if run["is_running"]:
            notif_channel_id = await self.config.guild(guild).notification_channel()
            channel = guild.get_channel(notif_channel_id) if notif_channel_id else None
            if channel:
                boss_info = await self._get_current_boss_info(guild)
                await channel.send(f"⚔️ **Next Boss:** {boss_info}")

    async def _revert_run(self, guild: discord.Guild):
        async with self.config.guild(guild).active_run() as run:
            if run["current_index"] <= -1: return
            
            # If the run was finished (is_running=False but index at the end), restart it
            if not run["is_running"] and run["current_index"] >= len(run["boss_order"]) - 1:
                run["is_running"] = True
            
            run["current_index"] -= 1
            
            # If we went back to before the first boss, the run is no longer "running"
            if run["current_index"] < 0:
                run["is_running"] = False
                run["current_index"] = -1
                run["start_time"] = None
            else:
                # Reset timer for the reverted boss so it doesn't immediately auto-death
                run["start_time"] = datetime.now(timezone.utc).isoformat()

        await self._refresh_live_season_view(guild)
        
        # Notify current boss (the one we went back to)
        run = await self.config.guild(guild).active_run()
        if run["is_running"] and run["current_index"] >= 0:
            notif_channel_id = await self.config.guild(guild).notification_channel()
            channel = guild.get_channel(notif_channel_id) if notif_channel_id else None
            if channel:
                boss_info = await self._get_current_boss_info(guild)
                await channel.send(f"⏪ **Reverted to Boss:** {boss_info}")

    async def _get_upcoming_boss_info(self, guild: discord.Guild, day_name: Optional[str] = None, slot_idx: Optional[int] = None) -> str:
        """Returns boss info for the current week. Chronologically maps bosses to winning days."""
        season = await self.config.guild(guild).season_data()
        if not season["is_active"]: return "No Active Season"
        
        bosses = self._get_bosses_for_week(season, season["current_week"])
        if not bosses: return "No Bosses Scheduled"
        
        boss_pool = await self.config.guild(guild).boss_pool()
        new_emote = await self.config.guild(guild).new_boss_emote()
        priority = season.get("priority_bosses", [])
        
        def format_boss(name):
            emoji = boss_pool.get(name, "⚔️")
            suffix = f" {new_emote}" if name in priority else ""
            return f"{emoji} {name}{suffix}"

        # Determine which boss index to use based on day_name chronological order
        idx = slot_idx
        if day_name:
            polling_cog = self.bot.get_cog("EventPolling")
            if polling_cog:
                polls = await polling_cog.config.guild(guild).polls()
                if polls:
                    latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                    poll_data = polls[latest_poll_id]
                    snap = poll_data.get("weekly_snapshot_winning_times")
                    winners = snap if snap else polling_cog._calculate_winning_times_weighted(poll_data.get("selections", {}))
                    ba_winners = winners.get("Breaking Army", {})
                    
                    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    # Get unique days and sort them chronologically to map to boss indices
                    win_days = sorted(list(set(s[0][0] for s in ba_winners.values())), key=lambda d: dow_order.index(d))
                    
                    if day_name in win_days:
                        idx = win_days.index(day_name)

        if idx is not None and 0 <= idx < len(bosses):
            return format_boss(bosses[idx])
            
        res = [format_boss(b) for b in bosses]
        return " & ".join(res)

    async def _get_current_boss_info(self, guild: discord.Guild) -> str:
        """Returns a formatted string (Emoji Name [New]) for the current active boss."""
        run = await self.config.guild(guild).active_run()
        if not run["is_running"] or run["current_index"] < 0 or run["current_index"] >= len(run["boss_order"]):
            return ""
        
        boss_name = run["boss_order"][run["current_index"]]
        boss_pool = await self.config.guild(guild).boss_pool()
        new_emote = await self.config.guild(guild).new_boss_emote()
        season = await self.config.guild(guild).season_data()
        priority = season.get("priority_bosses", [])
        
        emoji = boss_pool.get(boss_name, "⚔️")
        suffix = f" {new_emote}" if boss_name in priority else ""
        return f"{emoji} {boss_name}{suffix}"

    @commands.group(name="ba")
    @commands.guild_only()
    async def ba(self, ctx: commands.Context):
        """Breaking Army Management"""
        pass

    @ba.error
    async def ba_error_handler(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ **Permission Denied:** You must be a server admin or have a designated BA Admin role to use this command.")
        else:
            # Re-raise other errors to be handled by the bot's global error handler
            raise error

    @ba.command(name="refresh")
    async def ba_refresh(self, ctx: commands.Context):
        """Force update all active embeds (Poll and Season Live View)."""
        if not await self.is_ba_admin(ctx.author):
            return await ctx.send("❌ **Permission Denied.**")

        poll_updated = False
        live_updated = False

        # 1. Update Poll Embed
        poll = await self.config.guild(ctx.guild).active_poll()
        if poll.get("message_id"):
            try:
                await self._update_poll_embed(ctx.guild)
                poll_updated = True
            except:
                pass

        # 2. Update Live Season View
        season = await self.config.guild(ctx.guild).season_data()
        if season.get("live_season_message", {}).get("message_id"):
            try:
                await self._refresh_live_season_view(ctx.guild)
                live_updated = True
            except:
                pass

        status_msg = "✅ **Refresh Results:**\n"
        status_msg += f"- Poll Embed: {'Updated' if poll_updated else 'Not found/failed'}\n"
        status_msg += f"- Live Season View: {'Updated' if live_updated else 'Not found/failed'}"
        
        await ctx.send(status_msg)

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

    @ba_config.command(name="notifchannel")
    async def config_notif_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel for Breaking Army start/advance notifications. Leave empty to disable."""
        if channel:
            await self.config.guild(ctx.guild).notification_channel.set(channel.id)
            await ctx.send(f"✅ Notifications will be sent to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).notification_channel.set(None)
            await ctx.send("✅ Notifications disabled.")

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

        async with self.config.guild(ctx.guild).seen_bosses() as seen:
            if old_name in seen:
                seen[seen.index(old_name)] = new_name

        async with self.config.guild(ctx.guild).active_poll.votes() as votes:
            for uid, ballot in votes.items():
                if not isinstance(ballot, list): continue
                if isinstance(ballot[0], list):
                    votes[uid][0] = [new_name if b == old_name else b for b in ballot[0]]
                elif ballot[0] == old_name:
                    votes[uid][0] = new_name
                if ballot[1] == old_name: votes[uid][1] = new_name
                if isinstance(ballot[2], list):
                    votes[uid][2] = [new_name if b == old_name else b for b in ballot[2]]

        async with self.config.guild(ctx.guild).season_data() as s:
            s["anchors"] = [new_name if b == old_name else b for b in s["anchors"]]
            s["guests"] = [new_name if b == old_name else b for b in s["guests"]]
            s["priority_bosses"] = [new_name if b == old_name else b for b in s["priority_bosses"]]

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
        """Initialize a new 6-week season based on current poll votes.
        
        Requires at least 8 unique bosses to have received votes in the current poll.
        """
        async with ctx.typing():
            poll_data = await self.config.guild(ctx.guild).active_poll()
            votes = poll_data.get("votes", {})
            
            if not votes:
                return await ctx.send("❌ **Setup Failed:** No votes found in the current poll. Use `[p]ba poll start` and have members vote first.")
            
            tally = self._calculate_weighted_tally(votes)
            if len(tally) < 8:
                return await ctx.send(f"❌ **Setup Failed:** Only **{len(tally)}** unique bosses have votes. Need at least **8** to generate a 6-week season.")

            embed = await self._setup_new_season_logic(ctx.guild)
            if embed: 
                await ctx.send(embed=embed)
                season = await self.config.guild(ctx.guild).season_data()
                bosses = self._get_bosses_for_week(season, season["current_week"])
                await self.config.guild(ctx.guild).active_run.set({
                    "boss_order": bosses, "current_index": -1, "is_running": False, "start_time": None
                })
                await self._refresh_live_season_view(ctx.guild)
                await ctx.send("✅ **Success:** Season 1 initialized and Week 1 schedule set.")
            else: 
                await ctx.send("❌ **Setup Failed:** An internal error occurred while generating the season matrix.")

    @ba_season.command(name="setweek")
    async def season_set_week(self, ctx: commands.Context, week: int):
        if not (1 <= week <= 6): return await ctx.send("Week must be between 1 and 6.")
        async with self.config.guild(ctx.guild).season_data() as s:
            s["current_week"] = week; s["is_active"] = True
        
        season = await self.config.guild(ctx.guild).season_data()
        bosses = self._get_bosses_for_week(season, week)
        await self.config.guild(ctx.guild).active_run.set({
            "boss_order": bosses, "current_index": -1, "is_running": False, "start_time": None
        })
        
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

    @ba_season.command(name="overwrite")
    async def season_overwrite(self, ctx: commands.Context, message_id: str):
        """Overwrite an existing bot message with the Season Live View.
        
        This allows you to turn any existing bot message into the persistent season tracker.
        
        Example: [p]ba season overwrite 123456789
        Or: [p]ba season overwrite https://discord.com/channels/...
        """
        parsed = self._parse_message_id(message_id)
        if parsed is None:
            return await ctx.send("❌ **Error:** Invalid message ID or link.")

        target_message = None
        channel_id = None
        msg_id = None

        if isinstance(parsed, tuple):
            channel_id, msg_id = parsed
        else:
            msg_id = parsed

        # Strategy 1: Use channel ID from link if available
        if channel_id:
            try:
                channel = ctx.guild.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                target_message = await channel.fetch_message(msg_id)
            except:
                pass

        # Strategy 2: Check current channel
        if not target_message:
            try:
                target_message = await ctx.channel.fetch_message(msg_id)
            except:
                pass

        # Strategy 3: Check tracked channel
        if not target_message:
            season_data = await self.config.guild(ctx.guild).season_data()
            live = season_data.get("live_season_message", {})
            if live.get("channel_id"):
                try:
                    channel = ctx.guild.get_channel(live["channel_id"]) or await self.bot.fetch_channel(live["channel_id"])
                    target_message = await channel.fetch_message(msg_id)
                except:
                    pass

        # Strategy 4: Search all text channels (last resort)
        if not target_message:
            await ctx.send("🔍 Searching for message in other channels...")
            for channel in ctx.guild.text_channels:
                if channel.id == ctx.channel.id: continue # Already checked
                try:
                    target_message = await channel.fetch_message(msg_id)
                    if target_message: break
                except:
                    continue

        if not target_message:
            return await ctx.send("❌ **Error:** Could not find the specified message. If using an ID, please run the command in the same channel as the message, or use a full Message Link.")

        if target_message.author.id != self.bot.user.id:
            return await ctx.send("❌ **Error:** I can only overwrite messages sent by me.")

        # Generate content
        embeds = await self._generate_season_status_embeds(ctx.guild)
        poll_data = await self.config.guild(ctx.guild).active_poll()
        view = None
        if poll_data.get("message_id"):
            url = f"https://discord.com/channels/{ctx.guild.id}/{poll_data['channel_id']}/{poll_data['message_id']}"
            view = SeasonLiveView(url)

        try:
            await target_message.edit(embeds=embeds, view=view)
            async with self.config.guild(ctx.guild).season_data() as s:
                s["live_season_message"] = {"message_id": target_message.id, "channel_id": target_message.channel.id}
            await ctx.send(f"✅ **Success:** Message {target_message.id} in {target_message.channel.mention} is now tracking the season.")
        except Exception as e:
            await ctx.send(f"❌ **Error:** Failed to edit message: {e}")

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

    @ba_run.command(name="back", aliases=["undo", "prev"])
    async def run_back(self, ctx: commands.Context):
        """Mark the last defeated boss as undefeated (go back 1 boss)."""
        if not await self.is_ba_admin(ctx.author):
            return await ctx.send("Permission denied.")
        
        run = await self.config.guild(ctx.guild).active_run()
        if run["current_index"] <= -1:
            return await ctx.send("❌ **Error:** No progress to revert.")
        
        await self._revert_run(ctx.guild)
        await ctx.tick()

    @ba_run.command(name="setindex")
    async def run_set_index(self, ctx: commands.Context, index: int):
        """Manually set the current boss index for the active run."""
        async with self.config.guild(ctx.guild).active_run() as run:
            if not run["is_running"]:
                return await ctx.send("❌ **Error:** No run is currently active.")
            
            if index < -1 or index >= len(run["boss_order"]):
                return await ctx.send(f"❌ **Error:** Index must be between -1 and {len(run['boss_order']) - 1}.")
            
            run["current_index"] = index
        
        await self._refresh_live_season_view(ctx.guild)
        await ctx.send(f"✅ **Success:** Current boss index set to {index}.")

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

    @ba_poll.command(name="cleanup")
    async def poll_cleanup(self, ctx: commands.Context):
        """Remove votes from users who left or lost their member roles."""
        # Specific role IDs: @Member and @Friend of the Guild
        target_role_ids = {1439747785644703754, 1452430729115078850}
        
        removed_count = 0
        async with self.config.guild(ctx.guild).active_poll.votes() as votes:
            user_ids = list(votes.keys())
            for user_id_str in user_ids:
                user_id = int(user_id_str)
                member = ctx.guild.get_member(user_id)
                
                should_remove = False
                reason = ""
                
                if not member:
                    should_remove = True
                    reason = "left the server"
                else:
                    has_role = any(role.id in target_role_ids for role in member.roles)
                    if not has_role:
                        should_remove = True
                        reason = "lost member roles"
                
                if should_remove:
                    del votes[user_id_str]
                    removed_count += 1
                    log.info(f"Cleanup: Removed Breaking Army votes for user {user_id} because they {reason}.")
        
        if removed_count > 0:
            await self._update_poll_embed(ctx.guild)
            await ctx.send(f"✅ Cleanup complete. Removed votes from **{removed_count}** user(s) who are no longer eligible.")
        else:
            await ctx.send("✅ Cleanup complete. No ineligible voters found.")

    async def _start_run_display(self, ctx, boss_list):
        embed = await self._generate_run_embed(ctx.guild, boss_list, -1, False)
        msg = await ctx.send(embed=embed)

    async def _generate_run_embed(self, guild, boss_list, current_index, is_running):
        pool = await self.config.guild(guild).boss_pool(); desc = ""
        new_emote = await self.config.guild(guild).new_boss_emote()
        season = await self.config.guild(guild).season_data()
        priority = season.get("priority_bosses", [])
        
        days = []
        polling_cog = self.bot.get_cog("EventPolling")
        if polling_cog:
            polls = await polling_cog.config.guild(guild).polls()
            if polls:
                latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                poll_data = polls[latest_poll_id]
                snap = poll_data.get("weekly_snapshot_winning_times")
                winners = snap if snap else polling_cog._calculate_winning_times_weighted(poll_data.get("selections", {}))
                ba_winners = winners.get("Breaking Army", {})
                dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                raw_days = list(set(slot[0][0] for slot in ba_winners.values()))
                raw_days.sort(key=lambda d: dow_order.index(d))
                days = [d[:3] for d in raw_days]

        for i, b in enumerate(boss_list):
            e = pool.get(b, "⚔️")
            suffix = f" {new_emote}" if b in priority else ""
            day_text = days[i] if i < len(days) else "???"
            day_code = f"`{day_text}` "
            
            if i < current_index:
                desc += f"{day_code}💀 ~~{e} {b}{suffix}~~\n"
            elif i == current_index and is_running:
                desc += f"{day_code}⚔️ **__{e} {b}{suffix}__**\n"
            else:
                desc += f"{day_code}⏳ {e} {b}{suffix}\n"
        
        return discord.Embed(description=desc, color=discord.Color.green())

    def _parse_message_id(self, message_input: Union[str, int]) -> Union[int, Tuple[int, int], None]:
        """Parse message ID from either an integer or a Discord message link.
        
        Returns:
            - int: Just the message ID if a raw integer was provided
            - Tuple[int, int]: (channel_id, message_id) if a link was provided
            - None: if parsing failed
        """
        if isinstance(message_input, int):
            return message_input
        if isinstance(message_input, str):
            # Try direct integer
            try:
                return int(message_input)
            except ValueError:
                pass
            
            # Try Discord link format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
            match = re.search(r'discord\.com/channels/\d+/(\d+)/(\d+)', message_input)
            if match:
                return int(match.group(1)), int(match.group(2))
        return None

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
        actual_cog = interaction.client.get_cog("BreakingArmy") or self.cog
        choices = [self.anchor.values if self.anchor.values else [], self.encore.values[0] if self.encore.values else None, self.guests.values if self.guests.values else []]
        async with actual_cog.config.guild(interaction.guild).active_poll() as p: p["votes"][str(interaction.user.id)] = choices
        await actual_cog._update_poll_embed(interaction.guild); await interaction.followup.send("Ballot Saved!", ephemeral=True)

class BossPollView(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog
    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="ba_vote")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        actual_cog = interaction.client.get_cog("BreakingArmy") or self.cog
        pool = await actual_cog.config.guild(interaction.guild).boss_pool()
        poll_data = await actual_cog.config.guild(interaction.guild).active_poll()
        cur_votes = poll_data.get("votes", {}).get(str(interaction.user.id), [])
        await interaction.response.send_modal(BossVoteModal(actual_cog, interaction.guild, interaction.user.id, pool, cur_votes))
    @discord.ui.button(label="Total Results", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="ba_results")
    async def results(self, interaction: discord.Interaction, button: discord.ui.Button):
        actual_cog = interaction.client.get_cog("BreakingArmy") or self.cog
        poll = await actual_cog.config.guild(interaction.guild).active_poll()
        boss_pool = await actual_cog.config.guild(interaction.guild).boss_pool()
        new_emote = await actual_cog.config.guild(interaction.guild).new_boss_emote()
        seen_bosses = await actual_cog.config.guild(interaction.guild).seen_bosses()
        tally = actual_cog._calculate_weighted_tally(poll.get("votes", {}))
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