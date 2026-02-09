import discord
import logging
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Set, List, Tuple

from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import paginated_text_entry, box
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
            "global_daily_messages": {},
            "global_daily_vc_minutes": {},
            "global_hourly_messages": [0] * 24,
            "global_hourly_vc_minutes": [0.0] * 24,
        }
        self.config.register_guild(**default_guild)
        
        self.vc_joins: Dict[tuple, float] = {}
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Daily task to anonymize/purge data older than 1 year."""
        all_guilds = await self.config.all_guilds()
        cutoff = date.today() - timedelta(days=365)
        
        for guild_id, settings in all_guilds.items():
            users = settings.get("users", {})
            changed = False
            
            for u_id, u_data in users.items():
                # Clean daily messages
                daily_msgs = u_data.get("daily_messages", {})
                old_keys = [d for d in daily_msgs if date.fromisoformat(d) < cutoff]
                if old_keys:
                    for k in old_keys: del daily_msgs[k]
                    changed = True
                
                # Clean daily VC
                daily_vc = u_data.get("daily_vc_minutes", {})
                old_vc_keys = [d for d in daily_vc if date.fromisoformat(d) < cutoff]
                if old_vc_keys:
                    for k in old_vc_keys: del daily_vc[k]
                    changed = True
            
            if changed:
                await self.config.guild_from_id(guild_id).users.set(users)
                log.info(f"ActivityLogger: Purged data older than {cutoff} for guild {guild_id}")

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
            "best_streak": 0
        }

    async def _update_global(self, guild: discord.Guild, date_str: str, hour: int, msg_count: int = 0, vc_mins: float = 0.0):
        async with self.config.guild(guild).all() as conf:
            if msg_count:
                conf["global_daily_messages"][date_str] = conf["global_daily_messages"].get(date_str, 0) + msg_count
                conf["global_hourly_messages"][hour] += msg_count
            if vc_mins:
                conf["global_daily_vc_minutes"][date_str] = conf["global_daily_vc_minutes"].get(date_str, 0.0) + vc_mins
                conf["global_hourly_vc_minutes"][hour] += vc_mins

    def _update_streak(self, user_record: dict, today: date):
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
        if not message.guild or message.author.bot: return
        u_id = str(message.author.id)
        now = datetime.now()
        today_str = now.date().isoformat()
        hour = now.hour

        async with self.config.guild(message.guild).users() as users:
            u_data = users.setdefault(u_id, self._get_user_template())
            u_data["daily_messages"][today_str] = u_data["daily_messages"].get(today_str, 0) + 1
            u_data["hourly_messages"][hour] += 1
            self._update_streak(u_data, now.date())
        
        await self._update_global(message.guild, today_str, hour, msg_count=1)

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
                async with self.config.guild(guild).users() as users:
                    u_data = users.setdefault(u_id, self._get_user_template())
                    u_data["daily_vc_minutes"][today_str] = u_data["daily_vc_minutes"].get(today_str, 0.0) + mins
                    u_data["hourly_vc_minutes"][hour] += mins
                    self._update_streak(u_data, now.date())
                await self._update_global(guild, today_str, hour, vc_mins=mins)

    def _get_period_data(self, daily_dict: Dict[str, Any], months: int) -> Dict[str, Any]:
        if months <= 0: return daily_dict
        cutoff = date.today() - timedelta(days=months * 30)
        return {d: c for d, c in daily_dict.items() if date.fromisoformat(d) >= cutoff}

    @commands.group(aliases=["act"])
    @commands.guild_only()
    async def activity(self, ctx):
        """Activity logging commands."""
        pass

    @activity.command(name="stats")
    async def activity_stats(self, ctx, member: Optional[discord.Member] = None, months: int = 0):
        """View activity stats with streaks and behavior tags."""
        member = member or ctx.author
        users = await self.config.guild(ctx.guild).users()
        data = users.get(str(member.id))
        if not data: return await ctx.send("No data.")

        period_msgs = self._get_period_data(data.get("daily_messages", {}), months)
        period_vc = self._get_period_data(data.get("daily_vc_minutes", {}), months)
        total_msgs = sum(period_msgs.values())
        total_vc_min = sum(period_vc.values())

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        msgs_by_day = [0] * 7
        for d_str, count in period_msgs.items():
            msgs_by_day[date.fromisoformat(d_str).weekday()] += count
        
        # Tagging
        hourly_msgs = data.get("hourly_messages", [0]*24)
        night_msgs = sum(hourly_msgs[0:6]) + sum(hourly_msgs[22:24])
        behavior = "Consistent"
        if total_msgs > 0:
            if night_msgs / total_msgs > 0.6: behavior = "Night Owl"
            elif (msgs_by_day[5] + msgs_by_day[6]) / total_msgs > 0.6: behavior = "Weekend Warrior"

        embed = discord.Embed(title=f"Activity Stats: {member.display_name}", color=member.color)
        embed.add_field(name="💬 Messaging", value=f"**Total:** {total_msgs}\n**Peak:** {day_names[msgs_by_day.index(max(msgs_by_day))] if total_msgs > 0 else 'N/A'}\n**Behavior:** {behavior}", inline=True)
        embed.add_field(name="🔥 Streaks", value=f"**Current:** {data.get('current_streak', 0)}d\n**Best:** {data.get('best_streak', 0)}d", inline=True)
        embed.add_field(name="🎙️ Voice", value=f"**Total:** {total_vc_min:.1f}m\n**Days:** {len(period_vc)}", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @activity.command(name="trends")
    async def activity_trends(self, ctx, months: int = 0):
        """View global server trends using anonymized aggregate data."""
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
        """View server-wide retention (Active last 30d vs 30-60d ago)."""
        users = await self.config.guild(ctx.guild).users()
        t = date.today()
        m1, m2 = t - timedelta(days=30), t - timedelta(days=60)
        a1 = {uid for uid, d in users.items() if any(date.fromisoformat(ds) >= m1 for ds in d.get("daily_messages", {}))}
        a2 = {uid for uid, d in users.items() if any(m2 <= date.fromisoformat(ds) < m1 for ds in d.get("daily_messages", {}))}
        rate = (len(a1 & a2) / len(a2) * 100) if a2 else 0
        await ctx.send(embed=discord.Embed(title="Retention", description=f"**Active (0-30d):** {len(a1)}\n**Active (30-60d):** {len(a2)}\n**Retention:** {rate:.1f}%", color=discord.Color.green()))

    @activity.command(name="backtrack")
    @checks.admin_or_permissions(manage_guild=True)
    async def activity_backtrack(self, ctx):
        """Sync historical message data."""
        await ctx.send("🔄 Syncing historical message data...")
        asyncio.create_task(self._do_backtrack(ctx))

    async def _do_backtrack(self, ctx):
        guild = ctx.guild
        bc = await self.config.guild(guild).backtracked_channels()
        channels = [c for c in guild.text_channels if c.id not in bc]
        for channel in channels:
            if not channel.permissions_for(guild.me).read_message_history: continue
            try:
                temp_u = {} # u_id -> {date: count}
                async for m in channel.history(limit=None, oldest_first=True):
                    if m.author.bot: continue
                    u_id, d_str = str(m.author.id), m.created_at.date().isoformat()
                    temp_u.setdefault(u_id, {})[d_str] = temp_u[u_id].get(d_str, 0) + 1
                    await self._update_global(guild, d_str, m.created_at.hour, msg_count=1)
                async with self.config.guild(guild).users() as users:
                    for uid, counts in temp_u.items():
                        ud = users.setdefault(uid, self._get_user_template())
                        for d, c in counts.items(): ud["daily_messages"][d] = ud["daily_messages"].get(d, 0) + c
                        latest = max(counts.keys())
                        if not ud["last_active"] or latest > ud["last_active"]: ud["last_active"] = latest
                async with self.config.guild(guild).backtracked_channels() as bcl: bcl.append(channel.id)
            except: continue
        await ctx.send("✅ Historical sync complete.")
