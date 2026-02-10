import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
from typing import Optional, List, Dict, Union
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
                "votes": {},  # user_id: [choice1, choice2, choice3, choice4, choice5]
                "live_view_message": {} 
            },
            "active_run": {
                "message_id": None,
                "channel_id": None,
                "boss_order": [], 
                "current_index": -1,
                "is_running": False,
                "last_auto_trigger": None # YYYY-MM-DDTHH:MM
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
        if member.guild_permissions.manage_guild:
            return True
        admin_roles = await self.config.guild(member.guild).admin_roles()
        for role in member.roles:
            if role.id in admin_roles:
                return True
        return False

    def _calculate_weighted_tally(self, votes: Dict[str, List[str]]) -> Dict[str, int]:
        """Calculates points based on ranking: 5, 4, 3, 2, 1."""
        tally = {}
        for user_choices in votes.values():
            for i, boss in enumerate(user_choices):
                if not boss: continue
                points = 5 - i
                if points < 1: break
                tally[boss] = tally.get(boss, 0) + points
        return tally

    async def _update_live_view(self, guild):
        poll_data = await self.config.guild(guild).active_poll()
        live_view = poll_data.get("live_view_message", {})
        boss_pool = await self.config.guild(guild).boss_pool()
        
        if not live_view.get("message_id"):
            return

        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))
        sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        
        desc = ""
        if not sorted_tally:
            desc = "No votes yet."
        else:
            for boss, points in sorted_tally:
                emote = boss_pool.get(boss, "⚔️")
                desc += f"{emote} **{boss}**: {points} pts\n"
        
        embed = discord.Embed(title="📊 Live Poll Results (Weighted)", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Total Voters: {len(poll_data.get('votes', {}))}")

        try:
            channel = guild.get_channel(live_view["channel_id"])
            if channel:
                msg = await channel.fetch_message(live_view["message_id"])
                await msg.edit(embed=embed)
        except:
            pass

    @tasks.loop(minutes=1)
    async def schedule_checker(self):
        """Checks EventPolling schedule to auto-start runs."""
        try:
            for guild_id in await self.config.all_guilds():
                guild = self.bot.get_guild(guild_id)
                if not guild: continue
                
                polling_cog = self.bot.get_cog("EventPolling")
                if not polling_cog: continue

                # Get winning times from Polling Cog
                # We replicate the logic from EventPolling.event_notification_task
                polls = await polling_cog.config.guild(guild).polls()
                if not polls: continue
                
                latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                poll_data = polls[latest_poll_id]
                selections = poll_data.get("selections", {})
                
                # Reach into polling cog's internal method if possible, or replicate
                # Since we can't easily call private methods, we look for signs of start
                server_tz = timezone(timedelta(hours=1))
                now = datetime.now(server_tz)
                day_name = now.strftime("%A")
                time_str = now.strftime("%H:%M")
                
                # Calculate winners for Breaking Army
                winners = polling_cog._calculate_winning_times_weighted(selections)
                ba_winners = winners.get("Breaking Army", {})
                
                trigger = False
                for slot_data in ba_winners.values():
                    win_key, _, _ = slot_data # (day, time)
                    if win_key[0] == day_name and win_key[1] == time_str:
                        trigger = True
                        break
                
                if trigger:
                    # Check if already triggered in this minute
                    last_trigger = await self.config.guild(guild).active_run.last_auto_trigger()
                    current_key = now.strftime("%Y-%m-%dT%H:%M")
                    if last_trigger != current_key:
                        await self.config.guild(guild).active_run.last_auto_trigger.set(current_key)
                        await self._auto_start_run(guild)
        except Exception as e:
            log.error(f"Error in schedule_checker: {e}")

    async def _auto_start_run(self, guild):
        """Logic to advance week and post dashboard."""
        season = await self.config.guild(guild).season_data()
        if not season["is_active"]: return

        # Advance week logic (simulate [p]ba season next)
        week = season["current_week"]
        if week > 6: return

        anchors = season["anchors"]; guests = season["guests"]
        if week == 1: boss_list = [anchors[0], anchors[1]]
        elif week == 2: boss_list = [anchors[2], guests[0]]
        elif week == 3: boss_list = [anchors[3], guests[1]]
        elif week == 4: boss_list = [anchors[0], anchors[1]]
        elif week == 5: boss_list = [anchors[2], guests[2]]
        elif week == 6: boss_list = [anchors[3], guests[3]]

        # Save Run
        await self.config.guild(guild).active_run.set({
            "boss_order": boss_list, "current_index": 0, "is_running": True
        })
        
        # Post to default channel or polling channel
        poll_data = await self.config.guild(guild).active_poll()
        channel = guild.get_channel(poll_data["channel_id"])
        if channel:
            embed = await self._generate_run_embed(guild, boss_list, 0, True)
            msg = await channel.send(content=f"🚀 **Auto-Starting Breaking Army: Week {week}**", embed=embed)
            async with self.config.guild(guild).active_run() as run:
                run["message_id"] = msg.id
                run["channel_id"] = channel.id

        # Advance week for next time
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
        """Configuration"""
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
        """Season Management"""
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_season.command(name="setup")
    async def season_setup(self, ctx: commands.Context):
        poll_data = await self.config.guild(ctx.guild).active_poll()
        boss_pool = await self.config.guild(ctx.guild).boss_pool()
        seen_bosses = await self.config.guild(ctx.guild).seen_bosses()
        
        tally = self._calculate_weighted_tally(poll_data.get("votes", {}))
        ranked_names = [b[0] for b in sorted(tally.items(), key=lambda x: x[1], reverse=True)]
        
        if len(ranked_names) < 8:
            await ctx.send(f"Need 8 bosses with votes. Have {len(ranked_names)}."); return

        new_bosses = [b for b in ranked_names if b not in seen_bosses]
        anchors = [None]*4; guests = [None]*4; used = []

        if len(new_bosses) >= 1: anchors[0] = new_bosses[0]; used.append(new_bosses[0])
        if len(new_bosses) >= 2: anchors[1] = new_bosses[1]; used.append(new_bosses[1])
        if len(new_bosses) >= 3: anchors[3] = new_bosses[2]; used.append(new_bosses[2])
            
        rem = [b for b in ranked_names if b not in used]
        for i in range(4):
            if anchors[i] is None: anchors[i] = rem.pop(0); used.append(anchors[i])
        for i in range(4):
            if guests[i] is None: guests[i] = rem.pop(0); used.append(guests[i])
        
        async with self.config.guild(ctx.guild).season_data() as s:
            s["anchors"] = anchors; s["guests"] = guests; s["current_week"] = 1; s["is_active"] = True
        async with self.config.guild(ctx.guild).seen_bosses() as seen:
            for b in used: 
                if b not in seen: seen.append(b)
        await ctx.send("Season Setup Complete. Use `[p]ba season show` to see the roster.")

    @ba_season.command(name="show")
    async def season_show(self, ctx: commands.Context):
        """Displays schedule and current run status."""
        season = await self.config.guild(ctx.guild).season_data()
        run = await self.config.guild(ctx.guild).active_run()
        boss_pool = await self.config.guild(ctx.guild).boss_pool()
        
        if not season["anchors"]:
            await ctx.send("No season data."); return

        embed = discord.Embed(title="📅 Breaking Army Season Status", color=discord.Color.blue())
        
        # Schedule
        a = season["anchors"]; g = season["guests"]
        sched = ""
        matrix = [(a[0],a[1]), (a[2],g[0]), (a[3],g[1]), (a[0],a[1]), (a[2],g[2]), (a[3],g[3])]
        for i, (b1, b2) in enumerate(matrix):
            w = i+1
            pref = "▶️ " if w == season["current_week"] and season["is_active"] else ""
            stat = " (Complete)" if w < season["current_week"] else ""
            enc = " (Encore)" if w == 4 else ""
            sched += f"{pref}**W{w}**: {b1} & {b2}{enc}{stat}\n"
        embed.add_field(name="6-Week Schedule", value=sched, inline=False)

        # Current Run if active
        if run["is_running"]:
            run_embed = await self._generate_run_embed(ctx.guild, run["boss_order"], run["current_index"], True)
            await ctx.send(embed=embed)
            await ctx.send(content="🔥 **Current Active Run:**", embed=run_embed)
        else:
            await ctx.send(embed=embed)

    @ba.group(name="run")
    async def ba_run(self, ctx: commands.Context):
        """Manual Run Management"""
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_run.command(name="start")
    async def run_manual_start(self, ctx: commands.Context):
        """Manually trigger the current week's run."""
        await self._auto_start_run(ctx.guild)
        await ctx.send("Manual run triggered.")

    @ba_run.command(name="next", aliases=["bossdown"])
    async def run_next(self, ctx: commands.Context):
        """Advance to the next boss."""
        async with self.config.guild(ctx.guild).active_run() as run:
            if not run["is_running"]: return await ctx.send("No run active.")
            run["current_index"] += 1
            if run["current_index"] >= len(run["boss_order"]):
                run["is_running"] = False
                await ctx.send("🏁 **Run Complete!**")
            else:
                await ctx.send(f"⚔️ Next Target: **{run['boss_order'][run['current_index']]}**")
            
            # Update dashboard if exists
            try:
                channel = ctx.guild.get_channel(run["channel_id"])
                msg = await channel.fetch_message(run["message_id"])
                embed = await self._generate_run_embed(ctx.guild, run["boss_order"], run["current_index"], run["is_running"])
                await msg.edit(embed=embed)
            except: pass

    @ba_run.command(name="cancel")
    async def run_cancel(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).active_run.is_running.set(False)
        await ctx.send("Run cancelled.")

    @ba.group(name="poll")
    async def ba_poll(self, ctx: commands.Context):
        """Poll Management"""
        if not await self.is_ba_admin(ctx.author): raise commands.CheckFailure()
        pass

    @ba_poll.command(name="start")
    async def poll_start(self, ctx: commands.Context):
        if not await self.config.guild(ctx.guild).boss_pool(): return await ctx.send("Pool empty.")
        embed = discord.Embed(title="Breaking Army Voting", description="Rank your Top 5 bosses below!", color=discord.Color.gold())
        view = BossPollView(self)
        msg = await ctx.send(embed=embed, view=view)
        async with self.config.guild(ctx.guild).active_poll() as p:
            p["message_id"] = msg.id; p["channel_id"] = msg.channel.id

    async def _generate_run_embed(self, guild, boss_list, current_index, is_running):
        status = "In Progress" if is_running else "Complete"
        color = discord.Color.green() if is_running else discord.Color.purple()
        pool = await self.config.guild(guild).boss_pool()
        desc = ""
        for i, b in enumerate(boss_list):
            e = pool.get(b, "⚔️")
            if i < current_index: desc += f"💀 ~~{e} {b}~~\n"
            elif i == current_index and is_running: desc += f"⚔️ **__ {e} {b} __** (Target)\n"
            else: desc += f"⏳ {e} {b}\n"
        return discord.Embed(title=f"Breaking Army Run - {status}", description=desc, color=color)

class BossVoteModal(Modal, title="Weighted Boss Ballot"):
    def __init__(self, cog, guild, user_id, pool):
        super().__init__()
        self.cog = cog; self.guild = guild; self.user_id = user_id
        Label_cls = Label or getattr(discord.ui, "Label", None)
        options = [discord.SelectOption(label=n, value=n, emoji=e) for n, e in list(pool.items())[:25]]
        
        self.selects = []
        for i in range(1, 6):
            sel = StringSelect(placeholder=f"Rank {i} Choice...", options=options, custom_id=f"choice_{i}")
            self.selects.append(sel)
            if Label_cls: self.add_item(Label_cls(f"{i}st Choice" if i==1 else f"{i}th Choice", sel))
            else: self.add_item(sel)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        choices = [s.values[0] if s.values else None for s in self.selects]
        async with self.cog.config.guild(interaction.guild).active_poll() as p:
            p["votes"][str(interaction.user.id)] = choices
        await self.cog._update_live_view(interaction.guild)
        await interaction.followup.send("Ballot Saved!", ephemeral=True)

class BossPollView(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog
    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="🗳️", custom_id="ba_vote")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = await self.cog.config.guild(interaction.guild).boss_pool()
        await interaction.response.send_modal(BossVoteModal(self.cog, interaction.guild, interaction.user.id, pool))
