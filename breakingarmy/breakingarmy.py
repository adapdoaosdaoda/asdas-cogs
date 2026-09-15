import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
import asyncio
import logging
import pytz
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Union, Any, Tuple

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
            "log_channel_id": None,
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
                "weeks": 4,  # Active season's natural length (4, or 5 for a "special" season)
                "max_week": 4,  # Normally == weeks; a mid-month fallback season is capped lower (1-3) so it ends before the next queued slot
                "roster": [],  # Flat list of 6 bosses for a normal 4-week season: W1=roster[0:2], W2=roster[2:4], W3=roster[4:6], W4=encore of W1
                "special_anchors": [],  # 3 anchors, only populated for a 5-week "special" season
                "special_guests": [],  # 4 guests, only populated for a 5-week "special" season
                "priority_bosses": [], # Bosses that get the 'new' emote this season
                "is_active": False,
                "live_season_message": {},
                "last_reset": None,  # ISO format timestamp of last reset
                "season_queue": [],  # Pre-generated future season windows: [{"start": iso, "end": iso, "weeks": 4|5}, ...]
            }
        }
        
        self.config.register_guild(**default_guild)
        self.schedule_checker.start()

    async def cog_load(self):
        """Called when the cog is loaded"""
        self.bot.add_view(BossPollView(self))

    def cog_unload(self):
        self.schedule_checker.cancel()

    async def _send_log(self, guild: discord.Guild, msg: str):
        """Send a bot-status message to the owners (DM) and the configured log channel, if any."""
        await self.bot.send_to_owners(msg)
        log_channel_id = await self.config.guild(guild).log_channel_id()
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if channel:
                try:
                    await channel.send(msg)
                except discord.HTTPException:
                    log.warning(f"Failed to send log message to configured log channel in {guild.name}")

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

    def _compute_season_assignment(
        self, new_p: List[str], old_p: List[str], boss_pool: Dict[str, str], seen_bosses: List[str]
    ) -> Tuple[List[Optional[str]], List[str], Dict[str, str]]:
        """Pure assignment logic shared by season setup and poll previews.

        Returns (roster[6], used_in_order, slot_of[boss_name]).
        `new_p`/`old_p` are consumed as copies - callers' lists are untouched.
        """
        new_p = list(new_p); old_p = list(old_p)
        ranked = new_p + old_p

        r: List[Optional[str]] = [None] * 6
        used: List[str] = []

        # 1. Fill roster slots in unlock order (N1..N6)
        for i in range(6):
            if new_p:
                b = new_p.pop(0)
                r[i] = b
                used.append(b)

        # 2. Fill remaining empty slots from the ranked list
        rem = [b for b in ranked if b not in used]
        for i in range(6):
            if r[i] is None:
                boss = rem.pop(0)
                r[i] = boss
                used.append(boss)

        slot_of: Dict[str, str] = {}
        for i, boss in enumerate(r):
            if boss: slot_of[boss] = f"Week {i // 2 + 1}"

        return r, used, slot_of

    def _compute_special_season_assignment(
        self, new_p: List[str], old_p: List[str], boss_pool: Dict[str, str], seen_bosses: List[str]
    ) -> Tuple[List[Optional[str]], List[Optional[str]], List[str], Dict[str, str]]:
        """Assignment logic for a "special" 5-week season: 3 anchors + 4 guests (7
        unique bosses). Pairing (built by `_get_bosses_for_week`): W1=(a0,g0),
        W2=(a1,g1), W3=(a2,g2), W4=(a1,a0) encore, W5=(a2,g3).

        Returns (anchors[3], guests[4], used_in_order, slot_of[boss_name]).
        `new_p`/`old_p` are consumed as copies - callers' lists are untouched.
        """
        new_p = list(new_p); old_p = list(old_p)
        ranked = new_p + old_p

        a: List[Optional[str]] = [None] * 3
        g: List[Optional[str]] = [None] * 4
        used: List[str] = []

        # Fill in unlock order: a0,g0,a1,g1,a2,g2,g3 (7 unique bosses)
        slots: List[Tuple[str, int]] = [("a", 0), ("g", 0), ("a", 1), ("g", 1), ("a", 2), ("g", 2), ("g", 3)]
        for kind, idx in slots:
            if new_p:
                b = new_p.pop(0)
                used.append(b)
                if kind == "a": a[idx] = b
                else: g[idx] = b

        rem = [b for b in ranked if b not in used]
        for kind, idx in slots:
            target = a if kind == "a" else g
            if target[idx] is None:
                boss = rem.pop(0)
                used.append(boss)
                target[idx] = boss

        slot_of: Dict[str, str] = {}
        week_of_slot = {("a", 0): 1, ("g", 0): 1, ("a", 1): 2, ("g", 1): 2, ("a", 2): 3, ("g", 2): 3, ("g", 3): 5}
        for kind, idx in slots:
            boss = (a if kind == "a" else g)[idx]
            if boss: slot_of[boss] = f"Week {week_of_slot[(kind, idx)]}"

        return a, g, used, slot_of

    @staticmethod
    def _next_sunday_2200_on_or_after(dt: datetime) -> datetime:
        """The nearest Sunday 22:00 (server time) at or after `dt`."""
        days_ahead = (6 - dt.weekday()) % 7  # 6 = Sunday
        candidate = dt.replace(hour=22, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        if candidate < dt:
            candidate += timedelta(days=7)
        return candidate

    @staticmethod
    def _nearest_month_start_sunday(first_of_month: datetime) -> datetime:
        """The Sunday 22:00 (server time) closest to `first_of_month` (which must be
        the 1st of a month at midnight): on the 1st itself if it's a Sunday, the day
        BEFORE if it's a Monday (so the season can start no more than a day early),
        otherwise the next Sunday on/after the 1st (same as the general rule).
        """
        wd = first_of_month.weekday()  # Mon=0 ... Sun=6
        if wd == 6:
            return first_of_month.replace(hour=22, minute=0, second=0, microsecond=0)
        elif wd == 0:
            return (first_of_month - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
        return BreakingArmy._next_sunday_2200_on_or_after(first_of_month)

    @classmethod
    def _weeks_available_before(cls, now: datetime, deadline: datetime) -> int:
        """How many `current_week` values (1, 2, 3...) a season starting at `now` can
        reach before `deadline` (typically the next queued month-aligned slot). Week 1
        always counts as available (it's "now" until the first Sunday 22:00 rollover),
        even if `now` is mid-week - each subsequent week needs a full rollover-to-rollover
        span that still ends at or before `deadline`.
        """
        if now >= deadline:
            return 0
        rollover = cls._next_sunday_2200_on_or_after(now)
        weeks = 1
        while True:
            next_rollover = rollover + timedelta(days=7)
            if rollover >= deadline or next_rollover > deadline:
                break
            weeks += 1
            rollover = next_rollover
        return weeks

    def _generate_season_queue(self, from_date: datetime, existing_queue: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Builds/extends a queue of {"start", "end", "weeks"} season windows, one per
        remaining calendar month in `from_date`'s year (plus January of next year, so
        December's entry has a real "end"/"weeks"), each starting at the Sunday 22:00
        nearest that month's 1st (see `_nearest_month_start_sunday`) and running until
        the NEXT month's start boundary - so there's never a dead gap between seasons.
        That gap is 4 or 5 weeks depending on the calendar, giving an occasional
        "special" 5-week season.
        Existing entries are kept, but self-heal: an entry whose "start" matches but is
        missing/wrong on "end" or "weeks" (e.g. queued by an older version of this
        function, before variable-length seasons existed) gets those fields recomputed
        and overwritten in-place - so stale queues quietly repair themselves the next
        time this runs, without needing a manual wipe. Months already started (start <=
        from_date, e.g. a season just activated from this month's slot) are skipped -
        this makes the function idempotent/safe to call at any point.
        """
        server_tz = from_date.tzinfo
        by_start = {entry["start"]: entry for entry in existing_queue}
        year = from_date.year

        def month_start(y, m):
            return datetime(y, m, 1, tzinfo=server_tz)

        for month in range(from_date.month, 13):
            this_start = self._nearest_month_start_sunday(month_start(year, month))
            next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
            next_start = self._nearest_month_start_sunday(month_start(next_year, next_month))
            weeks = (next_start - this_start).days // 7

            if this_start <= from_date:
                continue
            start_iso = this_start.isoformat()
            existing = by_start.get(start_iso)
            if existing is None:
                by_start[start_iso] = {"start": start_iso, "end": next_start.isoformat(), "weeks": weeks}
            elif existing.get("end") != next_start.isoformat() or existing.get("weeks") != weeks:
                existing["end"] = next_start.isoformat()
                existing["weeks"] = weeks

        queue = list(by_start.values())
        queue.sort(key=lambda e: e["start"])
        return queue

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
        
        # New Ranking Logic: All new bosses first, then old
        new_p = sorted([b for b in boss_pool if b not in seen_bosses], key=lambda x: tally.get(x, 0), reverse=True)
        old_p = sorted([b for b in boss_pool if b in seen_bosses], key=lambda x: tally.get(x, 0), reverse=True)

        embed = discord.Embed(title="⚔️ Breaking Army: Boss Poll", color=discord.Color.gold())
        embed.description = "Vote for your favorite bosses to determine the next 4-week season roster!"
        sample = (
            "**Week 1**: Boss 1 & Boss 2\n"
            "**Week 2**: Boss 3 & Boss 4\n"
            "**Week 3**: Boss 5 & Boss 6\n"
            "**Week 4**: Boss 1 & Boss 2 (Encore)"
        )
        embed.add_field(name="📋 Season Structure (Rotation)", value=sample, inline=False)

        if len(new_p) + len(old_p) < 6:
            leaders = f"⚠️ *Not enough bosses in pool to form a season ({len(new_p) + len(old_p)}/6)*"
        else:
            _, used, slot_of = self._compute_season_assignment(new_p, old_p, boss_pool, seen_bosses)

            def fmt(name):
                emote = boss_pool.get(name, '⚔️')
                suffix = f" {new_emote}" if name not in seen_bosses else ""
                return f"{emote} {name}{suffix}"

            lines = [f"{i + 1}. {fmt(name)} ({slot_of.get(name, '?')})" for i, name in enumerate(used)]
            leaders = "\n".join(lines)
        embed.add_field(name="📊 Current Priority Order", value=leaders, inline=False)
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
        
        weeks = season.get("weeks", 4)
        is_special = weeks == 5
        color = discord.Color.green() if season["is_active"] else discord.Color.purple()
        title = "✨ Breaking Army Season Status (Special)" if is_special and season["is_active"] else "📅 Breaking Army Season Status"
        sched_embed = discord.Embed(title=title, color=color)

        has_roster = bool(season.get("roster")) if not is_special else (len(season.get("special_anchors", [])) >= 3 and len(season.get("special_guests", [])) >= 4)
        if not has_roster:
            sched_embed.description = "No season initialized."
        else:
            def get_fmt_name(n):
                e = boss_pool.get(n, "⚔️")
                suffix = f" {new_emote}" if n in priority else ""
                return f"{e} {n}{suffix}"

            max_week = season.get("max_week", weeks)
            sched = ""
            for w in range(1, weeks + 1):
                b1, b2 = self._get_bosses_for_week(season, w)
                n1 = get_fmt_name(b1)
                n2 = get_fmt_name(b2)

                if w > max_week:
                    # Fallback season - this week is beyond max_week and will never run.
                    sched += f"🚫 ~~**Week {w}**: {n1} & {n2}~~\n-# (skipped - season ends after Week {max_week})\n\n"
                elif w < season["current_week"]:
                    sched += f"💀 ~~**Week {w}**: {n1} & {n2}~~\n"
                elif w == season["current_week"] and season["is_active"]:
                    if run["is_running"]:
                        sched += f"⚔️ **Week {w}**: {n1} & {n2} (Active)\n"
                    else:
                        sched += f"⏳ **Week {w}**: {n1} & {n2}\n"
                else:
                    sched += f"⏳ **Week {w}**: {n1} & {n2}\n"
            sched_embed.description = sched

        queue = season.get("season_queue", [])
        if queue:
            upcoming = "\n".join(
                f"🗓️ {datetime.fromisoformat(entry['start']).strftime('%b %d, %Y')}{' ✨special' if entry.get('weeks') == 5 else ''}"
                for entry in queue[:3]
            )
            sched_embed.add_field(name="📆 Upcoming Seasons", value=upcoming, inline=False)

        embeds = [sched_embed]
        # Always show run dashboard if season is active
        if season["is_active"] and (run["boss_order"] or run["is_running"]):
            run_embed = await self._generate_run_embed(guild, run["boss_order"], run["current_index"], run["is_running"])
            run_embed.title = f"🔥 Week {season['current_week']}"
            embeds.append(run_embed)
        return embeds

    def _get_bosses_for_week(self, season: Dict, week: int) -> List[str]:
        if season.get("weeks", 4) == 5:
            a = season.get("special_anchors", [])
            g = season.get("special_guests", [])
            if len(a) < 3 or len(g) < 4: return []
            matrix = [(a[0], g[0]), (a[1], g[1]), (a[2], g[2]), (a[1], a[0]), (a[2], g[3])]
            if 1 <= week <= 5:
                return list(matrix[week-1])
            return []

        r = season.get("roster", [])
        if len(r) < 6: return []
        matrix = [(r[0], r[1]), (r[2], r[3]), (r[4], r[5]), (r[0], r[1])]
        if 1 <= week <= 4:
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
                # We use a 1-hour window for the "active" check, but catch-up handles downtime.
                # Target: Sunday 22:00 Server Time (UTC+1)
                days_back = (now.weekday() - 6) % 7 # 6 = Sunday
                target_reset = now.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(days=days_back)
                if target_reset > now:
                    target_reset -= timedelta(days=7)

                last_reset_str = (await self.config.guild(guild).season_data())["last_reset"]
                should_reset = False
                if not last_reset_str:
                    # Initialize last_reset if it doesn't exist, but only trigger if it's currently Sunday 22:00
                    if day_name == "Sunday" and time_str == "22:00":
                        should_reset = True
                    else:
                        async with self.config.guild(guild).season_data() as s:
                            s["last_reset"] = target_reset.isoformat()
                else:
                    last_reset = datetime.fromisoformat(last_reset_str)
                    if last_reset < target_reset:
                        should_reset = True

                if should_reset:
                    msg = ""
                    is_active = False
                    async with self.config.guild(guild).season_data() as s:
                        # Catch up on every Sunday 22:00 boundary missed since last_reset
                        # (e.g. the bot was offline across 2+ rollovers) instead of only
                        # advancing current_week by 1 - otherwise the week count desyncs
                        # from real elapsed weeks and a missed advance is never logged.
                        missed_reset = datetime.fromisoformat(last_reset_str) if last_reset_str else target_reset
                        weeks_advanced = 0
                        season_ended = False
                        r = missed_reset
                        while r < target_reset:
                            r += timedelta(days=7)
                            if not s["is_active"]:
                                break
                            s["current_week"] += 1
                            weeks_advanced += 1
                            if s["current_week"] > s.get("max_week", 4):
                                s["is_active"] = False
                                season_ended = True
                                break
                        s["last_reset"] = target_reset.isoformat()

                        if season_ended:
                            msg = f"🏁 **Breaking Army Season Ended** in {guild.name}."
                        elif weeks_advanced == 1:
                            msg = f"📈 **Breaking Army Advanced to Week {s['current_week']}** in {guild.name}."
                        elif weeks_advanced > 1:
                            msg = f"📈 **Breaking Army Advanced to Week {s['current_week']}** in {guild.name} *(caught up {weeks_advanced} missed weeks)*."
                        is_active = s["is_active"]

                        # Keep the year's schedule populated (covers first-ever setup too).
                        if not s.get("season_queue"):
                            s["season_queue"] = self._generate_season_queue(now, [])

                    if not is_active:
                        # Only activate the next season once its pre-generated,
                        # month-aligned start date has actually arrived - never
                        # chain immediately after the previous season ends. Peek
                        # (don't pop) so a failed setup (e.g. not enough bosses for
                        # a special 5-week season) leaves the slot queued for retry
                        # instead of silently discarding that month's season.
                        season_data = await self.config.guild(guild).season_data()
                        queue = season_data.get("season_queue", [])
                        due_weeks = queue[0]["weeks"] if queue and datetime.fromisoformat(queue[0]["start"]) <= now else None

                        if due_weeks:
                            setup_embed = await self._setup_new_season_logic(guild, weeks=due_weeks, max_week=due_weeks)
                            if setup_embed:
                                await self._consume_due_season_slot(guild)
                                special_tag = "✨ Special (5-Week) " if due_weeks == 5 else ""
                                msg = f"🚀 **New {special_tag}Breaking Army Season Started** in {guild.name}!"
                                poll_data = await self.config.guild(guild).active_poll()
                                channel = guild.get_channel(poll_data["channel_id"])
                                if channel: await channel.send(embed=setup_embed)
                            else:
                                min_pool = 7 if due_weeks == 5 else 6
                                msg += f"\n⚠️ A season was due to start but failed - need at least **{min_pool}** bosses in the pool. It will retry next tick."

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
                        await self._send_log(guild, msg)
                    
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

    async def _setup_new_season_logic(self, guild: discord.Guild, weeks: int = 4, max_week: Optional[int] = None) -> Optional[discord.Embed]:
        """Computes a season roster from current poll votes and activates it now.

        `weeks` is the season's natural length (4 for a normal season, 5 for a
        "special" season using the 3-anchor/4-guest model). `max_week` caps how many
        weeks this season actually runs before schedule_checker ends it - defaults to
        `weeks`, but a mid-month fallback season (started via the "nothing due yet,
        start now" path) passes a lower cap (1-3) so it ends before the next queued
        month-aligned slot is due. Fallback seasons always use the 4-week model
        regardless of the upcoming slot's natural length.

        Always ensures the year's season_queue is populated/extended as a side effect,
        which is how the "pre-generate the rest of the year's schedule" feature is surfaced.
        """
        if max_week is None:
            max_week = weeks

        poll_data = await self.config.guild(guild).active_poll()
        boss_pool = await self.config.guild(guild).boss_pool()
        seen_bosses = await self.config.guild(guild).seen_bosses()
        new_emote = await self.config.guild(guild).new_boss_emote()

        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))

        min_pool = 7 if weeks == 5 else 6
        if len(boss_pool) < min_pool: return None

        # Split pool into new and old groups, ranked by votes. Bosses with no
        # votes sort together at the back of their group in random order, so a
        # season can still be formed (and stays varied) even with partial or
        # no voter turnout.
        def _ranked(names: List[str]) -> List[str]:
            voted = [b for b in names if tally.get(b, 0) > 0]
            unvoted = [b for b in names if tally.get(b, 0) <= 0]
            random.shuffle(unvoted)
            voted.sort(key=lambda x: tally.get(x, 0), reverse=True)
            return voted + unvoted

        new_p = _ranked([b for b in boss_pool if b not in seen_bosses])
        old_p = _ranked([b for b in boss_pool if b in seen_bosses])

        if weeks == 5:
            anchors, guests, used, _ = self._compute_special_season_assignment(new_p, old_p, boss_pool, seen_bosses)
            roster = []
        else:
            roster, used, _ = self._compute_season_assignment(new_p, old_p, boss_pool, seen_bosses)
            anchors, guests = [], []
        priority_bosses = [b for b in used if b not in seen_bosses]

        server_tz = timezone(timedelta(hours=1))
        now = datetime.now(server_tz)
        target_reset = self._next_sunday_2200_on_or_after(now) - timedelta(days=7)

        async with self.config.guild(guild).season_data() as s:
            s["weeks"] = weeks
            s["roster"] = roster
            s["special_anchors"] = anchors
            s["special_guests"] = guests
            s["is_active"] = True
            s["priority_bosses"] = priority_bosses
            s["current_week"] = 1
            s["max_week"] = max_week
            s["last_reset"] = target_reset.isoformat()
            s["season_queue"] = self._generate_season_queue(now, s.get("season_queue", []))

        async with self.config.guild(guild).seen_bosses() as seen:
            for b in used:
                if b not in seen: seen.append(b)

        # Wipe the poll so each new season starts with a clean vote - stops
        # stale votes (including from members who've since left) carrying
        # over, and keeps the roster relevant to whoever wants to vote now.
        await self.config.guild(guild).active_poll.votes.set({})
        await self._update_poll_embed(guild)

        season_shape = {"weeks": weeks, "roster": roster, "special_anchors": anchors, "special_guests": guests}

        # Notify the boss-change channel that a new season's bosses are live - this is
        # the same channel/style _advance_run uses for regular "Next Boss" pings, so
        # players watching for boss changes see season starts too (including fallback
        # seasons, which can start well after the usual weekly schedule tick).
        notif_channel_id = await self.config.guild(guild).notification_channel()
        notif_channel = guild.get_channel(notif_channel_id) if notif_channel_id else None
        if notif_channel:
            week1_bosses = self._get_bosses_for_week(season_shape, 1)
            week1_info = " & ".join(
                f"{boss_pool.get(b, '⚔️')} {b}" + (f" {new_emote}" if b in priority_bosses else "")
                for b in week1_bosses
            )
            special_tag = "✨ **Special Season!** " if weeks == 5 else ""
            try:
                await notif_channel.send(f"🚀 **New Breaking Army Season!** {special_tag}Week 1 Boss: {week1_info}")
            except discord.HTTPException:
                log.warning(f"Failed to send season-start boss-change notice in {guild.name}")

        if weeks == 5:
            title = "✨ New Special Season Initialized (5 Weeks)"
        elif max_week >= weeks:
            title = "🚀 New Season Initialized"
        else:
            title = f"🚀 New Season Initialized ({max_week} Week{'s' if max_week != 1 else ''})"
        embed = discord.Embed(title=title, color=discord.Color.green())
        def fmt(name): return f"{boss_pool.get(name, '⚔️')} **{name}**" + (f" {new_emote}" if name in priority_bosses else "")
        if weeks == 5:
            embed.add_field(name="Anchors", value="\n".join([f"{i+1}. {fmt(x)}" for i, x in enumerate(anchors)]), inline=True)
            embed.add_field(name="Guests", value="\n".join([f"{i+1}. {fmt(x)}" for i, x in enumerate(guests)]), inline=True)
        else:
            embed.add_field(name="Season Roster", value="\n".join([f"{i+1}. {fmt(x)}" for i, x in enumerate(roster)]), inline=False)
        if max_week < weeks:
            embed.description = f"Started mid-month - this season runs Week 1-{max_week} only, then the next month's season begins on schedule."
        return embed

    async def _resolve_season_activation(self, guild: discord.Guild) -> Tuple[str, Optional[int], Optional[int]]:
        """Decides what should happen right now if no season is active, ensuring/
        extending season_queue as a side effect. Shared by `season setup` and
        `_auto_start_run` so a boss-run auto-trigger during an off-season gap goes
        through the same due/fallback/nothing-available logic instead of blindly
        starting an uncapped season that could collide with a later queued slot.

        Only PEEKS at season_queue - never pops. Callers must call
        `_consume_due_season_slot` themselves, and only after `_setup_new_season_logic`
        has actually succeeded, so a failed setup (e.g. not enough bosses for a
        special 5-week season) leaves the queue entry intact for a later retry
        instead of silently discarding that month's slot.

        Returns (status, weeks, max_week):
        - ("active", None, None): a season is already active, nothing to do.
        - ("due", weeks, weeks): the next queued slot's start has arrived - activate
          a normal (uncapped) season of that length, then consume the slot on success.
        - ("fallback", 4, max_week): nothing is due yet, but a capped 1-3 week
          fallback season (always the plain 4-week model) can start now. Fallback
          seasons don't consume a queue slot - they run alongside the still-queued
          upcoming one.
        - ("none", None, None): nothing is due and no fallback fits (e.g. the queue
          is empty, or we're right at a month boundary with no room left).
        """
        season = await self.config.guild(guild).season_data()
        server_tz = timezone(timedelta(hours=1))
        now = datetime.now(server_tz)

        async with self.config.guild(guild).season_data() as s:
            s["season_queue"] = self._generate_season_queue(now, s.get("season_queue", []))
            queue = s["season_queue"]

        if season["is_active"]:
            return ("active", None, None)

        if queue and datetime.fromisoformat(queue[0]["start"]) <= now:
            return ("due", queue[0]["weeks"], queue[0]["weeks"])

        if not queue:
            return ("none", None, None)

        next_slot_start = datetime.fromisoformat(queue[0]["start"])
        max_week = min(3, self._weeks_available_before(now, next_slot_start))
        if max_week < 1:
            return ("none", None, None)
        return ("fallback", 4, max_week)

    async def _consume_due_season_slot(self, guild: discord.Guild):
        """Pops the front of season_queue - call only after a "due" season has
        actually been successfully activated by `_setup_new_season_logic`."""
        async with self.config.guild(guild).season_data() as s:
            if s.get("season_queue"):
                s["season_queue"] = s["season_queue"][1:]

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
            status, weeks, max_week = await self._resolve_season_activation(guild)
            if status in ("active", "none"):
                # "active" shouldn't happen here (we just checked is_active above),
                # but treat it the same as "nothing to activate" defensively.
                if channel:
                    await channel.send("⚠️ **Breaking Army:** Run scheduled but no active season/votes found. Please use `[p]ba season setup`!")
                return

            setup_embed = await self._setup_new_season_logic(guild, weeks=weeks, max_week=max_week)
            if not setup_embed:
                if channel:
                    await channel.send("⚠️ **Breaking Army:** Run scheduled but no active season/votes found. Please use `[p]ba season setup`!")
                return
            if status == "due":
                await self._consume_due_season_slot(guild)
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

    BA_ROLE_IDS = (1439747785644703754, 1452430729115078850)

    def _has_ba_role(self, member: discord.Member) -> bool:
        return any(r.id in self.BA_ROLE_IDS for r in getattr(member, "roles", []))

    @commands.hybrid_group(name="breakingarmy", invoke_without_command=True, fallback="vote")
    @commands.guild_only()
    async def breakingarmy(self, ctx: commands.Context):
        """Privately view (and vote on) the Breaking Army boss poll."""
        if ctx.invoked_subcommand is not None:
            return
        if not self._has_ba_role(ctx.author):
            await ctx.send("❌ You do not have permission to use this command.", ephemeral=True)
            return

        embed = await self._generate_poll_embed(ctx.guild)
        view = BossPollView(self)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @breakingarmy.command(name="show")
    async def breakingarmy_show(self, ctx: commands.Context):
        """Privately view the active Breaking Army season status."""
        if not self._has_ba_role(ctx.author):
            await ctx.send("❌ You do not have permission to use this command.", ephemeral=True)
            return

        embeds = await self._generate_season_status_embeds(ctx.guild)
        await ctx.send(embeds=embeds, ephemeral=True)

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

    @ba_config.command(name="logchannel")
    async def config_log_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel that receives owner-status log messages (week advances, schedule/trade commission updates). Leave empty to disable."""
        if channel:
            await self.config.guild(ctx.guild).log_channel_id.set(channel.id)
            await ctx.send(f"✅ Log messages will also be sent to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).log_channel_id.set(None)
            await ctx.send("✅ Log channel disabled. Messages will only be sent to the bot owner(s).")

    @ba_config.command(name="addboss")
    async def config_add_boss(self, ctx: commands.Context, emoji: Optional[str] = "⚔️", *, name: str):
        """Add a boss to the pool.
        
        Usage: [p]ba config addboss [emoji] <name>
        If emoji is omitted, ⚔️ is used.
        """
        # Simple emoji validation
        test_emoji = emoji
        if test_emoji and not (test_emoji.startswith("<") and test_emoji.endswith(">")):
            # If it's not a custom emoji, check if it's likely a single unicode character/sequence
            # If it's longer than 10 chars and doesn't look like custom, it's probably a name word
            if len(test_emoji) > 10:
                return await ctx.send(f"❌ **Error:** '{test_emoji}' doesn't look like a valid emoji. Did you forget to put the emoji FIRST?\nUsage: `[p]ba config addboss ⚔️ Grand Protector of Anxi`")

        async with self.config.guild(ctx.guild).boss_pool() as p: 
            p[name] = emoji
        await ctx.tick()

    @ba_config.command(name="listboss")
    async def config_list_boss(self, ctx: commands.Context):
        """List all bosses currently in the pool."""
        pool = await self.config.guild(ctx.guild).boss_pool()
        if not pool:
            return await ctx.send("Boss pool is empty.")

        seen = await self.config.guild(ctx.guild).seen_bosses()
        lines = []
        for name in sorted(pool.keys()):
            emoji = pool[name]
            status = "seen" if name in seen else "new"
            lines.append(f"{emoji} **{name}** ({status})")

        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            chunks.append(current)

        for i, chunk in enumerate(chunks):
            title = f"Boss Pool ({len(pool)})"
            if len(chunks) > 1:
                title += f" [{i + 1}/{len(chunks)}]"
            embed = discord.Embed(title=title, description=chunk, color=discord.Color.blurple())
            await ctx.send(embed=embed)

    @ba_config.command(name="removeboss")
    async def config_remove_boss(self, ctx: commands.Context, *, name: str):
        """Remove a boss from the pool.
        
        This also clears the boss from the 'seen' history, so re-adding it 
        will make it appear as a 'New' boss again.
        """
        async with self.config.guild(ctx.guild).boss_pool() as p:
            if name in p:
                del p[name]
                
                # Also remove from seen_bosses history to allow "resetting" a boss
                async with self.config.guild(ctx.guild).seen_bosses() as seen:
                    if name in seen:
                        seen.remove(name)
                        
                await ctx.send(f"✅ Removed **{name}** from the boss pool and cleared its 'seen' history.")
            else:
                await ctx.send(f"❌ Boss **{name}** not found.")

    @ba_config.command(name="newemote")
    async def config_new_emote(self, ctx: commands.Context, emote: str):
        """Set the emote used to indicate a New Priority boss."""
        await self.config.guild(ctx.guild).new_boss_emote.set(emote)
        await ctx.send(f"New priority boss emote set to: {emote}")

    @ba_config.command(name="markunseen")
    async def config_mark_unseen(self, ctx: commands.Context, *emotes: str):
        """Mark one or more bosses as unseen again, identified by their boss icon/emote.

        Removes the matching boss(es) from the 'seen' history so they'll be
        treated as 'New' again in the next season setup. Pass multiple emotes
        to reset multiple bosses at once.

        Usage: [p]ba config markunseen <emote> [emote2] [emote3] ...
        """
        if not emotes:
            return await ctx.send("❌ Provide at least one boss emote to mark as unseen.")

        pool = await self.config.guild(ctx.guild).boss_pool()

        # Map emote -> [boss names using it] (an emote can be shared by multiple bosses)
        emote_to_names: Dict[str, List[str]] = {}
        for name, emoji in pool.items():
            emote_to_names.setdefault(emoji, []).append(name)

        not_found = []
        ambiguous = []
        to_reset = []
        for emote in emotes:
            names = emote_to_names.get(emote)
            if not names:
                not_found.append(emote)
            elif len(names) > 1:
                ambiguous.append((emote, names))
            else:
                to_reset.append(names[0])

        if ambiguous:
            lines = "\n".join(f"{emote} → {', '.join(names)}" for emote, names in ambiguous)
            return await ctx.send(
                f"❌ **Ambiguous emote(s):** multiple bosses share the same icon. "
                f"Use `[p]ba config listboss` and remove/re-add with a unique emote, "
                f"or resolve manually:\n{lines}"
            )

        if not to_reset:
            return await ctx.send(f"❌ No bosses found using emote(s): {' '.join(not_found)}")

        async with self.config.guild(ctx.guild).seen_bosses() as seen:
            actually_reset = [name for name in to_reset if name in seen]
            for name in actually_reset:
                seen.remove(name)

        msg = f"✅ Marked as unseen: {', '.join(actually_reset) if actually_reset else 'none (already unseen)'}"
        if not_found:
            msg += f"\n⚠️ No boss found for emote(s): {' '.join(not_found)}"
        already_unseen = [name for name in to_reset if name not in actually_reset]
        if already_unseen:
            msg += f"\nℹ️ Already unseen: {', '.join(already_unseen)}"
        await ctx.send(msg)

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
            s["roster"] = [new_name if b == old_name else b for b in s["roster"]]
            s["special_anchors"] = [new_name if b == old_name else b for b in s.get("special_anchors", [])]
            s["special_guests"] = [new_name if b == old_name else b for b in s.get("special_guests", [])]
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
        """Initialize a new season based on current poll votes.

        Seasons normally run 4 weeks, but a "special" 5-week season happens
        automatically when the calendar gap to next month allows it - special
        seasons need 7 bosses in the pool instead of 6. Any slots not covered by
        votes are filled randomly (unvoted/new bosses first) so a season can still
        be formed even with low or no turnout.

        Also ensures the rest of the calendar year's season schedule (start/end
        dates only, one season per month) is pre-generated. If a season is
        already active, or the next scheduled slot hasn't started yet, this
        just refreshes/displays the queue without activating anything.

        **Examples:**
        - `[p]ba season setup` - Start the season now (if due) and show the year's schedule
        """
        async with ctx.typing():
            poll_data = await self.config.guild(ctx.guild).active_poll()
            votes = poll_data.get("votes", {})
            boss_pool = await self.config.guild(ctx.guild).boss_pool()

            if len(boss_pool) < 6:
                return await ctx.send(f"❌ **Setup Failed:** Only **{len(boss_pool)}** bosses in the pool. Need at least **6** to generate a season.")

            tally = self._calculate_weighted_tally(votes)
            if len(tally) < 6:
                await ctx.send(f"⚠️ Only **{len(tally)}** boss(es) have votes - filling the rest of the roster randomly.")

            status, weeks, max_week = await self._resolve_season_activation(ctx.guild)

            if status == "active":
                season = await self.config.guild(ctx.guild).season_data()
                queue = season.get("season_queue", [])
                await ctx.send("ℹ️ A season is already active. The year's schedule has been refreshed; it will auto-advance to the next queued season when this one ends.")
                await self._show_season_queue(ctx, queue)
                return

            if status == "none":
                season = await self.config.guild(ctx.guild).season_data()
                queue = season.get("season_queue", [])
                await ctx.send("ℹ️ No season is due to start yet, and not enough of this month remains for a fallback season. Here's the upcoming schedule:")
                await self._show_season_queue(ctx, queue)
                return

            if weeks == 5 and len(boss_pool) < 7:
                return await ctx.send(f"❌ **Setup Failed:** The next season is a special 5-week season, which needs **7** bosses in the pool (only **{len(boss_pool)}** available).")

            embed = await self._setup_new_season_logic(ctx.guild, weeks=weeks, max_week=max_week)
            if embed:
                if status == "due":
                    await self._consume_due_season_slot(ctx.guild)
                await ctx.send(embed=embed)
                season = await self.config.guild(ctx.guild).season_data()
                bosses = self._get_bosses_for_week(season, season["current_week"])
                await self.config.guild(ctx.guild).active_run.set({
                    "boss_order": bosses, "current_index": -1, "is_running": False, "start_time": None
                })
                await self._refresh_live_season_view(ctx.guild)
                if status == "fallback":
                    await ctx.send(f"✅ **Success:** Fallback season initialized (Week 1-{max_week} only). Week 1 schedule set.")
                elif weeks == 5:
                    await ctx.send("✅ **Success:** ✨ Special 5-week season initialized and Week 1 schedule set.")
                else:
                    await ctx.send("✅ **Success:** Season 1 initialized and Week 1 schedule set.")
            else:
                await ctx.send("❌ **Setup Failed:** An internal error occurred while generating the season roster.")

    async def _show_season_queue(self, ctx: commands.Context, queue: List[Dict[str, str]]):
        if not queue:
            return await ctx.send("*No upcoming seasons queued.*")
        lines = [
            f"🗓️ {datetime.fromisoformat(e['start']).strftime('%b %d, %Y')}{' ✨special' if e.get('weeks') == 5 else ''}"
            for e in queue
        ]
        await ctx.send("**Upcoming Seasons:**\n" + "\n".join(lines))

    @ba_season.command(name="setweek")
    async def season_set_week(self, ctx: commands.Context, week: int):
        season_weeks = (await self.config.guild(ctx.guild).season_data()).get("weeks", 4)
        if not (1 <= week <= season_weeks): return await ctx.send(f"Week must be between 1 and {season_weeks}.")
        async with self.config.guild(ctx.guild).season_data() as s:
            s["current_week"] = week; s["is_active"] = True
            
            # Update last_reset to the most recent Sunday 22:00
            server_tz = timezone(timedelta(hours=1))
            now = datetime.now(server_tz)
            days_back = (now.weekday() - 6) % 7
            target_reset = now.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(days=days_back)
            if target_reset > now: target_reset -= timedelta(days=7)
            s["last_reset"] = target_reset.isoformat()
        
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
    def __init__(self, cog, guild, user_id, pool, current_votes, seen_bosses):
        super().__init__()
        self.cog = cog; self.guild = guild; self.user_id = user_id
        Label_cls = Label or getattr(discord.ui, "Label", None)
        cur_anchors = current_votes[0] if current_votes and isinstance(current_votes[0], list) else []
        cur_encore = current_votes[1] if current_votes and len(current_votes) > 1 else None
        cur_guests = current_votes[2] if current_votes and len(current_votes) > 2 and isinstance(current_votes[2], list) else []
        
        # Sort pool items: unseen bosses first, then alphabetically
        sorted_pool = sorted(pool.items(), key=lambda x: (x[0] in seen_bosses, x[0]))
        
        def safe_emoji(e):
            if not e: return None
            # Check if unicode or custom emoji format
            if len(e) <= 8 or (e.startswith("<") and e.endswith(">")):
                return e
            return "⚔️" # Fallback for corrupted/invalid emojis

        anchor_opts = [discord.SelectOption(label=n[:100], value=n[:100], emoji=safe_emoji(e), default=(n in cur_anchors)) for n, e in sorted_pool[:25]]
        self.anchor = StringSelect(placeholder="Select up to 2 Anchors...", min_values=0, max_values=2, options=anchor_opts, custom_id="anchor")
        encore_opts = [discord.SelectOption(label=n[:100], value=n[:100], emoji=safe_emoji(e), default=(n == cur_encore)) for n, e in sorted_pool[:25]]
        self.encore = StringSelect(placeholder="Select Encore Preference...", min_values=0, options=encore_opts, custom_id="encore")
        guest_opts = [discord.SelectOption(label=n[:100], value=n[:100], emoji=safe_emoji(e), default=(n in cur_guests)) for n, e in sorted_pool[:25]]
        self.guests = StringSelect(placeholder="Select up to 4 other bosses...", min_values=0, max_values=4, options=guest_opts, custom_id="guests")
        if Label_cls:
            self.add_item(Label_cls("Anchor Votes (2.5 pts ea, max 2)", self.anchor))
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
        seen_bosses = await actual_cog.config.guild(interaction.guild).seen_bosses()
        cur_votes = poll_data.get("votes", {}).get(str(interaction.user.id), [])
        await interaction.response.send_modal(BossVoteModal(actual_cog, interaction.guild, interaction.user.id, pool, cur_votes, seen_bosses))
    @discord.ui.button(label="Total Results", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="ba_results")
    async def results(self, interaction: discord.Interaction, button: discord.ui.Button):
        actual_cog = interaction.client.get_cog("BreakingArmy") or self.cog
        poll = await actual_cog.config.guild(interaction.guild).active_poll()
        boss_pool = await actual_cog.config.guild(interaction.guild).boss_pool()
        new_emote = await actual_cog.config.guild(interaction.guild).new_boss_emote()
        seen_bosses = await actual_cog.config.guild(interaction.guild).seen_bosses()
        tally = actual_cog._calculate_weighted_tally(poll.get("votes", {}))
        
        # New Ranking Logic: All new bosses first, then old
        new_p = sorted([b for b in boss_pool if b not in seen_bosses], key=lambda x: tally.get(x, 0), reverse=True)
        old_p = sorted([b for b in boss_pool if b in seen_bosses], key=lambda x: tally.get(x, 0), reverse=True)
        ranked = new_p + old_p

        if not ranked: return await interaction.response.send_message("No bosses in pool.", ephemeral=True)

        slot_of: Dict[str, str] = {}
        if len(new_p) + len(old_p) >= 6:
            _, _, slot_of = actual_cog._compute_season_assignment(new_p, old_p, boss_pool, seen_bosses)

        res = "**Current Priority Order (New Bosses First):**\n"
        for i, name in enumerate(ranked):
            pts = tally.get(name, 0)
            role = f" ({slot_of[name]})" if name in slot_of else ""
            suffix = f" {new_emote}" if name not in seen_bosses else ""
            res += f"{i+1}. {boss_pool.get(name, '⚔️')} **{name}**{suffix}: {pts:g} pts{role}\n"
        await interaction.response.send_message(res, ephemeral=True)