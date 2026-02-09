import discord
import logging
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Set, List, Tuple

from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from discord.ext import tasks

log = logging.getLogger("red.asdas-cogs.activitylogger")

class ActivityLogger(commands.Cog):
    """
    Advanced activity logging with privacy-focused data aging.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        default_guild = {
            "users": {}, 
            "backtracked_channels": [],
            "staff_roles": [],
            "global_daily_messages": {},
            "global_daily_vc_minutes": {},
            "global_daily_hourly_messages": {}, # date -> [0]*24
            "global_daily_hourly_vc_minutes": {}, # date -> [0.0]*24
            "global_hourly_messages": [0] * 24, # Legacy/Aggregate
            "global_hourly_vc_minutes": [0.0] * 24, # Legacy/Aggregate
        }
        self.config.register_guild(**default_guild)
        
        self.vc_joins: Dict[tuple, float] = {}
        self.backtracking_guilds: Set[int] = set()
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Daily task to anonymize/purge data older than 1 year, and remove users who left 30+ days ago."""
        all_guilds = await self.config.all_guilds()
        now_date = date.today()
        purge_cutoff = now_date - timedelta(days=365) # 1 year
        leave_cutoff = now_date - timedelta(days=30)
        
        for guild_id, settings in all_guilds.items():
            guild = self.bot.get_guild(int(guild_id))
            users = settings.get("users", {})
            changed = False
            to_delete = []
            
            for u_id, u_data in users.items():
                if guild:
                    member = guild.get_member(int(u_id))
                    if not member:
                        left_at_str = u_data.get("left_at")
                        if left_at_str:
                            if date.fromisoformat(left_at_str) < leave_cutoff:
                                to_delete.append(u_id)
                                continue
                        else:
                            last_active_str = u_data.get("last_active")
                            if last_active_str and date.fromisoformat(last_active_str) < leave_cutoff:
                                to_delete.append(u_id)
                                continue
                            else:
                                u_data["left_at"] = now_date.isoformat()
                                changed = True
                    elif u_data.get("left_at"):
                        u_data["left_at"] = None
                        changed = True

                daily_msgs = u_data.get("daily_messages", {})
                old_keys = [d for d in daily_msgs if date.fromisoformat(d) < purge_cutoff]
                if old_keys:
                    for k in old_keys: del daily_msgs[k]
                    changed = True
                
                daily_vc = u_data.get("daily_vc_minutes", {})
                old_vc_keys = [d for d in daily_vc if date.fromisoformat(d) < purge_cutoff]
                if old_vc_keys:
                    for k in old_vc_keys: del daily_vc[k]
                    changed = True
            
            for u_id in to_delete:
                del users[u_id]
                changed = True

            for key in ["global_daily_messages", "global_daily_vc_minutes", "global_daily_hourly_messages", "global_daily_hourly_vc_minutes"]:
                data = settings.get(key, {})
                old_keys = [d for d in data if date.fromisoformat(d) < purge_cutoff]
                if old_keys:
                    for k in old_keys: del data[k]
                    changed = True

            if changed:
                await self.config.guild_from_id(guild_id).users.set(users)
                guild_conf = self.config.guild_from_id(guild_id)
                await guild_conf.global_daily_messages.set(settings.get("global_daily_messages", {}))
                await guild_conf.global_daily_vc_minutes.set(settings.get("global_daily_vc_minutes", {}))
                await guild_conf.global_daily_hourly_messages.set(settings.get("global_daily_hourly_messages", {}))
                await guild_conf.global_daily_hourly_vc_minutes.set(settings.get("global_daily_hourly_vc_minutes", {}))

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()

    def _get_user_template(self):
        return {
            "daily_messages": {},
            "daily_vc_minutes": {},
            "hourly_messages": [0] * 24,
            "hourly_vc_minutes": [0.0] * 24,
            "last_active": None,
            "current_streak": 0,
            "best_streak": 0,
            "left_at": None
        }

    async def _update_global(self, guild: discord.Guild, date_str: str, hour: int, msg_count: int = 0, vc_mins: float = 0.0):
        async with self.config.guild(guild).all() as conf:
            if msg_count:
                conf.setdefault("global_daily_messages", {})[date_str] = conf.get("global_daily_messages", {}).get(date_str, 0) + msg_count
                conf.setdefault("global_hourly_messages", [0] * 24)[hour] += msg_count
                gdhm = conf.setdefault("global_daily_hourly_messages", {})
                gdhm.setdefault(date_str, [0] * 24)[hour] += msg_count
            if vc_mins:
                conf.setdefault("global_daily_vc_minutes", {})[date_str] = conf.get("global_daily_vc_minutes", {}).get(date_str, 0.0) + vc_mins
                conf.setdefault("global_hourly_vc_minutes", [0.0] * 24)[hour] += vc_mins
                gdhvc = conf.setdefault("global_daily_hourly_vc_minutes", {})
                gdhvc.setdefault(date_str, [0.0] * 24)[hour] += vc_mins

    def _update_streak(self, user_record: dict, today: date):
        user_record["left_at"] = None 
        last_active_str = user_record.get("last_active")
        if not last_active_str:
            user_record["current_streak"] = 1
            user_record["best_streak"] = 1
        else:
            last_active = date.fromisoformat(last_active_str)
            if last_active == today:
                pass 
            elif last_active == today - timedelta(days=1):
                user_record["current_streak"] += 1
                if user_record["current_streak"] > user_record.get("best_streak", 0):
                    user_record["best_streak"] = user_record["current_streak"]
            else:
                user_record["current_streak"] = 1
        user_record["last_active"] = today.isoformat()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or message.webhook_id: return
        prefixes = await self.bot.get_valid_prefixes(message.guild)
        if any(message.content.startswith(p) for p in prefixes): return

        u_id = str(message.author.id)
        now = datetime.now()
        today_str = now.date().isoformat()
        hour = now.hour

        async with self.config.guild(message.guild).all() as conf:
            users = conf.setdefault("users", {})
            u_data = users.setdefault(u_id, self._get_user_template())
            u_data["daily_messages"][today_str] = u_data["daily_messages"].get(today_str, 0) + 1
            u_data.setdefault("hourly_messages", [0] * 24)[hour] += 1
            self._update_streak(u_data, now.date())
            
            gdm = conf.setdefault("global_daily_messages", {})
            gdm[today_str] = gdm.get(today_str, 0) + 1
            ghm = conf.setdefault("global_hourly_messages", [0] * 24)
            ghm[hour] += 1
            gdhm = conf.setdefault("global_daily_hourly_messages", {})
            gdhm.setdefault(today_str, [0] * 24)[hour] += 1

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        async with self.config.guild(member.guild).users() as users:
            if str(member.id) in users:
                users[str(member.id)]["left_at"] = date.today().isoformat()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with self.config.guild(member.guild).users() as users:
            if str(member.id) in users:
                users[str(member.id)]["left_at"] = None

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return
        guild = member.guild
        u_id = str(member.id)
        now = datetime.now()
        today_str = now.date().isoformat()
        hour = now.hour

        if before.channel is None and after.channel is not None:
            self.vc_joins[(guild.id, member.id)] = now.timestamp()
            async with self.config.guild(guild).users() as users:
                users.setdefault(u_id, self._get_user_template())

        elif before.channel is not None and after.channel is None:
            join_time = self.vc_joins.pop((guild.id, member.id), None)
            if join_time:
                mins = (now.timestamp() - join_time) / 60
                async with self.config.guild(guild).all() as conf:
                    users = conf.setdefault("users", {})
                    u_data = users.setdefault(u_id, self._get_user_template())
                    u_data["daily_vc_minutes"][today_str] = u_data["daily_vc_minutes"].get(today_str, 0.0) + mins
                    u_data.setdefault("hourly_vc_minutes", [0.0] * 24)[hour] += mins
                    self._update_streak(u_data, now.date())
                    
                    gdvc = conf.setdefault("global_daily_vc_minutes", {})
                    gdvc[today_str] = gdvc.get(today_str, 0.0) + mins
                    ghvc = conf.setdefault("global_hourly_vc_minutes", [0.0] * 24)
                    ghvc[hour] += mins
                    gdhvc = conf.setdefault("global_daily_hourly_vc_minutes", {})
                    gdhvc.setdefault(today_str, [0.0] * 24)[hour] += mins

    def _get_period_data(self, daily_dict: Dict[str, Any], months: int, start_offset_months: int = 0) -> Dict[str, Any]:
        if months <= 0 and start_offset_months == 0: return daily_dict
        today = date.today()
        t_limit_new = today - timedelta(days=start_offset_months * 30)
        t_limit_old = today - timedelta(days=(start_offset_months + months) * 30) if months > 0 else None
        
        res = {}
        for d_str, count in daily_dict.items():
            d = date.fromisoformat(d_str)
            if d <= t_limit_new and (t_limit_old is None or d > t_limit_old):
                res[d_str] = count
        return res

    @commands.group(aliases=["act"])
    @commands.guild_only()
    async def activity(self, ctx):
        """Activity logging commands."""
        pass

    @activity.command(name="roles")
    @checks.admin_or_permissions(manage_guild=True)
    async def activity_roles(self, ctx, role: discord.Role):
        """Add/Remove a role that can view other users' stats and interact with any buttons."""
        async with self.config.guild(ctx.guild).staff_roles() as roles:
            if role.id in roles:
                roles.remove(role.id)
                await ctx.send(f"✅ Role `{role.name}` removed from staff roles.")
            else:
                roles.append(role.id)
                await ctx.send(f"✅ Role `{role.name}` added to staff roles.")

    @activity.command(name="stats")
    async def activity_stats(self, ctx, member: Optional[discord.Member] = None):
        """View activity stats with interactive period switching."""
        member = member or ctx.author
        
        # Privacy Check
        if member != ctx.author:
            is_owner = await self.bot.is_owner(ctx.author)
            staff_ids = await self.config.guild(ctx.guild).staff_roles()
            has_staff_role = any(r.id in staff_ids for r in ctx.author.roles)
            is_admin = ctx.author.guild_permissions.manage_guild
            
            if not (is_owner or is_admin or has_staff_role):
                return await ctx.send("❌ You do not have permission to view other users' statistics.")

        users = await self.config.guild(ctx.guild).users()
        data = users.get(str(member.id))
        if not data: return await ctx.send("No data.")
        
        view = ActivityUserStatsView(self, ctx, member, data)
        await view.start()

    @activity.command(name="trends")
    async def activity_trends(self, ctx, months: int = 0):
        """View global server trends."""
        conf = await self.config.guild(ctx.guild).all()
        period_msgs = self._get_period_data(conf["global_daily_messages"], months)
        global_hourly = conf["global_hourly_messages"]
        
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        msgs_by_day = [0] * 7
        for d_str, count in period_msgs.items():
            msgs_by_day[date.fromisoformat(d_str).weekday()] += count

        embed = discord.Embed(title="Server Activity Trends", color=discord.Color.blue())
        heatmap = "".join([f"`{h:02d}h`: {'█' * int(global_hourly[h]/max(global_hourly)*10 if max(global_hourly)>0 else 0)}\n" for h in range(24)])
        embed.add_field(name="📅 Daily Distribution", value="\n".join([f"**{day_names[i]}:** {msgs_by_day[i]}" for i in range(7)]), inline=True)
        embed.add_field(name="⏰ Hourly Heatmap", value=heatmap or "No data", inline=True)
        await ctx.send(embed=embed)

    @activity.command(name="leaderboard", aliases=["lb", "top"])
    async def activity_leaderboard(self, ctx, sort_by: str = "messages", months: int = 0):
        """Paginated leaderboard for active members."""
        users = await self.config.guild(ctx.guild).users()
        leaderboard = []
        for u_id, u_data in users.items():
            p_data = self._get_period_data(u_data.get("daily_messages" if sort_by in ["messages", "msgs"] else "daily_vc_minutes", {}), months)
            score = sum(p_data.values())
            if score > 0: leaderboard.append((int(u_id), score))
        
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        if not leaderboard: return await ctx.send("No data.")

        pages = []
        for i in range(0, len(leaderboard), 10):
            chunk = leaderboard[i:i+10]
            desc = "\n".join([f"{j}. **{(ctx.guild.get_member(uid).display_name if ctx.guild.get_member(uid) else uid)}**: {s:.0f}" for j, (uid, s) in enumerate(chunk, i+1)])
            pages.append(discord.Embed(title="Activity Leaderboard", description=desc, color=discord.Color.gold()))
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @activity.command(name="inactive")
    @checks.admin_or_permissions(manage_guild=True)
    async def activity_inactive(self, ctx, days: int = 30):
        """Find members inactive for X+ days."""
        users = await self.config.guild(ctx.guild).users()
        cutoff = date.today() - timedelta(days=days)
        inactive = [f"• {ctx.guild.get_member(int(uid)).mention} (Last: {data.get('last_active', 'Never')})" for uid, data in users.items() if ctx.guild.get_member(int(uid)) and (not data.get('last_active') or date.fromisoformat(data['last_active']) < cutoff)]
        if not inactive: return await ctx.send("No inactive members.")
        pages = [discord.Embed(title=f"Inactive ({days}d+)", description="\n".join(inactive[i:i+15]), color=discord.Color.red()) for i in range(0, len(inactive), 15)]
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @activity.command(name="retention")
    async def activity_retention(self, ctx):
        """View server-wide retention."""
        users = await self.config.guild(ctx.guild).users()
        t = date.today()
        m1, m2 = t - timedelta(days=30), t - timedelta(days=60)
        a1 = {uid for uid, d in users.items() if any(date.fromisoformat(ds) >= m1 for ds in d.get("daily_messages", {}))}
        a2 = {uid for uid, d in users.items() if any(m2 <= date.fromisoformat(ds) < m1 for ds in d.get("daily_messages", {}))}
        rate = (len(a1 & a2) / len(a2) * 100) if a2 else 0
        await ctx.send(embed=discord.Embed(title="Retention", description=f"**Active (0-30d):** {len(a1)}\n**Active (30-60d):** {len(a2)}\n**Retention:** {rate:.1f}%", color=discord.Color.green()))

    @activity.command(name="resetall")
    @checks.is_owner()
    async def activity_reset_all(self, ctx, confirm: bool = False):
        """DANGEROUS: Wipe all activity data."""
        if not confirm:
            return await ctx.send("⚠️ Use `[p]activity resetall true` to confirm.")
        await self.config.guild(ctx.guild).clear()
        await ctx.send("✅ Data wiped.")

    @activity.command(name="resetbacktrack")
    @checks.admin_or_permissions(manage_guild=True)
    async def activity_reset_backtrack(self, ctx):
        """Reset backtrack status."""
        await self.config.guild(ctx.guild).backtracked_channels.set([])
        await ctx.send("✅ Backtrack reset.")

    @activity.command(name="dashboard", aliases=["dash", "all"])
    async def activity_dashboard(self, ctx):
        """Interactive dashboard."""
        view = ActivityDashboardView(self, ctx)
        await view.start()

    @activity.command(name="backtrack")
    @checks.admin_or_permissions(manage_guild=True)
    async def activity_backtrack(self, ctx):
        """Sync history."""
        if ctx.guild.id in self.backtracking_guilds:
            return await ctx.send("❌ Already in progress.")
        self.backtracking_guilds.add(ctx.guild.id)
        asyncio.create_task(self._do_backtrack(ctx))

    async def _do_backtrack(self, ctx):
        guild = ctx.guild
        msg = await ctx.send("🔄 Gathering channels...")
        try:
            bc = await self.config.guild(guild).backtracked_channels()
            bc_set = set(bc)
            channels_to_scan = []
            for c in (guild.text_channels + guild.voice_channels):
                if c.id not in bc_set: channels_to_scan.append(c)
            for t in guild.threads:
                if t.id not in bc_set: channels_to_scan.append(t)
            forums = getattr(guild, "forum_channels", [])
            for c in (guild.text_channels + forums):
                if not c.permissions_for(guild.me).read_message_history: continue
                try:
                    async for t in c.archived_threads(limit=None):
                        if t.id not in bc_set: channels_to_scan.append(t)
                except: continue

            total_channels = len(channels_to_scan)
            if total_channels == 0:
                await msg.edit(content="✅ Already backtracked.")
                return

            await msg.edit(content=f"🔄 Syncing {total_channels} channels...")
            for i, channel in enumerate(channels_to_scan, 1):
                if not channel.permissions_for(guild.me).read_message_history: continue
                await msg.edit(content=f"🔄 Syncing {i}/{total_channels}: {channel.name}...")
                try:
                    temp_u, temp_global_daily, temp_global_hourly_daily, temp_global_agg_hourly = {}, {}, {}, [0]*24
                    count = 0
                    prefixes = await self.bot.get_valid_prefixes(guild)
                    async for m in channel.history(limit=None, oldest_first=True):
                        if m.author.bot or m.webhook_id: continue
                        if any(m.content.startswith(p) for p in prefixes): continue
                        
                        u_id, d_str, hour = str(m.author.id), m.created_at.date().isoformat(), m.created_at.hour
                        if u_id not in temp_u: temp_u[u_id] = {"daily": {}, "hourly": [0]*24}
                        temp_u[u_id]["daily"][d_str] = temp_u[u_id]["daily"].get(d_str, 0) + 1
                        temp_u[u_id]["hourly"][hour] += 1
                        temp_global_daily[d_str] = temp_global_daily.get(d_str, 0) + 1
                        temp_global_hourly_daily.setdefault(d_str, [0]*24)[hour] += 1
                        temp_global_agg_hourly[hour] += 1
                        count += 1

                    if count > 0:
                        async with self.config.guild(guild).all() as conf:
                            g_daily = conf.setdefault("global_daily_messages", {})
                            for ds, c in temp_global_daily.items(): g_daily[ds] = g_daily.get(ds, 0) + c
                            g_hourly = conf.setdefault("global_hourly_messages", [0]*24)
                            for h in range(24): g_hourly[h] += temp_global_agg_hourly[h]
                            g_dh = conf.setdefault("global_daily_hourly_messages", {})
                            for ds, hrs in temp_global_hourly_daily.items():
                                curr = g_dh.setdefault(ds, [0]*24)
                                for h in range(24): curr[h] += hrs[h]
                            users = conf.setdefault("users", {})
                            for uid, data in temp_u.items():
                                ud = users.setdefault(uid, self._get_user_template())
                                for ds, c in data["daily"].items(): ud["daily_messages"][ds] = ud["daily_messages"].get(ds, 0) + c
                                if "hourly_messages" not in ud: ud["hourly_messages"] = [0]*24
                                for h in range(24): ud["hourly_messages"][h] += data["hourly"][h]
                                lb = max(data["daily"].keys())
                                if not ud["last_active"] or lb > ud["last_active"]: ud["last_active"] = lb
                    
                    async with self.config.guild(guild).backtracked_channels() as bcl:
                        if channel.id not in bcl: bcl.append(channel.id)
                except: continue
            await msg.edit(content="✅ Sync complete.")
        finally:
            self.backtracking_guilds.discard(guild.id)

class ActivityDashboardView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog, self.ctx, self.months, self.message = cog, ctx, 1, None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
                await self.ctx.message.add_reaction("✅")
            except: pass

    async def start(self):
        embed = await self.make_embed()
        self.message = await self.ctx.send(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        is_owner = await self.cog.bot.is_owner(interaction.user)
        staff_ids = await self.cog.config.guild(self.ctx.guild).staff_roles()
        has_staff_role = any(r.id in staff_ids for r in interaction.user.roles)
        is_admin = interaction.user.guild_permissions.manage_guild
        if is_owner or is_admin or has_staff_role:
            return True
        await interaction.response.send_message("❌ Only staff can interact with the global dashboard.", ephemeral=True)
        return False

    async def make_embed(self):
        conf = await self.cog.config.guild(self.ctx.guild).all()
        users, t, stats_months = conf.get("users", {}), date.today(), self.months
        ret_map = {1:(0,1,1,1), 3:(0,3,3,3), 6:(3,3,6,3), 9:(6,3,9,3), 0:(0,1,1,1)}
        r_off, r_win, p_off, p_win = ret_map[self.months]
        
        p_msgs = self.cog._get_period_data(conf["global_daily_messages"], stats_months, 0)
        total_msgs, total_vc = sum(p_msgs.values()), sum(self.cog._get_period_data(conf["global_daily_vc_minutes"], stats_months, 0).values())
        
        active_in_period, u_msg_s, u_vc_s = set(), [], []
        for uid, d in users.items():
            ms = sum(self.cog._get_period_data(d.get("daily_messages", {}), stats_months, 0).values())
            vs = sum(self.cog._get_period_data(d.get("daily_vc_minutes", {}), stats_months, 0).values())
            if ms > 0: active_in_period.add(uid); u_msg_s.append((uid, ms))
            if vs > 0: active_in_period.add(uid); u_vc_s.append((uid, vs))
        
        u_msg_s.sort(key=lambda x: x[1], reverse=True); u_vc_s.sort(key=lambda x: x[1], reverse=True)
        top_3_msgs = [f"• **{self.ctx.guild.get_member(int(uid)).display_name if self.ctx.guild.get_member(int(uid)) else uid}**: {s:,}" for uid, s in u_msg_s[:3]]
        top_3_vc = [f"• **{self.ctx.guild.get_member(int(uid)).display_name if self.ctx.guild.get_member(int(uid)) else uid}**: {s:,.1f}m" for uid, s in u_vc_s[:3]]

        coverage_warning = ""
        if self.months == 0:
            active_ever = {uid for uid, d in users.items() if d.get("daily_messages") and self.ctx.guild.get_member(int(uid))}
            retention, ret_label, ret_active_count = (len(active_ever) / self.ctx.guild.member_count * 100) if self.ctx.guild.member_count else 0, "Total Participation", len(active_ever)
        else:
            m_curr_end, m_prev_end = t - timedelta(days=(r_off+r_win)*30), t - timedelta(days=(p_off+p_win)*30)
            oldest = min([date.fromisoformat(d) for d in conf.get("global_daily_messages", {}).keys()]) if conf.get("global_daily_messages") else t
            if oldest > m_prev_end: coverage_warning = "\n⚠️ Partial history"
            a_now, a_prev = set(), set()
            for uid, d in users.items():
                daily = d.get("daily_messages", {})
                if (r_off == 0 and d.get("last_active") and date.fromisoformat(d["last_active"]) >= m_curr_end) or any(m_curr_end <= date.fromisoformat(ds) < (t-timedelta(days=r_off*30)) for ds in daily.keys()): a_now.add(uid)
                if any(m_prev_end <= date.fromisoformat(ds) < m_curr_end for ds in daily.keys()): a_prev.add(uid)
            retention, ret_active_count = (len(a_now & a_prev) / len(a_prev) * 100) if a_prev else 0, len(a_now)
            ret_label = "Last 1 Month" if self.months == 1 else f"Months {self.months-2}-{self.months}"

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        msgs_by_day = [0] * 7
        for d_str, count in p_msgs.items(): msgs_by_day[date.fromisoformat(d_str).weekday()] += count
        day_ranks = sorted(range(7), key=lambda i: msgs_by_day[i], reverse=True)
        dist_lines = [f"**{day_names[i]}:** {msgs_by_day[i]:,} `(#{day_ranks.index(i)+1})`{' 🔥' if day_ranks[0]==i and msgs_by_day[i]>0 else ''}" for i in range(7)]
        
        hourly_data = [0] * 24
        daily_hourly = conf.get("global_daily_hourly_messages", {})
        cutoff = t - timedelta(days=stats_months * 30) if stats_months > 0 else None
        for d_str, hours in daily_hourly.items():
            if cutoff is None or date.fromisoformat(d_str) >= cutoff:
                for h in range(24): hourly_data[h] += hours[h]
        m_h = max(hourly_data) if any(hourly_data) else 1
        heatmap_lines = [f"`{h:02d}h`: {'█' * int(hourly_data[h]/m_h*10)}{'░' * (10-int(hourly_data[h]/m_h*10))} ({hourly_data[h]:,})" for h in range(24)]

        period_label = "Total" if self.months == 0 else f"Last {self.months} Months"
        footer_text = f"Stats: {period_label} | Retention: {ret_label}{' | Partial history' if coverage_warning else ''}"
        embed = discord.Embed(title="Activity Dashboard", color=discord.Color.blue())
        embed.set_footer(text=footer_text)
        embed.add_field(name="📊 Period Totals", value=f"**Messages:** {total_msgs:,}\n**Voice:** {total_vc:,.1f}m\n**Active Users:** {len(active_in_period)}", inline=True)
        embed.add_field(name=f"📈 Retention ({ret_label})", value=f"**Rate:** {retention:.1f}%\n**Window Active:** {ret_active_count}{coverage_warning}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        top_label = " (Past 12 Months)" if self.months == 0 else ""
        embed.add_field(name=f"💬 Top 3 Messages{top_label}", value="\n".join(top_3_msgs) or "No data", inline=True)
        embed.add_field(name=f"🎙️ Top 3 Voice{top_label}", value="\n".join(top_3_vc) or "No data", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="📅 Daily Distribution", value="\n".join(dist_lines), inline=True)
        embed.add_field(name="⏰ Hourly Breakdown", value="\n".join(heatmap_lines), inline=True)
        return embed

    @discord.ui.button(label="1 Month", style=discord.ButtonStyle.primary)
    async def one_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 1; await self.update(i)
    @discord.ui.button(label="3 Months", style=discord.ButtonStyle.gray)
    async def three_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 3; await self.update(i)
    @discord.ui.button(label="6 Months", style=discord.ButtonStyle.gray)
    async def six_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 6; await self.update(i)
    @discord.ui.button(label="9 Months", style=discord.ButtonStyle.gray)
    async def nine_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 9; await self.update(i)
    @discord.ui.button(label="Total", style=discord.ButtonStyle.gray)
    async def global_period(self, i: discord.Interaction, b: discord.ui.Button): self.months = 0; await self.update(i)

    async def update(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.style = discord.ButtonStyle.primary if ((child.label == "Total" and self.months == 0) or (child.label == "1 Month" and self.months == 1) or (child.label == "3 Months" and self.months == 3) or (child.label == "6 Months" and self.months == 6) or (child.label == "9 Months" and self.months == 9)) else discord.ButtonStyle.gray
        await interaction.response.edit_message(embed=await self.make_embed(), view=self)

class ActivityUserStatsView(discord.ui.View):
    def __init__(self, cog, ctx, member, data):
        super().__init__(timeout=120)
        self.cog, self.ctx, self.member, self.data, self.months, self.message = cog, ctx, member, data, 1, None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
                await self.ctx.message.add_reaction("✅")
            except: pass

    async def start(self):
        embed = await self.make_embed()
        self.message = await self.ctx.send(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.member.id:
            return True
        is_owner = await self.cog.bot.is_owner(interaction.user)
        staff_ids = await self.cog.config.guild(self.ctx.guild).staff_roles()
        has_staff_role = any(r.id in staff_ids for r in interaction.user.roles)
        is_admin = interaction.user.guild_permissions.manage_guild
        if is_owner or is_admin or has_staff_role:
            return True
        await interaction.response.send_message("❌ You can only interact with your own statistics.", ephemeral=True)
        return False

    async def make_embed(self):
        m = self.months
        p_msgs = self.cog._get_period_data(self.data.get("daily_messages", {}), m)
        p_vc = self.cog._get_period_data(self.data.get("daily_vc_minutes", {}), m)
        total_msgs, total_vc_min = sum(p_msgs.values()), sum(p_vc.values())
        day_names, msgs_by_day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], [0]*7
        for d_str, count in p_msgs.items(): msgs_by_day[date.fromisoformat(d_str).weekday()] += count
        
        hourly_msgs = self.data.get("hourly_messages", [0]*24)
        night_msgs = sum(hourly_msgs[0:6]) + sum(hourly_msgs[22:24])
        behavior = "Consistent"
        if total_msgs > 0:
            if night_msgs / (total_msgs + 1) > 0.6: behavior = "Night Owl"
            elif (msgs_by_day[5] + msgs_by_day[6]) / (total_msgs + 1) > 0.6: behavior = "Weekend Warrior"

        period_label = "Past 12 Months" if m == 0 else f"Last {m} Months"
        embed = discord.Embed(title=f"Activity Stats: {self.member.display_name}", color=self.member.color)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        embed.set_footer(text=f"Period: {period_label}")
        embed.add_field(name="💬 Messaging", value=f"**Total:** {total_msgs:,}\n**Peak:** {day_names[msgs_by_day.index(max(msgs_by_day))] if total_msgs > 0 else 'N/A'}\n**Behavior:** {behavior}", inline=True)
        embed.add_field(name="🔥 Streaks", value=f"**Current:** {self.data.get('current_streak', 0)}d\n**Best:** {self.data.get('best_streak', 0)}d", inline=True)
        embed.add_field(name="🎙️ Voice", value=f"**Total:** {total_vc_min:,.1f}m\n**Days Active:** {len(p_vc)}", inline=False)
        return embed

    @discord.ui.button(label="1 Month", style=discord.ButtonStyle.primary)
    async def one_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 1; await self.update(i)
    @discord.ui.button(label="3 Months", style=discord.ButtonStyle.gray)
    async def three_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 3; await self.update(i)
    @discord.ui.button(label="6 Months", style=discord.ButtonStyle.gray)
    async def six_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 6; await self.update(i)
    @discord.ui.button(label="9 Months", style=discord.ButtonStyle.gray)
    async def nine_m(self, i: discord.Interaction, b: discord.ui.Button): self.months = 9; await self.update(i)
    @discord.ui.button(label="Total", style=discord.ButtonStyle.gray)
    async def global_period(self, i: discord.Interaction, b: discord.ui.Button): self.months = 0; await self.update(i)

    async def update(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.style = discord.ButtonStyle.primary if ((child.label == "Total" and self.months == 0) or (child.label == "1 Month" and self.months == 1) or (child.label == "3 Months" and self.months == 3) or (child.label == "6 Months" and self.months == 6) or (child.label == "9 Months" and self.months == 9)) else discord.ButtonStyle.gray
        await interaction.response.edit_message(embed=await self.make_embed(), view=self)
