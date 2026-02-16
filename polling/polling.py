from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
import discord
from typing import Optional, Dict, List, Tuple, Union
from datetime import datetime, time as dt_time, timedelta
import os
import tempfile
import re
import json
import base64
import hashlib
from pathlib import Path
import importlib
import logging

from .views import EventPollView
from . import calendar_renderer

log = logging.getLogger("red.asdas-cogs.polling")
log.setLevel(logging.ERROR)  # Only show errors in terminal, not info messages


class EventPolling(commands.Cog):
    """Event scheduling polling system with conflict detection"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config: Config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571751,
            force_registration=True,
        )

        # Store polls per guild
        self.config.register_guild(
            polls={},  # poll_id -> poll data
            notification_channel_id=None,
            notification_message="{event} is starting at {timestamp}!",
            notification_messages={},  # event_name -> message
            sent_notifications={},  # event_name -> last_notification_day_str (YYYY-MM-DD)
            event_roles={},  # event_name -> role_id
        )

        self.config.register_global(
            website_export_path=None,
            export_guild_id=None
        )

        # Event definitions (ordered: Party, Guild War, Hero's Realm, Sword Trial, Breaking Army, Showdown)
        # Priority order for calendar display (higher number = higher priority)
        self.events = {
            "Party": {
                "type": "daily",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,  # 30 minute intervals
                "duration": 10,  # 10 minutes
                "slots": 1,  # Single time slot
                "color": discord.Color(0xe1e7ec),
                "emoji": "🎉",
                "priority": 3,  # Priority 3 (matches results intro)
                "default_times": {
                    "default": "20:00"
                }
            },
            "Guild War": {
                "type": "once",
                "days": ["Saturday", "Sunday"],
                "time_range": (20.5, 23),  # 20:30 to 23:00 (latest start 21:30)
                "fixed_time": "20:30",
                "duration": 90,  # 1.5 hours (e.g., 20:30-22:00 or 21:30-23:00)
                "color": discord.Color(0xe1e7ec),
                "emoji": "🏰",
                "priority": 6,
                "slots": 2,
                "default_times": {
                    "Saturday": "20:30",
                    "Sunday": "20:30"
                }
            },
            "Hero's Realm (Catch-up)": {
                "type": "once",
                "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],  # Available voting days (Mon-Sat only)
                "time_range": (17, 26),  # 17:00 to 02:00 (26 = 02:00 next day)
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 1,  # Single slot - users vote for ONE preferred day+time from Mon-Sat
                "color": discord.Color(0xe1e7ec),
                "emoji": "🛡️",
                "priority": 5,  # Highest priority
                "default_times": {
                    "Friday": "22:00"
                }
            },
            "Hero's Realm (Reset)": {
                "type": "locked",
                "days": ["Sunday"],
                "fixed_time": "22:00",
                "duration": 30,  # 30 minutes
                "color": discord.Color(0xe1e7ec),
                "emoji": "🛡️",
                "priority": 5,
                "slots": 1
            },
            "Sword Trial": {
                "type": "fixed_days",
                "days": ["Wednesday", "Friday"],
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 2,  # 2 slots: one for each day (Wed, Fri)
                "color": discord.Color(0xe1e7ec),
                "emoji": "⚔️",
                "priority": 4,
                "default_times": {
                    "Wednesday": "21:30",
                    "Friday": "21:30"
                }
            },
            "Sword Trial (Echo)": {
                "type": "fixed_days",
                "days": ["Monday"],
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 1,
                "color": discord.Color(0xe1e7ec),
                "emoji": "⚔️",
                "priority": 4,
                "default_times": {
                    "Monday": "21:30"
                }
            },
            "Breaking Army": {
                "type": "once",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color(0xe1e7ec),
                "emoji": "⚡",
                "priority": 2,
                "default_times": {
                    "Wednesday": "19:30",
                    "Friday": "19:30"
                }
            },
            "Showdown": {
                "type": "once",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color(0xe1e7ec),
                "emoji": "🏆",
                "priority": 1,
                "default_times": {
                    "Wednesday": "18:30",
                    "Friday": "18:30"
                }
            }
        }

        # Guild Wars - blocked time event (Sat & Sun 20:30-22:00)
        self.guild_wars_emoji = "🏰"

        self.days_of_week = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        ]

        # Blocked time slots: Sunday 20:30 - 22:00 (Saturday handled as event)
        self.blocked_times = [
            {"day": "Sunday", "start": "20:30", "end": "22:00"}
        ]

        # Event-specific blocked time periods (applies to all days for these events)
        # Events cannot be scheduled if they would overlap with these time periods
        self.event_blocked_times = {
            "Showdown": {"start": "21:30", "end": "01:00"},  # Cannot run during 21:30-01:00, latest start: 20:30 (ends 21:30), earliest start: 01:00
            "Breaking Army": {"start": "20:30", "end": "22:30"},  # Cannot run during 20:30-22:30, latest start: 19:30 (ends 20:30), earliest start: 22:30
            "Party": {"start": "20:40", "end": "22:30"}  # Cannot run during 20:40-22:30, latest start: 20:30 (ends 20:40), earliest start: 22:30
        }

        # Timezone display - customize this to match your server's timezone
        # Examples: "UTC", "UTC+1", "UTC-5", "EST", "PST", "Server Time"
        self.timezone_display = "Server Time (UTC+1)"

        # Initialize calendar renderer
        self.calendar_renderer = calendar_renderer.CalendarRenderer(timezone=self.timezone_display)

        # Backup directory path
        self.backups_dir = Path.cwd() / "data" / "eventpolling" / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    async def cog_load(self):
        """Called when the cog is loaded"""
        # Reload the calendar_renderer module to ensure we have the latest code
        importlib.reload(calendar_renderer)
        # Reinitialize the calendar renderer with the reloaded class
        self.calendar_renderer = calendar_renderer.CalendarRenderer(timezone=self.timezone_display)

        # Restore views for all existing polls after bot restart
        # Don't wait for ready during reload - bot is already running
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            polls = guild_data.get("polls", {})
            for poll_id, poll_data in polls.items():
                await self._restore_poll_view(guild, poll_data, poll_id)
                await self._restore_calendar_views(guild, poll_data, poll_id)
                # Add small delay between restores to avoid rate limiting
                import asyncio
                await asyncio.sleep(0.5)

        self.backup_task.start()
        self.weekly_results_update.start()
        self.weekly_calendar_update.start()
        self.event_notification_task.start()
        self.website_export_task.start()

    def cog_unload(self):
        """Called when the cog is unloaded"""
        self.backup_task.cancel()
        self.weekly_results_update.cancel()
        self.weekly_calendar_update.cancel()
        self.event_notification_task.cancel()
        self.website_export_task.cancel()

    def _get_embed_color(self, guild: discord.Guild) -> discord.Color:
        """Get the poll embed color (0x5a61ee)"""
        return discord.Color(0x5a61ee)

    def _get_calendar_color(self, guild: discord.Guild) -> discord.Color:
        """Get the calendar embed color (0xcb4449)"""
        return discord.Color(0xcb4449)

    @tasks.loop(hours=24)
    async def backup_task(self):
        """Daily backup task for latest active poll"""
        try:
            all_guilds = await self.config.all_guilds()

            # Create timestamp for backup filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backups_dir / f"poll_backup_{timestamp}.json"

            # Prepare backup data
            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "guilds": {}
            }

            # Collect only the latest poll from each guild
            for guild_id, guild_data in all_guilds.items():
                polls = guild_data.get("polls", {})
                if polls:
                    # Find the latest poll (highest message_id = most recent)
                    latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                    backup_data["guilds"][str(guild_id)] = {
                        "polls": {
                            latest_poll_id: polls[latest_poll_id]
                        }
                    }

            # Write backup file
            if backup_data["guilds"]:
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)

                # Keep only last 30 backups (delete older ones)
                backup_files = sorted(self.backups_dir.glob("poll_backup_*.json"))
                if len(backup_files) > 30:
                    for old_backup in backup_files[:-30]:
                        old_backup.unlink()

        except Exception as e:
            # Log error but don't crash
            print(f"Error during poll backup: {e}")

    @backup_task.before_loop
    async def before_backup_task(self):
        """Wait for bot to be ready before starting backup task"""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def weekly_results_update(self):
        """Update weekly results embeds every Monday at 10 AM server time (UTC+1)"""
        try:
            # Get current datetime in server timezone (UTC+1 / Europe/Berlin)
            from datetime import timezone
            server_tz = timezone(timedelta(hours=1))
            now = datetime.now(server_tz)

            # Check if it's Monday (0 = Monday) and between 10:00-10:59 AM
            if now.weekday() != 0 or now.hour != 10:
                return

            # Get all guilds
            all_guilds = await self.config.all_guilds()

            for guild_id, guild_data in all_guilds.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                polls = guild_data.get("polls", {})
                for poll_id, poll_data in polls.items():
                    # Update all results messages for this poll
                    await self._update_results_messages(guild, poll_data, poll_id)

        except Exception as e:
            print(f"Error during weekly results update: {e}")

    @weekly_results_update.before_loop
    async def before_weekly_results_update(self):
        """Wait for bot to be ready before starting weekly results update task"""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def weekly_calendar_update(self):
        """Update weekly calendar embeds every Monday at 10 AM server time (UTC+1)"""
        try:
            # Get current datetime in server timezone (UTC+1 / Europe/Berlin)
            from datetime import timezone
            server_tz = timezone(timedelta(hours=1))
            now = datetime.now(server_tz)

            # Check if it's Monday (0 = Monday) and between 10:00-10:59 AM
            if now.weekday() != 0 or now.hour != 10:
                return

            # Get all guilds
            all_guilds = await self.config.all_guilds()

            for guild_id, guild_data in all_guilds.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                polls = guild_data.get("polls", {})
                for poll_id, poll_data in polls.items():
                    # Update all weekly calendar messages for this poll
                    await self._update_weekly_calendar_messages(guild, poll_data, poll_id)

        except Exception as e:
            print(f"Error during weekly calendar update: {e}")

    @weekly_calendar_update.before_loop
    async def before_weekly_calendar_update(self):
        """Wait for bot to be ready before starting weekly calendar update task"""
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def event_notification_task(self):
        """Check for upcoming events and send notifications"""
        try:
            # Use UTC+1 (CET/CEST) as server time, consistent with other tasks
            from datetime import timezone
            server_tz = timezone(timedelta(hours=1))
            now = datetime.now(server_tz)
            today_str = now.strftime("%Y-%m-%d")
            day_name = now.strftime("%A")

            all_guilds = await self.config.all_guilds()

            for guild_id, guild_data in all_guilds.items():
                channel_id = guild_data.get("notification_channel_id")
                if not channel_id:
                    continue

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue

                polls = guild_data.get("polls", {})
                if not polls:
                    continue

                # Get latest poll
                latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                poll_data = polls[latest_poll_id]
                selections = poll_data.get("selections", {})
                
                # Get winning times - prefer weekly snapshot if available (stable schedule)
                winning_times = poll_data.get("weekly_snapshot_winning_times")
                if not winning_times:
                    # Fallback to live data if no snapshot exists
                    winning_times = self._calculate_winning_times_weighted(selections)
                
                # Get sent notifications for this guild
                sent_notifs = guild_data.get("sent_notifications", {})
                event_roles = guild_data.get("event_roles", {})
                
                # Events to check
                target_events = ["Party", "Showdown", "Breaking Army"]
                
                for event_name in winning_times:
                    # Check if this is a target event
                    if not any(event_name.startswith(t) for t in target_events):
                        continue
                        
                    event_slots = winning_times[event_name]
                    event_info = self.events.get(event_name)
                    if not event_info:
                        continue

                    for slot_idx, slot_data in event_slots.items():
                        winner_key, points, _ = slot_data
                        
                        # Determine winning day/time
                        if event_info["type"] == "daily":
                            win_day = day_name 
                            win_time_str = winner_key[1]
                        elif event_info["type"] in ["fixed_days", "once", "weekly"]:
                             win_day = winner_key[0]
                             win_time_str = winner_key[1]
                        else:
                            continue
                            
                        # Parse time
                        try:
                            h, m = map(int, win_time_str.split(":"))
                            
                            # Determine actual day/time of event
                            is_next_day = h < 17 # Times 00:00 - 16:59 are considered part of the "night" of the previous day
                            
                            should_fire = False
                            
                            if is_next_day:
                                # It's actually the next day relative to win_day
                                prev_day_date = now - timedelta(days=1)
                                prev_day_name = prev_day_date.strftime("%A")
                                
                                if win_day == prev_day_name and now.hour == h and now.minute == m:
                                    should_fire = True

                                # Daily event special case
                                if event_info["type"] == "daily":
                                    if now.hour == h and now.minute == m:
                                        should_fire = True

                            else:
                                # Same day event
                                if win_day == day_name and now.hour == h and now.minute == m:
                                    should_fire = True
                                    
                            if should_fire:
                                # Unique key for this notification instance: event_name + slot + date
                                notif_key = f"{event_name}_{slot_idx}"
                                last_sent = sent_notifs.get(notif_key)
                                
                                if last_sent != today_str:
                                    # Send notification
                                    # Check for event-specific message first
                                    custom_msgs = guild_data.get("notification_messages", {})
                                    msg_tmpl = custom_msgs.get(event_name)
                                    
                                    if not msg_tmpl:
                                        msg_tmpl = guild_data.get("notification_message", "{event} is starting at {timestamp}!")
                                    
                                    # Create timestamp
                                    event_dt = now.replace(second=0, microsecond=0)
                                    ts = int(event_dt.timestamp())
                                    discord_ts = f"<t:{ts}:R>" # Relative format (e.g. "in 2 minutes")
                                    
                                    # Determine display name (Role mention or Bold Text)
                                    role_id = event_roles.get(event_name)
                                    if role_id:
                                        event_display_name = f"<@&{role_id}>"
                                    else:
                                        event_display_name = f"**{event_name}**"

                                    if "Slot" in event_name or (event_info["slots"] > 1 and "Slot" not in event_name):
                                        # Simple cleanup if needed, but event_name usually includes Slot info if managed that way, 
                                        # actually polling.py keys are "Breaking Army", not "Breaking Army Slot 1".
                                        # Slots are indices.
                                        if event_info["slots"] > 1:
                                            # Add slot info if relevant
                                            pass

                                    message = msg_tmpl.replace("{event}", event_display_name)\
                                                      .replace("{timestamp}", discord_ts)\
                                                      .replace("{time_str}", f"{now.hour:02d}:{now.minute:02d}")
                                    
                                    # Handle {boss} variable for Breaking Army
                                    if "{boss}" in message and "Breaking Army" in event_name:
                                        ba_cog = self.bot.get_cog("BreakingArmy")
                                        if ba_cog:
                                            boss_info = await ba_cog._get_current_boss_info(guild)
                                            message = message.replace("{boss}", boss_info or "Unknown Boss")
                                        else:
                                            message = message.replace("{boss}", "Unknown Boss")
                                    
                                    # Calculate auto-delete duration
                                    delete_duration = None
                                    if "Showdown" in event_name or "Breaking Army" in event_name:
                                        delete_duration = 180 * 60 # 180 minutes
                                    elif "Party" in event_name:
                                        delete_duration = 90 * 60 # 90 minutes

                                    try:
                                        await channel.send(
                                            message,
                                            delete_after=delete_duration,
                                            allowed_mentions=discord.AllowedMentions(roles=True)
                                        )
                                        sent_notifs[notif_key] = today_str
                                        # Save config
                                        async with self.config.guild(guild).sent_notifications() as s:
                                            s[notif_key] = today_str
                                    except Exception as e:
                                        print(f"Failed to send notification: {e}")

                        except ValueError:
                            continue

        except Exception as e:
            print(f"Error in event notification task: {e}")

    @event_notification_task.before_loop
    async def before_event_notification_task(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def website_export_task(self):
        """Periodically export schedule to JSON for website"""
        try:
            await self._export_to_json()
        except Exception as e:
            log.error(f"Error in website export task: {e}")

    @website_export_task.before_loop
    async def before_website_export_task(self):
        await self.bot.wait_until_ready()

    async def _export_to_json(self):
        """Export polling data and Discord events to a JSON file for the website"""
        export_path = await self.config.website_export_path()
        if not export_path:
            return

        target_guild_id = await self.config.export_guild_id()
        all_guilds_data = await self.config.all_guilds()
        
        export_data = {
            "last_updated": datetime.utcnow().isoformat(),
            "guilds": {}
        }

        # Ensure emojis directory exists
        export_dir = Path(export_path).parent
        emoji_dir = export_dir / "emojis"
        emoji_dir.mkdir(parents=True, exist_ok=True)

        # Helper to download or save data URL image
        async def save_image(url_or_data, local_path):
            if not url_or_data:
                return False
            
            if str(url_or_data).startswith("data:"):
                try:
                    # Format: data:image/png;base64,iVBORw0KGgo...
                    if "," in str(url_or_data):
                        header, data_str = str(url_or_data).split(",", 1)
                        with open(local_path, "wb") as f:
                            f.write(base64.b64decode(data_str))
                        return True
                except Exception as e:
                    log.error(f"Failed to save data URL image to {local_path}: {e}")
                    return False
            else:
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url_or_data) as resp:
                            if resp.status == 200:
                                with open(local_path, "wb") as f:
                                    f.write(await resp.read())
                                return True
                            else:
                                log.error(f"Failed to download image from {url_or_data}: Status {resp.status}")
                except Exception as e:
                    log.error(f"Failed to download image from {url_or_data} to {local_path}: {e}")
                return False

        # Download favicon if not exists
        favicon_path = export_dir / "favicon.png"
        if not favicon_path.exists():
            # Try to download flower icon in blossom-pink (#fbcfe8)
            # PNG is not reliably available via Iconify API, but SVG is.
            # We save it as favicon.png because index.html expects that filename, 
            # and most modern browsers handle SVG-content-in-PNG-named-file or we can just update HTML.
            favicon_url = "https://api.iconify.design/ri:flower-fill.svg?color=%23fbcfe8"
            await save_image(favicon_url, favicon_path)

        async def get_emoji_url(emoji_str):
            if not emoji_str:
                return ""
            
            # Check if it's a data URL
            if str(emoji_str).startswith("data:image/"):
                # Create a unique filename based on the data
                data_hash = hashlib.md5(str(emoji_str).encode()).hexdigest()
                ext = "png"
                if "image/gif" in str(emoji_str):
                    ext = "gif"
                elif "image/jpeg" in str(emoji_str):
                    ext = "jpg"
                
                filename = f"data_{data_hash}.{ext}"
                local_path = emoji_dir / filename
                if not local_path.exists():
                    await save_image(emoji_str, local_path)
                return f"emojis/{filename}"

            # Check if it's a custom Discord emoji <:name:id> or <a:name:id>
            match = re.search(r'<(a?):([^:]+):(\d+)>', str(emoji_str))
            if match:
                is_animated = bool(match.group(1))
                emoji_id = match.group(3)
                ext = "gif" if is_animated else "png"
                filename = f"{emoji_id}.{ext}"
                local_path = emoji_dir / filename
                
                # Download if not exists
                if not local_path.exists():
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                    await save_image(url, local_path)
                
                return f"emojis/{filename}"
            return emoji_str # Return original if unicode

        for guild_id_str, guild_data in all_guilds_data.items():
            guild_id = int(guild_id_str)
            
            # If a specific guild is configured, skip others
            if target_guild_id and guild_id != target_guild_id:
                continue
                
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            polls = guild_data.get("polls", {})
            if not polls:
                # If no polls, we still might want Discord events
                polling_events = []
            else:
                # Get latest poll
                latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                poll_data = polls[latest_poll_id]
                
                # Use weekly snapshot if available, otherwise calculate live winning times
                winning_times = poll_data.get("weekly_snapshot_winning_times")
                if not winning_times:
                    winning_times = self._calculate_winning_times_weighted(poll_data.get("selections", {}))
                
                # Prepare polling events
                polling_events = []
                prepared_data = self._prepare_calendar_data(winning_times)
                
                for event_name, day_times in prepared_data.items():
                    for day, time_str in day_times.items():
                        base_name = event_name
                        if event_name.endswith(" 1") or event_name.endswith(" 2"):
                            base_name = event_name.rsplit(" ", 1)[0]
                        
                        event_info = self.events.get(base_name, {})
                        emoji_val = await get_emoji_url(event_info.get("emoji", ""))
                        
                        polling_events.append({
                            "name": event_name,
                            "day": day,
                            "time": time_str,
                            "emoji": emoji_val,
                            "color": self._get_hex_color(base_name),
                            "type": "polling"
                        })

            # Get Discord scheduled events
            discord_events = []
            try:
                # scheduled_events is a list of ScheduledEvent objects
                for event in guild.scheduled_events:
                    # Only include upcoming or active events
                    if event.status in [discord.EventStatus.scheduled, discord.EventStatus.active]:
                        discord_events.append({
                            "name": event.name,
                            "start_time": event.start_time.isoformat(),
                            "end_time": event.end_time.isoformat() if event.end_time else None,
                            "location": event.location,
                            "description": event.description,
                            "status": event.status.name,
                            "type": "discord"
                        })
            except Exception as e:
                log.error(f"Failed to fetch Discord events for guild {guild_id}: {e}")

            # Get Breaking Army season data
            ba_season_data = None
            ba_cog = self.bot.get_cog("BreakingArmy")
            if ba_cog:
                try:
                    ba_config = await ba_cog.config.guild(guild).all()
                    ba_season = ba_config.get("season_data", {})
                    if ba_season.get("is_active"):
                        boss_pool = ba_config.get("boss_pool", {})
                        a = ba_season.get("anchors", [])
                        g = ba_season.get("guests", [])
                        if a and g:
                            matrix = [(a[0],g[0]), (a[1],g[1]), (a[2],g[2]), (a[0],g[0]), (a[1],g[3]), (a[2],g[4])]
                            ba_season_data = {
                                "current_week": ba_season.get("current_week", 1),
                                "schedule": []
                            }
                            for i, (b1, b2) in enumerate(matrix):
                                b1_emoji = await get_emoji_url(boss_pool.get(b1, "⚔️"))
                                b2_emoji = await get_emoji_url(boss_pool.get(b2, "⚔️"))
                                ba_season_data["schedule"].append({
                                    "week": i + 1,
                                    "boss1": {"name": b1, "emoji": b1_emoji},
                                    "boss2": {"name": b2, "emoji": b2_emoji},
                                    "is_encore": (i + 1 == 4)
                                })
                except Exception as e:
                    log.error(f"Failed to fetch Breaking Army data: {e}")

            # Calculate filtered member count
            member_count = 0
            online_count = 0
            try:
                # Specific role IDs: @Member and @Friend of the Guild
                target_role_ids = [1439747785644703754, 1452430729115078850]
                
                unique_members = set()
                online_unique_members = set()
                for role_id in target_role_ids:
                    role = guild.get_role(role_id)
                    if role:
                        for member in role.members:
                            unique_members.add(member.id)
                            # Check if member is online (not offline)
                            if member.status != discord.Status.offline:
                                online_unique_members.add(member.id)
                
                count = len(unique_members)
                # Round down to lowest 10
                member_count = (count // 10) * 10
                online_count = len(online_unique_members)
            except Exception as e:
                log.error(f"Failed to calculate member count: {e}")

            export_data["guilds"][guild_id_str] = {
                "name": guild.name,
                "icon_url": str(guild.icon.url) if guild.icon else None,
                "banner_url": str(guild.banner.url) if guild.banner else None,
                "splash_url": str(guild.splash.url) if guild.splash else None,
                "member_count": f"{member_count}+",
                "online_count": online_count,
                "polling_events": polling_events,
                "discord_events": discord_events,
                "ba_season": ba_season_data
            }

            # Export calendar image for this guild (if it's the target guild)
            try:
                # Generate calendar image
                image_buffer = self.calendar_renderer.render_calendar(
                    prepared_data,
                    self.events,
                    self.blocked_times,
                    len(guild_data.get("polls", {}).get(latest_poll_id, {}).get("selections", {})) if polls else 0
                )
                img_path = Path(export_path).parent / "calendar.png"
                with open(img_path, 'wb') as f:
                    f.write(image_buffer.getvalue())
            except Exception as e:
                log.error(f"Failed to export calendar image: {e}")

        # Write to file
        try:
            path = Path(export_path).resolve()
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Failed to export schedule to JSON at {export_path}: {e}")

    def _get_hex_color(self, event_name: str) -> str:
        """Get hex color for an event based on its name"""
        # Strip parentheses for sub-events like "Hero's Realm (Catch-up)"
        base_name = event_name.split('(')[0].strip()
        
        colors = {
            "Hero's Realm": "#5C6BC0",
            "Sword Trial": "#FFCA28",
            "Party": "#e91e63",
            "Breaking Army": "#3498db",
            "Showdown": "#e67e22",
            "Guild War": "#D81B60"
        }
        return colors.get(base_name, "#fbcfe8")

    async def _restore_poll_view(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Restore the poll view to an existing poll message after import

        Args:
            guild: The guild containing the poll
            poll_data: The poll data dictionary
            poll_id: The poll ID
        """
        try:
            channel_id = poll_data.get("channel_id")
            message_id = poll_data.get("message_id")

            if not channel_id or not message_id:
                return

            channel = guild.get_channel(channel_id)
            if not channel:
                # Channel not found - remove the poll from storage
                print(f"Channel {channel_id} for poll {poll_id} not found, removing from storage")
                async with self.config.guild(guild).polls() as polls:
                    if poll_id in polls:
                        del polls[poll_id]
                        print(f"✓ Removed poll {poll_id} from guild {guild.id}")
                return

            message = await channel.fetch_message(message_id)
            if not message:
                return

            # Create a new view for this poll
            view = EventPollView(
                self,
                guild.id,
                poll_data.get("creator_id"),
                self.events,
                self.days_of_week,
                self.blocked_times
            )
            view.poll_id = poll_id

            # Update the message with the new view
            await message.edit(view=view)

        except discord.NotFound:
            # Message not found (404) - remove the poll from storage
            print(f"Poll {poll_id} not found (404), removing from storage")
            async with self.config.guild(guild).polls() as polls:
                if poll_id in polls:
                    del polls[poll_id]
                    print(f"✓ Removed poll {poll_id} from guild {guild.id}")
        except discord.HTTPException as e:
            # Handle rate limiting and other HTTP errors gracefully
            if e.status == 429:  # Rate limited
                log.warning(f"Rate limited when restoring poll {poll_id}, will retry later")
            elif e.status == 404:  # Handle 404 if it comes through as HTTPException
                print(f"Poll {poll_id} not found (404 via HTTPException), removing from storage")
                async with self.config.guild(guild).polls() as polls:
                    if poll_id in polls:
                        del polls[poll_id]
                        print(f"✓ Removed poll {poll_id} from guild {guild.id}")
            else:
                log.error(f"HTTP error when restoring poll {poll_id}: {e}")
        except Exception as e:
            # Silently fail if we can't restore the view
            print(f"Could not restore poll view for poll {poll_id}: {e}")

    async def _restore_calendar_views(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Restore views for calendar messages after bot restart

        Args:
            guild: The guild containing the poll
            poll_data: The poll data dictionary
            poll_id: The poll ID
        """
        from .views import CalendarTimezoneView

        # Restore live calendar views
        calendar_messages = poll_data.get("calendar_messages", [])
        for cal_msg_data in calendar_messages:
            try:
                channel = guild.get_channel(cal_msg_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(cal_msg_data["message_id"])
                    view = CalendarTimezoneView(self, guild.id, poll_id)
                    await message.edit(view=view)
            except Exception as e:
                print(f"Could not restore calendar view for poll {poll_id}: {e}")

        # Restore weekly calendar views
        weekly_calendar_messages = poll_data.get("weekly_calendar_messages", [])
        if weekly_calendar_messages:
            poll_channel_id = poll_data.get("channel_id")
            poll_message_id = poll_data.get("message_id")
            poll_url = f"https://discord.com/channels/{guild.id}/{poll_channel_id}/{poll_message_id}"
            
            for cal_msg_data in weekly_calendar_messages:
                try:
                    channel = guild.get_channel(cal_msg_data["channel_id"])
                    if channel:
                        message = await channel.fetch_message(cal_msg_data["message_id"])
                        view = CalendarTimezoneView(self, guild.id, poll_id, is_weekly=True, poll_url=poll_url)
                        await message.edit(view=view)
                except Exception as e:
                    print(f"Could not restore weekly calendar view for poll {poll_id}: {e}")

    async def _update_poll_message(self, guild_id: int, poll_id: str, poll_data: Dict):
        """Update the poll message embed and related calendar messages"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            channel = guild.get_channel(poll_data["channel_id"])
            if channel:
                message = await channel.fetch_message(poll_data["message_id"])
                updated_embed = await self._create_poll_embed(
                    poll_data["title"],
                    guild_id,
                    poll_id
                )
                updated_embed.set_footer(text="Click the buttons below to set your preferences")
                
                # Recreate the view to update buttons
                view = EventPollView(
                    self,
                    guild_id,
                    poll_data.get("creator_id"),
                    self.events,
                    self.days_of_week,
                    self.blocked_times
                )
                view.poll_id = poll_id
                
                await message.edit(embed=updated_embed, view=view)

            # Update any live calendar messages for this poll
            await self._update_calendar_messages(guild, poll_data, poll_id)

            # Check if we need to create initial weekly snapshot (for first vote)
            await self._check_and_create_initial_snapshot(guild, poll_id)

            # Update any weekly calendar messages for this poll
            await self._update_weekly_calendar_messages(guild, poll_data, poll_id)
            
            # Export to website JSON
            await self._export_to_json()
        except Exception as e:
            log.error(f"Error updating poll message: {e}")

    async def _update_poll_votes(self, ctx: commands.Context, target_poll_id: str, imported_votes: Dict, merge: bool) -> bool:
        """Update votes on an existing poll without recreating the message

        Args:
            ctx: The command context
            target_poll_id: The message ID of the target poll to update
            imported_votes: The votes dictionary from the backup file
            merge: If True, merge with existing votes; if False, replace all votes

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.config.guild(ctx.guild).polls() as polls:
                if target_poll_id not in polls:
                    await ctx.send(f"❌ Poll with ID {target_poll_id} not found in this server!")
                    return False

                poll_data = polls[target_poll_id]

                if merge:
                    # Merge: Add imported votes to existing votes
                    existing_selections = poll_data.get("selections", {})
                    for user_id, user_votes in imported_votes.items():
                        if user_id in existing_selections:
                            # Merge user's votes
                            existing_selections[user_id].update(user_votes)
                        else:
                            # Add new user's votes
                            existing_selections[user_id] = user_votes
                    poll_data["selections"] = existing_selections
                else:
                    # Replace: Completely replace all votes
                    poll_data["selections"] = imported_votes

                # Update the poll in config
                polls[target_poll_id] = poll_data

                # Update the poll message embed to reflect new votes
                try:
                    channel = ctx.guild.get_channel(poll_data.get("channel_id"))
                    if channel:
                        message = await channel.fetch_message(int(target_poll_id))
                        title = poll_data.get("title", "Event Schedule Poll")
                        embed = await self._create_poll_embed(title, ctx.guild.id, target_poll_id)
                        embed.set_footer(text="Click the buttons below to set your preferences")
                        await message.edit(embed=embed)
                except Exception as e:
                    print(f"Could not update poll message embed: {e}")
                    # Continue anyway - votes are saved even if embed update fails

            return True

        except Exception as e:
            print(f"Could not update poll votes: {e}")
            await ctx.send(f"❌ Error updating poll votes: {e}")
            return False

    async def _recreate_poll_message(self, ctx: commands.Context, poll_data: Dict, poll_id: str, current_polls: Dict) -> bool:
        """Recreate a poll message from imported data, replacing any existing active poll

        Args:
            ctx: The command context
            poll_data: The imported poll data dictionary
            poll_id: The poll ID
            current_polls: The current polls dictionary (will be modified)

        Returns:
            True if successful, False otherwise
        """
        try:
            # If there's an existing active poll with this ID, disable its message
            if poll_id in current_polls:
                old_poll_data = current_polls[poll_id]
                try:
                    old_channel = ctx.guild.get_channel(old_poll_data.get("channel_id"))
                    if old_channel:
                        old_message = await old_channel.fetch_message(old_poll_data.get("message_id"))
                        # Disable the old poll message
                        view = discord.ui.View()
                        for item in range(5):
                            button = discord.ui.Button(
                                label="Replaced",
                                style=discord.ButtonStyle.secondary,
                                disabled=True
                            )
                            view.add_item(button)
                        await old_message.edit(view=view)
                except:
                    # If we can't disable the old message, continue anyway
                    pass

            # Create a new poll view
            view = EventPollView(
                self,
                ctx.guild.id,
                poll_data.get("creator_id"),
                self.events,
                self.days_of_week,
                self.blocked_times
            )

            # Create the poll embed
            title = poll_data.get("title", "Event Schedule Poll")
            embed = await self._create_poll_embed(title, ctx.guild.id, poll_id)
            embed.set_footer(text="Click the buttons below to set your preferences")

            # Send the new message
            message = await ctx.send(embed=embed, view=view)

            # Update the poll data with the new message and channel IDs
            poll_data["message_id"] = message.id
            poll_data["channel_id"] = ctx.channel.id

            # Update the poll ID to match the new message ID
            new_poll_id = str(message.id)
            current_polls[new_poll_id] = poll_data

            # Remove old poll ID if it's different
            if poll_id != new_poll_id and poll_id in current_polls:
                del current_polls[poll_id]

            # Set the view's poll ID
            view.poll_id = new_poll_id

            return True

        except Exception as e:
            print(f"Could not recreate poll message for poll {poll_id}: {e}")
            return False

    def _parse_message_id(self, message_input: Union[str, int]) -> Optional[int]:
        """Parse message ID from either an integer or a Discord message link

        Args:
            message_input: Either an integer message ID or a Discord message link

        Returns:
            The message ID as an integer, or None if parsing failed
        """
        # If it's already an int, return it
        if isinstance(message_input, int):
            return message_input

        # If it's a string, try to parse it
        if isinstance(message_input, str):
            # Try to parse as direct integer first
            try:
                return int(message_input)
            except ValueError:
                pass

            # Try to extract from Discord message link
            # Format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
            match = re.search(r'discord\.com/channels/\d+/\d+/(\d+)', message_input)
            if match:
                return int(match.group(1))

        return None

    def _prepare_calendar_data(self, winning_times: Dict) -> Dict[str, Dict[str, str]]:
        """Convert winning_times format to calendar renderer format

        Args:
            winning_times: {event_name: {slot_index: (winner_key, points, all_entries)}}
                where winner_key is (day, time) or ("Daily", time) or ("Fixed", time)

        Returns:
            {event_name: {day: time}} or {event_name_slot: {day: time}} for multi-slot weekly events
        """
        calendar_data = {}

        for event_name, event_info in self.events.items():
            event_slots = winning_times.get(event_name, {})
            # Convert string keys to integers (happens when data is cached/serialized)
            event_slots = {int(k) if isinstance(k, str) else k: v for k, v in event_slots.items()}

            for slot_index, slot_data in event_slots.items():
                # Ensure slot_index is always an integer (handles any edge cases in serialization)
                slot_index = int(slot_index) if isinstance(slot_index, str) else slot_index

                if not slot_data:
                    continue

                winner_key, points, all_entries = slot_data
                winner_day, winner_time = winner_key

                # For multi-slot weekly events, create separate entries with slot number
                if event_info["type"] == "weekly" and event_info["slots"] > 1:
                    # Use event name with slot number (e.g., "Breaking Army 1", "Breaking Army 2")
                    event_key = f"{event_name} {slot_index + 1}"
                    if event_key not in calendar_data:
                        calendar_data[event_key] = {}
                    calendar_data[event_key][winner_day] = winner_time
                elif event_info["type"] == "daily":
                    # Daily events appear on all days
                    if event_name not in calendar_data:
                        calendar_data[event_name] = {}
                    for day in self.days_of_week:
                        calendar_data[event_name][day] = winner_time
                elif event_info["type"] == "fixed_days":
                    # Fixed-day events
                    if event_name not in calendar_data:
                        calendar_data[event_name] = {}
                    if event_info["slots"] > 1:
                        # Multi-slot: map slot_index to the specific day
                        # slot_index corresponds to position in event_info["days"]
                        if slot_index < len(event_info["days"]):
                            actual_day = event_info["days"][slot_index]
                            calendar_data[event_name][actual_day] = winner_time
                    else:
                        # Single slot: appears on all configured days
                        for day in event_info["days"]:
                            calendar_data[event_name][day] = winner_time
                else:
                    # Single-slot weekly events
                    if event_name not in calendar_data:
                        calendar_data[event_name] = {}
                    calendar_data[event_name][winner_day] = winner_time

        return calendar_data

    @commands.group(name="eventpoll")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def eventpoll(self, ctx: commands.Context):
        """Event polling commands"""
        pass

    @eventpoll.command(name="create")
    async def create_poll(self, ctx: commands.Context, *, title: Optional[str] = None):
        """Create a new event scheduling poll

        Example: [p]eventpoll create Weekly Events Schedule
        """
        if not title:
            title = "Event Schedule Poll"

        # Create the poll view
        view = EventPollView(self, ctx.guild.id, ctx.author.id, self.events, self.days_of_week, self.blocked_times)

        # Create the initial embed with calendar view
        embed = await self._create_poll_embed(title, ctx.guild.id, str(0))
        embed.set_footer(text="Click the buttons below to set your preferences")

        message = await ctx.send(embed=embed, view=view)

        # Store poll data
        poll_id = str(message.id)
        async with self.config.guild(ctx.guild).polls() as polls:
            polls[poll_id] = {
                "message_id": message.id,
                "channel_id": ctx.channel.id,
                "creator_id": ctx.author.id,
                "title": title,
                "selections": {},
                "created_at": datetime.utcnow().isoformat()
            }

        view.poll_id = poll_id
        await ctx.tick()

    @eventpoll.command(name="overwrite")
    async def overwrite_poll(self, ctx: commands.Context, message_id: str, *, title: Optional[str] = None):
        """Overwrite an existing bot message with a new event poll

        This will replace the existing message content with a new poll while preserving the message ID.
        The old poll data will be backed up before being replaced.

        Example: [p]eventpoll overwrite 123456789 New Poll Title
        Or: [p]eventpoll overwrite https://discord.com/channels/guild/channel/message New Title
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        if not title:
            title = "Event Schedule Poll"

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        # Try to fetch the message to ensure it exists and is a bot message
        try:
            # Try to find the message in any channel
            message = None
            if poll_id in polls:
                # Poll exists, try to get the message from stored channel
                channel = ctx.guild.get_channel(polls[poll_id]["channel_id"])
                if channel:
                    try:
                        message = await channel.fetch_message(parsed_id)
                    except:
                        pass

            # If not found in stored location, try current channel
            if not message:
                try:
                    message = await ctx.channel.fetch_message(parsed_id)
                except:
                    await ctx.send("Could not find the specified message. Make sure the message ID is correct and the message is in an accessible channel.")
                    return

            # Verify it's a bot message
            if message.author.id != self.bot.user.id:
                await ctx.send("The specified message is not a bot message!")
                return

        except Exception as e:
            await ctx.send(f"Error fetching message: {e}")
            return

        # Backup old poll data if it exists
        if poll_id in polls:
            old_poll_data = polls[poll_id].copy()
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backups_dir / f"overwrite_backup_{ctx.guild.id}_{poll_id}_{timestamp}.json"

            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "guild_id": ctx.guild.id,
                "poll_id": poll_id,
                "old_poll_data": old_poll_data
            }

            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            await ctx.send(f"Old poll data backed up to: `{backup_file.name}`")

        # Create the new poll view
        view = EventPollView(self, ctx.guild.id, ctx.author.id, self.events, self.days_of_week, self.blocked_times)

        # Create the initial embed
        embed = await self._create_poll_embed(title, ctx.guild.id, str(0))
        embed.set_footer(text="Click the buttons below to set your preferences")

        # Update the existing message
        await message.edit(embed=embed, view=view)

        # Update or create poll data
        async with self.config.guild(ctx.guild).polls() as polls:
            polls[poll_id] = {
                "message_id": message.id,
                "channel_id": message.channel.id,
                "creator_id": ctx.author.id,
                "title": title,
                "selections": {},
                "created_at": datetime.utcnow().isoformat()
            }

        view.poll_id = poll_id
        await ctx.send(f"Successfully overwrote message with new poll: {message.jump_url}")

    @eventpoll.command(name="updateembed")
    async def update_embed(self, ctx: commands.Context, message_id: str):
        """Update an existing poll embed without altering poll results

        This refreshes the embed text and appearance while preserving all votes.
        Useful for updating descriptions or fixing formatting.

        Example: [p]eventpoll updateembed 123456789
        Or: [p]eventpoll updateembed https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]
        title = poll_data["title"]

        # Try to fetch the message
        try:
            channel = ctx.guild.get_channel(poll_data["channel_id"])
            if not channel:
                await ctx.send("Could not find the poll's channel!")
                return

            message = await channel.fetch_message(parsed_id)

            # Verify it's a bot message
            if message.author.id != self.bot.user.id:
                await ctx.send("The specified message is not a bot message!")
                return

        except Exception as e:
            await ctx.send(f"Error fetching message: {e}")
            return

        # Create the updated poll view
        view = EventPollView(self, ctx.guild.id, poll_data["creator_id"], self.events, self.days_of_week, self.blocked_times)
        view.poll_id = poll_id

        # Create the updated embed (this will use the new text)
        embed = await self._create_poll_embed(title, ctx.guild.id, poll_id)

        # Update the existing message
        await message.edit(embed=embed, view=view)

        await ctx.send(f"✅ Successfully updated poll embed: {message.jump_url}")

    @eventpoll.command(name="updateall")
    @commands.is_owner()
    async def update_all_polls(self, ctx: commands.Context):
        """Force update all active poll embeds across all guilds

        This refreshes the embed text and appearance for every poll in the database.
        Useful after deploying code changes that affect embed formatting.
        """
        await ctx.send("🔄 Starting global poll update... This may take a while.")
        
        all_guilds = await self.config.all_guilds()
        total_polls = 0
        updated_polls = 0
        
        for guild_id, guild_data in all_guilds.items():
            polls = guild_data.get("polls", {})
            total_polls += len(polls)
            
            for poll_id, poll_data in polls.items():
                try:
                    await self._update_poll_message(int(guild_id), poll_id, poll_data)
                    updated_polls += 1
                    # Add small delay to avoid rate limiting
                    import asyncio
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.error(f"Failed to update poll {poll_id} in guild {guild_id}: {e}")
        
        await ctx.send(f"✅ Global update complete! Updated {updated_polls}/{total_polls} polls.")

    @eventpoll.command(name="results")
    async def show_results(self, ctx: commands.Context, message_id: str):
        """Show the results of a poll

        Example: [p]eventpoll results 123456789
        Or: [p]eventpoll results https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]
        selections = poll_data.get("selections", {})

        if not selections:
            await ctx.send("No one has voted yet!")
            return

        # Create results embed
        embed = discord.Embed(
            title=f"📊 Results: {poll_data['title']}",
            color=self._get_embed_color(ctx.guild)
        )

        # Organize results by event
        for event_name in self.events.keys():
            event_results = {}
            event_info = self.events[event_name]

            for user_id, user_selections in selections.items():
                if event_name in user_selections:
                    selection = user_selections[event_name]

                    # Handle multi-slot events (stored as list)
                    if isinstance(selection, list):
                        for slot_index, slot_data in enumerate(selection):
                            if slot_data:  # Slot might be None if not yet selected
                                # Format the selection string
                                if event_info["type"] == "daily":
                                    key = f"Slot {slot_index + 1}: {slot_data['time']}"
                                elif event_info["type"] == "fixed_days":
                                    days_str = ", ".join([d[:3] for d in event_info["days"]])
                                    key = f"Slot {slot_index + 1}: {slot_data['time']} ({days_str})"
                                else:
                                    key = f"Slot {slot_index + 1}: {slot_data['day']} at {slot_data['time']}"

                                if key not in event_results:
                                    event_results[key] = []
                                event_results[key].append(f"<@{user_id}>")
                    else:
                        # Single-slot event (stored as dict)
                        # Format the selection string
                        if isinstance(selection, str):
                            time_val = selection
                            day_val = "Unknown"
                        else:
                            time_val = selection["time"]
                            day_val = selection.get("day", "Unknown")

                        if event_info["type"] == "daily":
                            key = time_val
                        elif event_info["type"] == "fixed_days":
                            days_str = ", ".join([d[:3] for d in event_info["days"]])
                            key = f"{time_val} ({days_str})"
                        else:
                            key = f"{day_val} at {time_val}"

                        if key not in event_results:
                            event_results[key] = []
                        event_results[key].append(f"<@{user_id}>")

            # Add to embed
            if event_results or event_info["type"] == "locked":
                if event_info["type"] == "locked":
                    day_val = event_info["days"][0]
                    time_val = event_info["fixed_time"]
                    field_value = f"**{day_val[:3]} {time_val}**: *Fixed time*\n"
                else:
                    field_value = ""
                    for selection, users in sorted(event_results.items()):
                        field_value += f"**{selection}**: {', '.join(users)}\n"

                emoji = self.events[event_name]["emoji"]
                embed.add_field(
                    name=f"{emoji} {event_name}",
                    value=field_value or "No votes",
                    inline=False
                )

        embed.set_footer(text=f"Total voters: {len(selections)}")
        await ctx.send(embed=embed)

    @eventpoll.command(name="end")
    async def end_poll(self, ctx: commands.Context, message_id: str):
        """End a poll and remove it from the database

        Example: [p]eventpoll end 123456789
        Or: [p]eventpoll end https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id not in polls:
                await ctx.send("Poll not found!")
                return

            poll_data = polls[poll_id]

            # Check permissions
            if ctx.author.id != poll_data["creator_id"] and not ctx.author.guild_permissions.manage_guild:
                await ctx.send("Only the poll creator or admins can end this poll!")
                return

            del polls[poll_id]

        await ctx.send("Poll ended and removed from database.")

        # Try to edit the original message to disable buttons
        try:
            channel = ctx.guild.get_channel(poll_data["channel_id"])
            if channel:
                message = await channel.fetch_message(poll_data["message_id"])
                view = discord.ui.View()
                for item in range(5):
                    button = discord.ui.Button(
                        label="Ended",
                        style=discord.ButtonStyle.secondary,
                        disabled=True
                    )
                    view.add_item(button)
                await message.edit(view=view)
        except:
            pass

    @eventpoll.command(name="clear")
    async def clear_user_votes(self, ctx: commands.Context, message_id: str, user: discord.Member):
        """Clear a user's votes from a poll

        Example: [p]eventpoll clear 123456789 @user
        Or: [p]eventpoll clear https://discord.com/channels/guild/channel/message @user
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id not in polls:
                await ctx.send("Poll not found!")
                return

            poll_data = polls[poll_id]
            user_id_str = str(user.id)

            if user_id_str in poll_data["selections"]:
                del poll_data["selections"][user_id_str]
                await ctx.send(f"Cleared votes for {user.mention}")
            else:
                await ctx.send(f"{user.mention} hasn't voted in this poll.")

    @eventpoll.command(name="calendar")
    async def post_calendar(self, ctx: commands.Context, message_id: str):
        """Post an auto-updating calendar view for a poll

        Example: [p]eventpoll calendar 123456789
        Or: [p]eventpoll calendar https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Create calendar embed and image
        embed, calendar_file, view = await self._create_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Send the calendar message with image and timezone button
        calendar_msg = await ctx.send(embed=embed, file=calendar_file, view=view)

        # Store calendar message ID in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                if "calendar_messages" not in polls[poll_id]:
                    polls[poll_id]["calendar_messages"] = []
                polls[poll_id]["calendar_messages"].append({
                    "message_id": calendar_msg.id,
                    "channel_id": ctx.channel.id
                })

        await ctx.tick()

    @eventpoll.command(name="weeklycalendar")
    async def post_weekly_calendar(self, ctx: commands.Context, message_id: str):
        """Post a weekly calendar view for a poll (updates only on Monday at 10 AM)

        Example: [p]eventpoll weeklycalendar 123456789
        Or: [p]eventpoll weeklycalendar https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Create weekly calendar embed and image
        embed, calendar_file, view, winning_times = await self._create_weekly_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Send the weekly calendar message with image and timezone button
        calendar_msg = await ctx.send(embed=embed, file=calendar_file, view=view)

        # Store weekly calendar message ID and snapshot in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                # Store the winning_times snapshot for timezone conversions
                polls[poll_id]["weekly_snapshot_winning_times"] = winning_times

                if "weekly_calendar_messages" not in polls[poll_id]:
                    polls[poll_id]["weekly_calendar_messages"] = []
                polls[poll_id]["weekly_calendar_messages"].append({
                    "message_id": calendar_msg.id,
                    "channel_id": ctx.channel.id
                })

        await ctx.tick()

    @eventpoll.command(name="postresults")
    async def post_results(self, ctx: commands.Context, message_id: str):
        """Post an auto-updating results embed for a poll (updates every Monday at 10 AM)

        Example: [p]eventpoll postresults 123456789
        Or: [p]eventpoll postresults https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Create results embed
        embed = await self._create_results_embed(poll_data, ctx.guild.id, poll_id)

        # Send the results message
        results_msg = await ctx.send(embed=embed)

        # Store results message ID in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                if "results_messages" not in polls[poll_id]:
                    polls[poll_id]["results_messages"] = []
                polls[poll_id]["results_messages"].append({
                    "message_id": results_msg.id,
                    "channel_id": ctx.channel.id
                })

        await ctx.tick()

    @eventpoll.command(name="overwritecalendar")
    async def overwrite_calendar(self, ctx: commands.Context, message_id_to_overwrite: str, poll_message_id: str):
        """Overwrite an existing bot message with a calendar embed

        Example: [p]eventpoll overwritecalendar 987654321 123456789
        Or: [p]eventpoll overwritecalendar <message_link> <poll_link>
        """
        # Parse message IDs
        target_msg_id = self._parse_message_id(message_id_to_overwrite)
        poll_msg_id = self._parse_message_id(poll_message_id)

        if target_msg_id is None or poll_msg_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(poll_msg_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Try to fetch the target message
        try:
            message = await ctx.channel.fetch_message(target_msg_id)

            # Verify it's a bot message
            if message.author.id != self.bot.user.id:
                await ctx.send("The specified message is not a bot message!")
                return

        except Exception as e:
            await ctx.send(f"Error fetching message: {e}")
            return

        # Create calendar embed and image
        embed, calendar_file, view = await self._create_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Update the message with timezone button
        await message.edit(embed=embed, attachments=[calendar_file], view=view)

        # Store calendar message ID in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                if "calendar_messages" not in polls[poll_id]:
                    polls[poll_id]["calendar_messages"] = []

                # Check if this message is already tracked
                calendar_messages = polls[poll_id]["calendar_messages"]
                if not any(msg["message_id"] == target_msg_id for msg in calendar_messages):
                    polls[poll_id]["calendar_messages"].append({
                        "message_id": target_msg_id,
                        "channel_id": ctx.channel.id
                    })

        await ctx.send(f"✅ Successfully overwrote message with calendar: {message.jump_url}")

    @eventpoll.command(name="overwriteweeklycalendar")
    async def overwrite_weekly_calendar(self, ctx: commands.Context, message_id_to_overwrite: str, poll_message_id: str):
        """Overwrite an existing bot message with a weekly calendar embed

        Example: [p]eventpoll overwriteweeklycalendar 987654321 123456789
        Or: [p]eventpoll overwriteweeklycalendar <message_link> <poll_link>
        """
        # Parse message IDs
        target_msg_id = self._parse_message_id(message_id_to_overwrite)
        poll_msg_id = self._parse_message_id(poll_message_id)

        if target_msg_id is None or poll_msg_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(poll_msg_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Try to fetch the target message
        try:
            message = await ctx.channel.fetch_message(target_msg_id)

            # Verify it's a bot message
            if message.author.id != self.bot.user.id:
                await ctx.send("The specified message is not a bot message!")
                return

        except Exception as e:
            await ctx.send(f"Error fetching message: {e}")
            return

        # Create weekly calendar embed and image
        embed, calendar_file, view, winning_times = await self._create_weekly_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Update the message with timezone button
        await message.edit(embed=embed, attachments=[calendar_file], view=view)

        # Store weekly calendar message ID and snapshot in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                # Store the winning_times snapshot for timezone conversions
                polls[poll_id]["weekly_snapshot_winning_times"] = winning_times

                if "weekly_calendar_messages" not in polls[poll_id]:
                    polls[poll_id]["weekly_calendar_messages"] = []

                # Check if this message is already tracked
                weekly_calendar_messages = polls[poll_id]["weekly_calendar_messages"]
                if not any(msg["message_id"] == target_msg_id for msg in weekly_calendar_messages):
                    polls[poll_id]["weekly_calendar_messages"].append({
                        "message_id": target_msg_id,
                        "channel_id": ctx.channel.id
                    })

        await ctx.send(f"✅ Successfully overwrote message with weekly calendar: {message.jump_url}")

    @eventpoll.command(name="updateweeklysnapshot")
    async def update_weekly_snapshot(self, ctx: commands.Context, message_id: str):
        """Manually update the weekly calendar snapshot with current poll results

        This updates the cached winning times used by weekly calendars. Use this if
        the automatic Monday 10 AM update didn't trigger or you want to update it manually.

        Example: [p]eventpoll updateweeklysnapshot 123456789
        Or: [p]eventpoll updateweeklysnapshot https://discord.com/channels/guild/channel/message
        """
        parsed_id = self._parse_message_id(message_id)
        if parsed_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(parsed_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Check if there are any weekly calendar messages for this poll
        weekly_calendar_messages = poll_data.get("weekly_calendar_messages", [])
        if not weekly_calendar_messages:
            await ctx.send("⚠️ This poll has no weekly calendar messages. Use `[p]eventpoll weeklycalendar` first.")
            return

        # Calculate current winning times from live selections
        selections = poll_data.get("selections", {})
        winning_times = self._calculate_winning_times_weighted(selections)

        # Store the new snapshot
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                polls[poll_id]["weekly_snapshot_winning_times"] = winning_times

        # Update all weekly calendar message images
        try:
            await self._update_weekly_calendar_messages(ctx.guild, poll_data, poll_id)
            await ctx.send(f"✅ Successfully updated weekly calendar snapshot with current poll results! All weekly calendar images have been refreshed.")
        except Exception as e:
            await ctx.send(f"✅ Snapshot updated, but failed to update some calendar images: {e}")

    @eventpoll.command(name="overwriteresults")
    async def overwrite_results(self, ctx: commands.Context, message_id_to_overwrite: str, poll_message_id: str):
        """Overwrite an existing bot message with a results embed

        Example: [p]eventpoll overwriteresults 987654321 123456789
        Or: [p]eventpoll overwriteresults <message_link> <poll_link>
        """
        # Parse message IDs
        target_msg_id = self._parse_message_id(message_id_to_overwrite)
        poll_msg_id = self._parse_message_id(poll_message_id)

        if target_msg_id is None or poll_msg_id is None:
            await ctx.send("Invalid message ID or link!")
            return

        poll_id = str(poll_msg_id)
        polls = await self.config.guild(ctx.guild).polls()

        if poll_id not in polls:
            await ctx.send("Poll not found!")
            return

        poll_data = polls[poll_id]

        # Try to fetch the target message
        try:
            message = await ctx.channel.fetch_message(target_msg_id)

            # Verify it's a bot message
            if message.author.id != self.bot.user.id:
                await ctx.send("The specified message is not a bot message!")
                return

        except Exception as e:
            await ctx.send(f"Error fetching message: {e}")
            return

        # Create results embed
        embed = await self._create_results_embed(poll_data, ctx.guild.id, poll_id)

        # Update the message
        await message.edit(embed=embed)

        # Store results message ID in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
                if "results_messages" not in polls[poll_id]:
                    polls[poll_id]["results_messages"] = []

                # Check if this message is already tracked
                results_messages = polls[poll_id]["results_messages"]
                if not any(msg["message_id"] == target_msg_id for msg in results_messages):
                    polls[poll_id]["results_messages"].append({
                        "message_id": target_msg_id,
                        "channel_id": ctx.channel.id
                    })

        await ctx.send(f"✅ Successfully overwrote message with results embed! This message will now be auto-updated.")

    @eventpoll.command(name="setchannel")
    async def eventpoll_setchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel for event notifications. Leave empty to disable."""
        if channel:
            await self.config.guild(ctx.guild).notification_channel_id.set(channel.id)
            await ctx.send(f"✅ Event notifications will be sent to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).notification_channel_id.set(None)
            await ctx.send("✅ Event notifications disabled")

    @eventpoll.command(name="setmessage")
    async def eventpoll_setmessage(self, ctx: commands.Context, option: Optional[str] = None, *, message: str = None):
        """Set the notification message.
        
        You can set a specific message for an event (e.g. Party) or a default message for all events.
        
        Usage:
        [p]eventpoll setmessage Party {event} is starting... (Set specifically for Party)
        [p]eventpoll setmessage {event} is starting... (Set default for all events)
        
        Available placeholders:
        {event} - Event name
        {timestamp} - Discord timestamp of the event start
        {time_str} - Time string (e.g. 20:00)
        
        Leave empty to reset default message.
        To clear a specific event message, use: [p]eventpoll setmessage "Event Name"
        """
        # Check if the first argument matches a known event
        target_event = None
        full_message = ""
        
        if option:
            # Check exact match or case-insensitive match against events
            for event_name in self.events:
                if option.lower() == event_name.lower():
                    target_event = event_name
                    break
            
            if not target_event:
                # Not an event name, treat as part of the message
                full_message = option
                if message:
                    full_message += " " + message
            else:
                # It is an event name, message is the rest
                full_message = message or ""
        
        if target_event:
            # Setting an event-specific message
            async with self.config.guild(ctx.guild).notification_messages() as messages:
                if full_message:
                    messages[target_event] = full_message
                    await ctx.send(f"✅ Notification message for **{target_event}** set to:\n{full_message}")
                else:
                    if target_event in messages:
                        del messages[target_event]
                    await ctx.send(f"✅ Notification message for **{target_event}** reset to default")
        else:
            # Setting the default message
            if full_message:
                await self.config.guild(ctx.guild).notification_message.set(full_message)
                await ctx.send(f"✅ Default notification message set to:\n{full_message}")
            else:
                await self.config.guild(ctx.guild).notification_message.clear()
                await ctx.send("✅ Default notification message reset to default")

    @eventpoll.command(name="setrole")
    async def eventpoll_setrole(self, ctx: commands.Context, event_name: str, role: discord.Role = None):
        """Set a role to be mentioned for a specific event.
        
        Usage: [p]eventpoll setrole "Event Name" @Role
        Example: [p]eventpoll setrole "Breaking Army" @BreakingArmy
        
        Leave role empty to clear the role for that event.
        """
        if event_name not in self.events:
            await ctx.send(f"❌ Invalid event name. Available events: {', '.join(self.events.keys())}")
            return

        async with self.config.guild(ctx.guild).event_roles() as roles:
            if role:
                roles[event_name] = role.id
                await ctx.send(f"✅ Set role for **{event_name}** to {role.mention}")
            else:
                if event_name in roles:
                    del roles[event_name]
                await ctx.send(f"✅ Cleared role for **{event_name}**")

    @eventpoll.command(name="settings")
    async def eventpoll_settings(self, ctx: commands.Context):
        """View current eventpoll configuration settings."""
        guild_data = await self.config.guild(ctx.guild).all()
        
        channel_id = guild_data.get("notification_channel_id")
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        
        notif_msg = guild_data.get("notification_message")
        custom_msgs = guild_data.get("notification_messages", {})
        event_roles = guild_data.get("event_roles", {})
        
        embed = discord.Embed(
            title="⚙️ EventPoll Settings",
            color=self._get_embed_color(ctx.guild)
        )
        
        embed.add_field(
            name="Notification Channel",
            value=channel.mention if channel else "Disabled",
            inline=False
        )
        
        embed.add_field(
            name="Default Notification Message",
            value=f"```\n{notif_msg}\n```",
            inline=False
        )
        
        if custom_msgs:
            custom_msg_text = ""
            for event, msg in custom_msgs.items():
                custom_msg_text += f"**{event}**: {msg}\n"
            embed.add_field(name="Custom Event Messages", value=custom_msg_text, inline=False)
            
        if event_roles:
            role_text = ""
            for event, role_id in event_roles.items():
                role = ctx.guild.get_role(role_id)
                role_text += f"**{event}**: {role.mention if role else f'Unknown ({role_id})'}\n"
            embed.add_field(name="Event Roles", value=role_text, inline=False)
            
        await ctx.send(embed=embed)

    @eventpoll.command(name="testnotif")
    async def eventpoll_testnotif(self, ctx: commands.Context, *, event_name: str):
        """Test an event notification message in the current channel.
        
        Example: [p]eventpoll testnotif Breaking Army
        """
        # 1. Verify Event Name
        matched_event = None
        for e in self.events:
            if event_name.lower() == e.lower():
                matched_event = e
                break
        
        if not matched_event:
            return await ctx.send(f"❌ Invalid event name. Available: {', '.join(self.events.keys())}")

        # 2. Get Message Template
        guild_data = await self.config.guild(ctx.guild).all()
        custom_msgs = guild_data.get("notification_messages", {})
        msg_tmpl = custom_msgs.get(matched_event)
        if not msg_tmpl:
            msg_tmpl = guild_data.get("notification_message", "{event} is starting at {timestamp}!")

        # 3. Variable Replacement
        # Timestamp (Current Time)
        from datetime import timezone
        server_tz = timezone(timedelta(hours=1))
        now = datetime.now(server_tz)
        ts = int(now.timestamp())
        discord_ts = f"<t:{ts}:R>"
        
        # Event Display (Role or Bold)
        event_roles = guild_data.get("event_roles", {})
        role_id = event_roles.get(matched_event)
        event_display = f"<@&{role_id}>" if role_id else f"**{matched_event}**"

        message = msg_tmpl.replace("{event}", event_display)\
                          .replace("{timestamp}", discord_ts)\
                          .replace("{time_str}", f"{now.hour:02d}:{now.minute:02d}")

        # Boss Variable
        if "{boss}" in message and "Breaking Army" in matched_event:
            ba_cog = self.bot.get_cog("BreakingArmy")
            if ba_cog:
                boss_info = await ba_cog._get_current_boss_info(ctx.guild)
                message = message.replace("{boss}", boss_info or "*(No Active Run)*")
            else:
                message = message.replace("{boss}", "*(BreakingArmy Cog Not Found)*")

        # 4. Send
        await ctx.send(f"🧪 **Test Notification for {matched_event}:**\n---\n{message}", allowed_mentions=discord.AllowedMentions(roles=True))

    @eventpoll.command(name="export")
    async def export_backup(self, ctx: commands.Context):
        """Manually create a backup of the latest active poll

        This creates an immediate backup file of the most recent poll.

        Example: [p]eventpoll export
        """
        try:
            all_guilds = await self.config.all_guilds()

            # Create timestamp for backup filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backups_dir / f"manual_backup_{timestamp}.json"

            # Prepare backup data
            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "type": "manual",
                "guilds": {}
            }

            # Collect only the latest poll from each guild
            for guild_id, guild_data in all_guilds.items():
                polls = guild_data.get("polls", {})
                if polls:
                    # Find the latest poll (highest message_id = most recent)
                    latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
                    backup_data["guilds"][str(guild_id)] = {
                        "polls": {
                            latest_poll_id: polls[latest_poll_id]
                        }
                    }

            # Write backup file
            if backup_data["guilds"]:
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)

                await ctx.send(f"✅ Backup created successfully: `{backup_file.name}`\nLocation: `{backup_file}`")
            else:
                await ctx.send("No poll data to backup!")

        except Exception as e:
            await ctx.send(f"❌ Error creating backup: {e}")

    @eventpoll.command(name="import")
    async def import_backup(self, ctx: commands.Context, backup_filename: str, target_poll_id: str, merge: str = "false", source_poll_id: Optional[str] = None):
        """Import votes from a backup file into an existing poll

        This command imports VOTES (not entire polls) from a backup file.
        By default, it consolidates votes from ALL polls in the backup.
        Optionally specify source_poll_id to import from a specific poll.
        Use merge="true" to merge imported votes with existing votes.
        Use merge="false" (default) to replace all existing votes.

        Example: [p]eventpoll import backup.json 123456789 false
        Example: [p]eventpoll import backup.json 123456789 true 987654321
        """
        # Parse merge parameter
        merge_bool = merge.lower() in ("true", "yes", "1", "y")
        try:
            # Find the backup file
            backup_file = self.backups_dir / backup_filename

            if not backup_file.exists():
                # Try to find it with pattern matching
                matching_files = list(self.backups_dir.glob(f"*{backup_filename}*"))
                if matching_files:
                    backup_file = matching_files[0]
                else:
                    await ctx.send(f"❌ Backup file not found: `{backup_filename}`\n\nAvailable backups:")
                    backup_files = sorted(self.backups_dir.glob("*.json"), reverse=True)
                    if backup_files:
                        file_list = "\n".join([f"- {f.name}" for f in backup_files[:10]])
                        await ctx.send(f"```\n{file_list}\n```")
                    else:
                        await ctx.send("No backup files found!")
                    return

            # Read backup file
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            # Validate backup data
            if "guilds" not in backup_data:
                await ctx.send("❌ Invalid backup file format!")
                return

            # Consolidate votes from backup polls
            all_imported_votes = {}
            polls_processed = 0
            source_description = ""

            for guild_id_str, guild_backup in backup_data["guilds"].items():
                backup_polls = guild_backup.get("polls", {})

                if not backup_polls:
                    continue

                if source_poll_id:
                    # Import from specific poll only
                    found_poll = None

                    # Check if source_poll_id exists directly
                    if source_poll_id in backup_polls:
                        found_poll = backup_polls[source_poll_id]
                    else:
                        # Check if any poll has matching message_id
                        for backup_pid, backup_pdata in backup_polls.items():
                            if str(backup_pdata.get("message_id")) == source_poll_id:
                                found_poll = backup_pdata
                                break

                    if not found_poll:
                        await ctx.send(f"❌ Source poll ID {source_poll_id} not found in backup file!\n\n"
                                      "Available polls in backup:")
                        poll_list = "\n".join([
                            f"- Poll ID: {pid} (Message: {pdata.get('message_id')}, Title: {pdata.get('title', 'N/A')})"
                            for pid, pdata in backup_polls.items()
                        ])
                        await ctx.send(f"```\n{poll_list}\n```")
                        return

                    # Get votes from specific poll
                    poll_votes = found_poll.get("selections", {})
                    for user_id, user_votes in poll_votes.items():
                        if user_id not in all_imported_votes:
                            all_imported_votes[user_id] = {}
                        all_imported_votes[user_id].update(user_votes)
                    polls_processed = 1
                    source_description = f"poll {source_poll_id}"
                else:
                    # No source specified - use latest poll (or all polls if multiple)
                    if len(backup_polls) == 1:
                        # Only one poll in backup - use it
                        poll_id, poll_data = list(backup_polls.items())[0]
                        poll_votes = poll_data.get("selections", {})
                        for user_id, user_votes in poll_votes.items():
                            if user_id not in all_imported_votes:
                                all_imported_votes[user_id] = {}
                            all_imported_votes[user_id].update(user_votes)
                        polls_processed = 1
                        source_description = f"poll {poll_id}"
                    else:
                        # Multiple polls - use the latest one (highest message_id)
                        latest_poll_id = max(backup_polls.keys(), key=lambda pid: int(pid))
                        poll_data = backup_polls[latest_poll_id]
                        poll_votes = poll_data.get("selections", {})
                        for user_id, user_votes in poll_votes.items():
                            if user_id not in all_imported_votes:
                                all_imported_votes[user_id] = {}
                            all_imported_votes[user_id].update(user_votes)
                        polls_processed = 1
                        source_description = f"latest poll {latest_poll_id} (from {len(backup_polls)} polls in backup)"

            vote_count = len(all_imported_votes)

            if vote_count == 0:
                await ctx.send(f"⚠️ No votes found in the backup!")
                return

            # Import the consolidated votes into the target poll
            success = await self._update_poll_votes(ctx, target_poll_id, all_imported_votes, merge_bool)

            if success:
                backup_timestamp = backup_data.get("timestamp", "unknown")
                mode_text = "merged with" if merge_bool else "replaced in"
                await ctx.send(
                    f"✅ Successfully {mode_text} poll {target_poll_id}!\n"
                    f"- Backup timestamp: {backup_timestamp}\n"
                    f"- Source: {source_description}\n"
                    f"- Users with votes imported: {vote_count}\n"
                    f"- Mode: {'Merge' if merge_bool else 'Replace'}"
                )

        except json.JSONDecodeError:
            await ctx.send("❌ Invalid JSON format in backup file!")
        except Exception as e:
            await ctx.send(f"❌ Error importing backup: {e}")

    @eventpoll.command(name="test")
    async def test_backup_restore(self, ctx: commands.Context):
        """Test the export/import functionality

        This command tests the export and import workflow:
        1. Exports the latest poll to a test backup
        2. Imports it back to verify the process works
        3. Reports the results

        Example: [p]eventpoll test
        """
        try:
            # Get current polls
            polls = await self.config.guild(ctx.guild).polls()

            if not polls:
                await ctx.send("❌ No polls found to test with! Create a poll first.")
                return

            # Find the latest poll
            latest_poll_id = max(polls.keys(), key=lambda pid: int(pid))
            latest_poll = polls[latest_poll_id]

            await ctx.send(f"🧪 Starting test with latest poll (ID: {latest_poll_id})...")

            # Step 1: Create a test export
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            test_backup_file = self.backups_dir / f"test_backup_{timestamp}.json"

            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "type": "test",
                "guilds": {
                    str(ctx.guild.id): {
                        "polls": {
                            latest_poll_id: latest_poll
                        }
                    }
                }
            }

            with open(test_backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            vote_count_before = len(latest_poll.get("selections", {}))
            await ctx.send(f"✅ Step 1: Exported poll with {vote_count_before} users to `{test_backup_file.name}`")

            # Step 2: Test import (merge mode to avoid data loss)
            imported_votes = latest_poll.get("selections", {})
            success = await self._update_poll_votes(ctx, latest_poll_id, imported_votes, merge=True)

            if not success:
                await ctx.send("❌ Step 2: Import test FAILED!")
                return

            # Step 3: Verify the import
            polls_after = await self.config.guild(ctx.guild).polls()
            poll_after = polls_after.get(latest_poll_id)

            if not poll_after:
                await ctx.send("❌ Step 3: Verification FAILED - Poll not found after import!")
                return

            vote_count_after = len(poll_after.get("selections", {}))

            await ctx.send(
                f"✅ **Test PASSED!**\n"
                f"- Poll ID: {latest_poll_id}\n"
                f"- Votes before: {vote_count_before}\n"
                f"- Votes after: {vote_count_after}\n"
                f"- Test backup: `{test_backup_file.name}`\n\n"
                f"Export and import are working correctly! ✨"
            )

            # Clean up test backup
            test_backup_file.unlink()
            await ctx.send(f"🗑️ Cleaned up test backup file.")

        except Exception as e:
            await ctx.send(f"❌ Error during test: {e}")

    @eventpoll.command(name="listbackups")
    async def list_backups(self, ctx: commands.Context):
        """List all available backup files

        Example: [p]eventpoll listbackups
        """
        try:
            backup_files = sorted(self.backups_dir.glob("*.json"), reverse=True)

            if not backup_files:
                await ctx.send("No backup files found!")
                return

            # Group backups by type
            daily_backups = [f for f in backup_files if f.name.startswith("poll_backup_")]
            manual_backups = [f for f in backup_files if f.name.startswith("manual_backup_")]
            overwrite_backups = [f for f in backup_files if f.name.startswith("overwrite_backup_")]

            embed = discord.Embed(
                title="📦 Available Backups",
                color=self._get_embed_color(ctx.guild)
            )

            if daily_backups:
                daily_list = "\n".join([f"- `{f.name}` ({self._format_file_size(f)})" for f in daily_backups[:5]])
                embed.add_field(
                    name=f"🕐 Daily Backups (Last 5 of {len(daily_backups)})",
                    value=daily_list,
                    inline=False
                )

            if manual_backups:
                manual_list = "\n".join([f"- `{f.name}` ({self._format_file_size(f)})" for f in manual_backups[:5]])
                embed.add_field(
                    name=f"📝 Manual Backups (Last 5 of {len(manual_backups)})",
                    value=manual_list,
                    inline=False
                )

            if overwrite_backups:
                overwrite_list = "\n".join([f"- `{f.name}` ({self._format_file_size(f)})" for f in overwrite_backups[:5]])
                embed.add_field(
                    name=f"🔄 Overwrite Backups (Last 5 of {len(overwrite_backups)})",
                    value=overwrite_list,
                    inline=False
                )

            embed.set_footer(text=f"Total backups: {len(backup_files)} | Location: {self.backups_dir}")

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Error listing backups: {e}")

    @eventpoll.command(name="exportpath")
    @commands.is_owner()
    async def set_export_path(self, ctx: commands.Context, path: str):
        """Set the path to export the schedule JSON file for the website.
        
        Example: [p]eventpoll exportpath /home/zoe/Claude/blossom.ink/schedule.json
        """
        await self.config.website_export_path.set(path)
        await self._export_to_json()
        await ctx.send(f"✅ Website export path set to: `{path}`. Initial export complete.")

    @eventpoll.command(name="exportguild")
    @commands.is_owner()
    async def set_export_guild(self, ctx: commands.Context, guild_id: Optional[int] = None):
        """Set the guild ID to export for the website. Leave empty to export all guilds.
        """
        if guild_id:
            await self.config.export_guild_id.set(guild_id)
            await ctx.send(f"✅ Website export guild set to: `{guild_id}`")
        else:
            await self.config.export_guild_id.set(None)
            await ctx.send("✅ Website export guild reset to all guilds")
        await self._export_to_json()

    @eventpoll.command(name="forceexport")
    @commands.is_owner()
    async def force_export(self, ctx: commands.Context):
        """Force an immediate export of the schedule JSON."""
        await self._export_to_json()
        await ctx.send("✅ Schedule JSON exported.")

    def _format_file_size(self, file_path: Path) -> str:
        """Format file size in human-readable format"""
        size = file_path.stat().st_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    async def _create_calendar_embed(self, poll_data: Dict, guild_id: int, poll_id: str) -> Tuple[discord.Embed, discord.File, discord.ui.View]:
        """Create a live calendar embed with image and poll link (updates on every vote)

        Returns:
            Tuple of (embed, file, view) where file is the calendar image and view contains timezone button
        """
        from .views import CalendarTimezoneView

        title = poll_data["title"]
        channel_id = poll_data["channel_id"]
        message_id = poll_data["message_id"]

        # Get guild for color
        guild = self.bot.get_guild(guild_id)

        # Create embed
        embed = discord.Embed(
            title="📅 Live Calendar",
            description="This calendar shows times in **Europe/Berlin** timezone.",
            color=self._get_calendar_color(guild)
        )

        # Get selections
        selections = poll_data.get("selections", {})

        # Calculate winning times using weighted point system
        winning_times = self._calculate_winning_times_weighted(selections)

        # Generate calendar image
        calendar_data = self._prepare_calendar_data(winning_times)
        image_buffer = self.calendar_renderer.render_calendar(
            calendar_data,
            self.events,
            self.blocked_times,
            len(selections)
        )

        # Create file attachment
        calendar_file = discord.File(image_buffer, filename="calendar.png")
        embed.set_image(url="attachment://calendar.png")

        # Create view with timezone button
        view = CalendarTimezoneView(self, guild_id, poll_id)

        return embed, calendar_file, view

    async def _create_weekly_calendar_embed(self, poll_data: Dict, guild_id: int, poll_id: str) -> Tuple[discord.Embed, discord.File, discord.ui.View, Dict]:
        """Create a weekly calendar embed with image and poll link (updates only on Monday 10AM)

        Returns:
            Tuple of (embed, file, view, winning_times) where file is the calendar image,
            view contains timezone button, and winning_times is the snapshot data
        """
        from .views import CalendarTimezoneView

        title = poll_data["title"]
        channel_id = poll_data["channel_id"]
        message_id = poll_data["message_id"]

        # Get guild for color
        guild = self.bot.get_guild(guild_id)

        # Create embed
        embed = discord.Embed(
            title="📅 Event Calendar",
            description="This calendar shows times in **Europe/Berlin** timezone.",
            color=self._get_calendar_color(guild)
        )

        # Get selections
        selections = poll_data.get("selections", {})

        # Calculate winning times using weighted point system
        winning_times = self._calculate_winning_times_weighted(selections)

        # Generate calendar image
        calendar_data = self._prepare_calendar_data(winning_times)
        image_buffer = self.calendar_renderer.render_calendar(
            calendar_data,
            self.events,
            self.blocked_times,
            len(selections)
        )

        # Create file attachment
        calendar_file = discord.File(image_buffer, filename="calendar.png")
        embed.set_image(url="attachment://calendar.png")

        # Add footer
        embed.set_footer(text="times are adjusted every week based on Monday's results")

        # Create view with timezone button (is_weekly=True) and link button
        poll_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        view = CalendarTimezoneView(self, guild_id, poll_id, is_weekly=True, poll_url=poll_url)

        return embed, calendar_file, view, winning_times

    async def _update_calendar_messages(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Update all live calendar messages associated with this poll"""
        calendar_messages = poll_data.get("calendar_messages", [])

        for cal_msg_data in calendar_messages:
            try:
                channel = guild.get_channel(cal_msg_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(cal_msg_data["message_id"])
                    updated_embed, calendar_file, view = await self._create_calendar_embed(poll_data, guild.id, poll_id)
                    await message.edit(embed=updated_embed, attachments=[calendar_file], view=view)
            except Exception:
                # Silently fail if we can't update a calendar message
                pass

    async def _check_and_create_initial_snapshot(self, guild: discord.Guild, poll_id: str):
        """Check if this is the first vote and create initial weekly snapshot if needed"""
        async with self.config.guild(guild).polls() as polls:
            if poll_id not in polls:
                return

            poll_data = polls[poll_id]

            # Check if snapshot already exists
            if "weekly_snapshot_winning_times" in poll_data:
                return

            # Check if there are any weekly calendar messages
            weekly_calendar_messages = poll_data.get("weekly_calendar_messages", [])
            if not weekly_calendar_messages:
                return

            # Calculate and store the initial snapshot
            selections = poll_data.get("selections", {})
            if not selections:
                return

            winning_times = self._calculate_winning_times_weighted(selections)
            polls[poll_id]["weekly_snapshot_winning_times"] = winning_times

        # Update the weekly calendar images with the new snapshot
        try:
            polls_data = await self.config.guild(guild).polls()
            poll_data = polls_data.get(poll_id)
            if poll_data:
                await self._update_weekly_calendar_messages(guild, poll_data, poll_id)
        except Exception:
            # Silently fail if we can't update calendars
            pass

    async def _update_weekly_calendar_messages(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Update all weekly calendar messages associated with this poll"""
        weekly_calendar_messages = poll_data.get("weekly_calendar_messages", [])

        if not weekly_calendar_messages:
            return

        # Generate the calendar with the snapshot
        updated_embed, first_calendar_file, view, winning_times = await self._create_weekly_calendar_embed(poll_data, guild.id, poll_id)

        # Store the snapshot
        async with self.config.guild(guild).polls() as polls:
            if poll_id in polls:
                polls[poll_id]["weekly_snapshot_winning_times"] = winning_times

        # Update all weekly calendar messages
        for idx, cal_msg_data in enumerate(weekly_calendar_messages):
            try:
                channel = guild.get_channel(cal_msg_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(cal_msg_data["message_id"])
                    # Need to create a new file for each message since files can only be sent once
                    if idx == 0:
                        # Use the first file for the first message
                        await message.edit(embed=updated_embed, attachments=[first_calendar_file], view=view)
                    else:
                        # Generate new file for subsequent messages
                        _, calendar_file_copy, _, _ = await self._create_weekly_calendar_embed(poll_data, guild.id, poll_id)
                        await message.edit(embed=updated_embed, attachments=[calendar_file_copy], view=view)
            except Exception:
                # Silently fail if we can't update a weekly calendar message
                pass

    async def _create_results_embed(self, poll_data: Dict, guild_id: int, poll_id: str) -> discord.Embed:
        """Create a results embed showing current poll results

        Returns:
            Embed with poll results
        """
        title = poll_data["title"]
        channel_id = poll_data["channel_id"]
        message_id = poll_data["message_id"]

        # Get guild for color
        guild = self.bot.get_guild(guild_id)

        # Create embed
        embed = discord.Embed(
            title=f"📊 Poll Results: {title}",
            color=self._get_embed_color(guild)
        )

        # Get selections
        selections = poll_data.get("selections", {})

        if not selections:
            embed.add_field(
                name="No Votes Yet",
                value="Be the first to vote!",
                inline=False
            )
            embed.set_footer(text="Updated every Monday at 10 AM server time")
            return embed

        # Calculate winning times using weighted point system
        winning_times = self._calculate_winning_times_weighted(selections)

        # Format results for each event
        for event_name, event_info in self.events.items():
            emoji = event_info["emoji"]
            event_slots = winning_times.get(event_name, {})

            if event_slots:
                field_value = ""
                for slot_index in range(event_info["slots"]):
                    if slot_index not in event_slots:
                        continue

                    winner_key, winner_points, all_entries = event_slots[slot_index]
                    day, time = winner_key

                    # Format header based on event type
                    if event_info["slots"] > 1:
                        if event_info["type"] == "fixed_days":
                            day_name = event_info["days"][slot_index] if slot_index < len(event_info["days"]) else f"Slot {slot_index + 1}"
                            field_value += f"**{day_name[:3]}:** "
                        else:
                            field_value += f"**Slot {slot_index + 1}:** "

                    # Show winning time
                    if event_info["type"] == "daily":
                        field_value += f"{time} ({winner_points} pts)\n"
                    elif event_info["type"] == "fixed_days":
                        if event_info["slots"] > 1:
                            field_value += f"{day[:3]} {time} ({winner_points} pts)\n"
                        else:
                            days_str = "/".join([d[:3] for d in event_info["days"]])
                            field_value += f"{time} ({days_str}) ({winner_points} pts)\n"
                    else:
                        field_value += f"{day[:3]} {time} ({winner_points} pts)\n"

                embed.add_field(
                    name=f"{emoji} {event_name}",
                    value=field_value.strip() or "No votes",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"{emoji} {event_name}",
                    value="No votes yet",
                    inline=False
                )

        # Add timestamp and voter count
        last_updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        embed.set_footer(text=f"Total voters: {len(selections)} | Last updated: {last_updated} | Updates every Monday at 10 AM")

        return embed

    async def _update_results_messages(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Update all results messages associated with this poll"""
        results_messages = poll_data.get("results_messages", [])

        for res_msg_data in results_messages:
            try:
                channel = guild.get_channel(res_msg_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(res_msg_data["message_id"])
                    updated_embed = await self._create_results_embed(poll_data, guild.id, poll_id)
                    await message.edit(embed=updated_embed)
            except Exception:
                # Silently fail if we can't update a results message
                pass

    async def _create_poll_embed(self, title: str, guild_id: int, poll_id: str) -> discord.Embed:
        """Create calendar-style embed showing winning times"""
        # Get guild for color
        guild = self.bot.get_guild(guild_id)

        embed = discord.Embed(
            title=f"📅 {title}",
            color=self._get_embed_color(guild)
        )

        # Get poll data if it exists
        polls = await self.config.guild_from_id(guild_id).polls()
        selections = {}
        if poll_id and poll_id in polls:
            selections = polls[poll_id].get("selections", {})

        # Show event info at the top
        embed.add_field(
            name="🔓 Unlocked",
            value=(
                "🛡️ **Hero's Realm (Catch-up)**\n"
                "Weekly (30 min, 1 slot)\n"
                "⚔️ **Sword Trial / (Echo)**\n"
                "Mon(Echo)/Wed/Fri (30 min)\n"
                "⚡ **Breaking Army**\n"
                "Weekly (60 min, 2 slots)\n"
                "🏆 **Showdown**\n"
                "Weekly (60 min, 2 slots)\n"
                "🏰 **Guild War**\n"
                "Sat (90 min, 20:30 - 23:00)\n"
                "🎉 **Party**\n"
                "Daily (10 min)"
            ),
            inline=True
        )
        embed.add_field(
            name="🔒 Locked",
            value=(
                "🛡️ **Hero's Realm (Reset)**\n"
                "Sun 22:00\n"
                "🏰 **Guild War**\n"
                "Sun 20:30-22:00"
            ),
            inline=True
        )

        # Calculate winning times (most votes) for each event and slot
        winning_times = {}
        for event_name, event_info in self.events.items():
            # Skip locked events - they have fixed times and no voting
            if event_info.get("type") == "locked":
                continue
            num_slots = event_info["slots"]
            winning_times[event_name] = {}

            for slot_index in range(num_slots):
                vote_counts = {}

                for user_id, user_selections in selections.items():
                    if event_name in user_selections:
                        selection = user_selections[event_name]

                        # Handle both list (multi-slot) and dict (single-slot) formats
                        if isinstance(selection, list):
                            if slot_index < len(selection) and selection[slot_index]:
                                slot_data = selection[slot_index]
                                if event_info["type"] == "daily":
                                    key = ("Daily", slot_data["time"])
                                elif event_info["type"] == "fixed_days":
                                    key = ("Fixed", slot_data["time"])
                                else:
                                    key = (slot_data.get("day", "Unknown"), slot_data["time"])
                                vote_counts[key] = vote_counts.get(key, 0) + 1
                        else:
                            # Legacy single-slot format
                            if slot_index == 0:
                                if isinstance(selection, str):
                                    time_val = selection
                                    day_val = "Unknown"
                                else:
                                    time_val = selection["time"]
                                    day_val = selection.get("day", "Unknown")

                                if event_info["type"] == "daily":
                                    key = ("Daily", time_val)
                                elif event_info["type"] == "fixed_days":
                                    key = ("Fixed", time_val)
                                else:
                                    key = (day_val, time_val)
                                vote_counts[key] = vote_counts.get(key, 0) + 1

                if vote_counts:
                    max_votes = max(vote_counts.values())
                    winners = [k for k, v in vote_counts.items() if v == max_votes]
                    winning_times[event_name][slot_index] = (winners, max_votes)

        # Current Winners removed - use Results button to view

        embed.set_footer(text="⚠️ Events (excluding party) cannot have conflicting times, click Results to view votes and tiebreak rules")

        return embed

    def format_results_intro(self, selections: Dict) -> str:
        """Format results introduction with rules explanation

        Args:
            selections: Dict of user selections

        Returns:
            Formatted string with voting rules and tiebreak explanation
        """
        summary_lines = [
            "**📊 Current Results** (Weighted Voting System)",
            f"Total voters: {len(selections)}",
            "",
            "**How voting works:**",
            "• 5 points: Your exact voted time",
            "• 2 points: 30 minutes before/after your voted time",
            "• 1 point: 1 hour before/after your voted time",
            "  *(Note: Guild War only counts exact time matches)*",
            "",
            "**Event priority and tiebreak rules:**",
            "• Priority order: Guild War (6) > Hero's Realm (5) > Sword Trial (4) > Party (3) > Breaking Army (2) > Showdown (1)",
            "• When events conflict: Higher priority gets +3 bonus points",
            "• After bonus, higher points wins the time slot",
            "• If still tied: Breaking Army/Showdown prefer Saturday, then later time; others prefer later time",
            "",
        ]
        return "\n".join(summary_lines)

    def format_all_results_inline(self, winning_times: Dict, selections: Dict) -> str:
        """Format all event results inline without buttons

        Args:
            winning_times: Dict from _calculate_winning_times_weighted
            selections: Dict of user selections

        Returns:
            Formatted string with all event results displayed inline
        """
        # Start with header
        result_lines = [self.format_results_intro(selections)]

        # Add results for each event
        for event_name, event_info in self.events.items():
            emoji = event_info["emoji"]
            event_slots = winning_times.get(event_name, {})

            # Format each slot for this event
            for slot_index in range(event_info["slots"]):
                slot_data = event_slots.get(slot_index)
                
                # Determine display label
                if event_info["slots"] > 1:
                    if event_info["type"] == "fixed_days":
                        day_name = event_info["days"][slot_index] if slot_index < len(event_info["days"]) else f"Slot {slot_index + 1}"
                        label = f"{emoji} **{event_name} ({day_name[:3]})**"
                    else:
                        label = f"{emoji} **{event_name} Slot {slot_index + 1}**"
                else:
                    label = f"{emoji} **{event_name}**"

                if not slot_data:
                    result_lines.append(f"{label}: *No votes yet*")
                    continue

                winner_key, winner_points, all_entries = slot_data
                
                # Show top 3 entries if they exist
                if all_entries:
                    top_entries = []
                    for rank, (key, points) in enumerate(all_entries[:3], 1):
                        day, time = key
                        entry_text = f"**{rank}.** "
                        if event_info["type"] == "daily" or event_info["type"] == "fixed_days":
                            entry_text += f"{time}"
                        else:
                            entry_text += f"{day[:3]} {time}"
                        
                        entry_text += f" ({points} pts)"
                        top_entries.append(entry_text)
                    
                    result_lines.append(f"{label}: {' **|** '.join(top_entries)}")
                else:
                    # Fallback for defaults (points = 0) or single winner
                    day, time = winner_key
                    if winner_points == 0:
                        result_lines.append(f"{label}: *Default:* {time}")
                    else:
                        # Use winner_key if all_entries is somehow empty but we have points
                        display_day = f"{day[:3]} " if day and day not in ("Daily", "Fixed") else ""
                        result_lines.append(f"{label}: **1.** {display_day}{time} ({winner_points} pts)")

        return "\n".join(result_lines)

    def format_event_results(self, event_name: str, winning_times: Dict, selections: Dict) -> str:
        """Format results for a single event category

        Args:
            event_name: Name of the event
            winning_times: Dict from _calculate_winning_times_weighted
            selections: Dict of user selections

        Returns:
            Formatted string with top 3 results for the event
        """
        summary_lines = []

        event_info = self.events.get(event_name)
        if not event_info:
            return f"Event '{event_name}' not found."

        emoji = event_info["emoji"]
        event_slots = winning_times.get(event_name, {})

        if event_slots:
            for slot_index in range(event_info["slots"]):
                if slot_index not in event_slots:
                    continue

                winner_key, winner_points, all_entries = event_slots[slot_index]

                # Format header based on event type
                if event_info["slots"] > 1:
                    if event_info["type"] == "fixed_days":
                        day_name = event_info["days"][slot_index] if slot_index < len(event_info["days"]) else f"Slot {slot_index + 1}"
                        summary_lines.append(f"{emoji} **{event_name} ({day_name[:3]})**:")
                    else:
                        summary_lines.append(f"{emoji} **{event_name} Slot {slot_index + 1}**:")
                else:
                    summary_lines.append(f"{emoji} **{event_name}**:")

                # Show top 3 entries
                for rank, (key, points) in enumerate(all_entries[:3], 1):
                    day, time = key
                    if event_info["type"] == "daily":
                        summary_lines.append(f"  {rank}. {time} - **{points} pts**")
                    elif event_info["type"] == "fixed_days":
                        if event_info["slots"] > 1:
                            summary_lines.append(f"  {rank}. {day[:3]} {time} - **{points} pts**")
                        else:
                            days_str = "/".join([d[:3] for d in event_info["days"]])
                            summary_lines.append(f"  {rank}. {time} ({days_str}) - **{points} pts**")
                    else:
                        summary_lines.append(f"  {rank}. {day[:3]} {time} - **{points} pts**")

                summary_lines.append("")
        else:
            if event_info["slots"] > 1:
                for slot_index in range(event_info["slots"]):
                    summary_lines.append(f"{emoji} **{event_name} Slot {slot_index + 1}**: No votes yet")
            else:
                summary_lines.append(f"{emoji} **{event_name}**: No votes yet")
            summary_lines.append("")

        return "\n".join(summary_lines)

    def format_results_summary_weighted(self, winning_times: Dict, selections: Dict) -> str:
        """Format results summary with weighted points for display

        Args:
            winning_times: Dict from _calculate_winning_times_weighted
            selections: Dict of user selections

        Returns:
            Formatted string with top 3 results and explanation
        """
        # Add header with explanation
        summary_lines = [
            "**📊 Current Results** (Weighted Voting System)",
            f"Total voters: {len(selections)}",
            "",
            "**How voting works:**",
            "• 5 points: Your exact voted time",
            "• 2 points: 30 minutes before/after your voted time",
            "• 1 point: 1 hour before/after your voted time",
            "  *(Note: Guild War only counts exact time matches)*",
            "",
            "**Event priority and tiebreak rules:**",
            "• Priority order: Guild War (6) > Hero's Realm (5) > Sword Trial (4) > Party (3) > Breaking Army (2) > Showdown (1)",
            "• When events conflict: Higher priority gets +3 bonus points",
            "• After bonus, higher points wins the time slot",
            "• If still tied: Breaking Army/Showdown prefer Saturday, then later time; others prefer later time",
            "",
            "**Top 3 Options Per Event:**",
            ""
        ]

        for event_name, event_info in self.events.items():
            emoji = event_info["emoji"]
            event_slots = winning_times.get(event_name, {})

            if event_slots:
                for slot_index in range(event_info["slots"]):
                    if slot_index not in event_slots:
                        continue

                    winner_key, winner_points, all_entries = event_slots[slot_index]

                    # Format header based on event type
                    if event_info["slots"] > 1:
                        if event_info["type"] == "fixed_days":
                            day_name = event_info["days"][slot_index] if slot_index < len(event_info["days"]) else f"Slot {slot_index + 1}"
                            summary_lines.append(f"{emoji} **{event_name} ({day_name[:3]})**:")
                        else:
                            summary_lines.append(f"{emoji} **{event_name} Slot {slot_index + 1}**:")
                    else:
                        summary_lines.append(f"{emoji} **{event_name}**:")

                    # Show top 3 entries
                    for rank, (key, points) in enumerate(all_entries[:3], 1):
                        day, time = key
                        if event_info["type"] == "daily":
                            summary_lines.append(f"  {rank}. {time} - **{points} pts**")
                        elif event_info["type"] == "fixed_days":
                            if event_info["slots"] > 1:
                                summary_lines.append(f"  {rank}. {day[:3]} {time} - **{points} pts**")
                            else:
                                days_str = "/".join([d[:3] for d in event_info["days"]])
                                summary_lines.append(f"  {rank}. {time} ({days_str}) - **{points} pts**")
                        else:
                            summary_lines.append(f"  {rank}. {day[:3]} {time} - **{points} pts**")

                    summary_lines.append("")
            else:
                if event_info["slots"] > 1:
                    for slot_index in range(event_info["slots"]):
                        summary_lines.append(f"{emoji} **{event_name} Slot {slot_index + 1}**: No votes yet")
                else:
                    summary_lines.append(f"{emoji} **{event_name}**: No votes yet")
                summary_lines.append("")

        return "\n".join(summary_lines)

    def format_results_summary(self, winning_times: Dict, selections: Dict) -> str:
        """Format results summary for display

        Args:
            winning_times: Dict of event winning times
            selections: Dict of user selections

        Returns:
            Formatted string with results summary
        """
        summary_lines = []
        for event_name, event_info in self.events.items():
            emoji = event_info["emoji"]
            event_slots = winning_times.get(event_name, {})

            if event_slots:
                for slot_index in range(event_info["slots"]):
                    if slot_index in event_slots:
                        winners, votes = event_slots[slot_index]
                        if event_info["type"] == "daily":
                            time_str = winners[0][1]
                            summary_lines.append(f"{emoji} **{event_name}**: {time_str} ({votes} votes)")
                        elif event_info["type"] == "fixed_days":
                            time_str = winners[0][1]
                            if event_info["slots"] > 1:
                                # Multi-slot fixed-day event - show day name from slot index
                                day_name = event_info["days"][slot_index] if slot_index < len(event_info["days"]) else f"Day {slot_index + 1}"
                                summary_lines.append(f"{emoji} **{event_name} ({day_name})**: {time_str} ({votes} votes)")
                            else:
                                summary_lines.append(f"{emoji} **{event_name}**: {time_str} ({votes} votes)")
                        else:
                            winner_strs = [f"{day} {time}" for day, time in winners]
                            if event_info["slots"] > 1:
                                summary_lines.append(f"{emoji} **{event_name} #{slot_index + 1}**: {winner_strs[0]} ({votes} votes)")
                            else:
                                summary_lines.append(f"{emoji} **{event_name}**: {winner_strs[0]} ({votes} votes)")
                    else:
                        if event_info["slots"] > 1:
                            summary_lines.append(f"{emoji} **{event_name} #{slot_index + 1}**: No votes yet")
            else:
                if event_info["slots"] > 1:
                    for slot_index in range(event_info["slots"]):
                        summary_lines.append(f"{emoji} **{event_name} #{slot_index + 1}**: No votes yet")
                else:
                    summary_lines.append(f"{emoji} **{event_name}**: No votes yet")

        header = f"**🏆 Current Results** (Total voters: {len(selections)})\n\n"
        return header + "\n".join(summary_lines)

    def _create_calendar_table(self, winning_times: Dict) -> str:
        """Create a visual Unicode calendar table showing the weekly schedule"""
        # Build a data structure: {time: {day: [(priority, emoji)]}}
        schedule = {}
        times = self.generate_time_options(17, 26, 30)

        for time_slot in times:
            schedule[time_slot] = {day: [] for day in self.days_of_week}

        # Populate schedule with winning events (with priority)
        for event_name, event_info in self.events.items():
            emoji = event_info["emoji"]
            priority = event_info["priority"]
            event_slots = winning_times.get(event_name, {})

            for slot_index, slot_winners in event_slots.items():
                winners, votes = slot_winners

                for winner_day, winner_time in winners:
                    if event_info["type"] == "daily":
                        # Daily events appear on all days
                        for day in self.days_of_week:
                            if event_info["slots"] > 1:
                                schedule[winner_time][day].append((priority, f"{emoji}{slot_index + 1}"))
                            else:
                                schedule[winner_time][day].append((priority, emoji))
                    elif event_info["type"] == "fixed_days":
                        # Fixed-day events appear on their configured days
                        if event_info["slots"] > 1:
                            # Multi-slot: each slot corresponds to one specific day
                            if slot_index < len(event_info["days"]):
                                specific_day = event_info["days"][slot_index]
                                schedule[winner_time][specific_day].append((priority, f"{emoji}{slot_index + 1}"))
                        else:
                            # Single slot: appears on all configured days
                            for day in event_info["days"]:
                                schedule[winner_time][day].append((priority, emoji))
                    else:
                        # Weekly events appear only on their specific day
                        if event_info["slots"] > 1:
                            schedule[winner_time][winner_day].append((priority, f"{emoji}{slot_index + 1}"))
                        else:
                            schedule[winner_time][winner_day].append((priority, emoji))

        # Add Guild Wars emoji to blocked time slots (priority 0 - always shows last)
        for blocked in self.blocked_times:
            blocked_day = blocked["day"]
            blocked_start = blocked["start"]
            blocked_end = blocked["end"]

            # Parse blocked times
            start_time = datetime.strptime(blocked_start, "%H:%M")
            end_time = datetime.strptime(blocked_end, "%H:%M")

            # Add Guild Wars emoji to all time slots in the blocked range
            for time_slot in times:
                # Handle 24:00 special case (treat as 00:00 next day)
                if time_slot == "24:00":
                    slot_time = datetime.strptime("00:00", "%H:%M")
                else:
                    slot_time = datetime.strptime(time_slot, "%H:%M")

                # Check if this time slot is within the blocked range (inclusive start, exclusive end)
                if start_time <= slot_time < end_time:
                    schedule[time_slot][blocked_day].append((0, self.guild_wars_emoji))

        # Build the table using code block for monospace formatting
        lines = []

        # Header row with timezone
        lines.append("```")
        lines.append(f"All times in {self.timezone_display}")
        lines.append("")
        header = "Time  │ Mon │ Tue │ Wed │ Thu │ Fri │ Sat │ Sun"
        lines.append(header)
        lines.append("─" * len(header))

        # Data rows - show all time slots
        for time_slot in times:
            row_data = schedule[time_slot]
            row = f"{time_slot} │"
            for day in self.days_of_week:
                events = row_data[day]
                if events:
                    # Sort by priority (descending - highest priority first)
                    sorted_events = sorted(events, key=lambda x: x[0], reverse=True)
                    # Extract just the emoji strings, limit to 2 events per cell
                    event_emojis = [emoji for priority, emoji in sorted_events[:2]]
                    cell = "".join(event_emojis)

                    # Emojis render as 2-char width in monospace
                    # Need 5 chars total before │ to match header
                    if len(event_emojis) == 2:
                        # 2 emojis = 4 char widths, need 1 leading space
                        row += f" {cell}│"
                    else:
                        # 1 emoji = 2 char widths, need 1 leading + 2 trailing spaces
                        row += f" {cell}  │"
                else:
                    # Empty cell - use braille blank pattern to match emoji width
                    # ⠀ (braille blank U+2800) +   (hair space U+200A) + ⠀ (braille blank)
                    # Pattern: " ⠀ ⠀  │" = 1 + 2 + 2 spaces = 5 chars (matches single emoji cell)
                    row += " ⠀ ⠀  │"
            lines.append(row)

        lines.append("```")

        return "\n".join(lines) if len(lines) > 3 else ""

    def _calculate_winning_times_weighted(self, selections: Dict) -> Dict:
        """Calculate winning times using weighted point system

        Args:
            selections: User selections dict

        Returns:
            Dict of winning times with points: {event_name: {slot_index: (winner_key, points, all_entries)}}
            where all_entries is a list of (key, points) tuples sorted by points descending
        """
        log.info("=== Starting weighted voting calculation ===")
        log.info(f"Total users with selections: {len(selections)}")

        winning_times = {}

        # Generate all possible times
        all_times = self.generate_time_options(17, 26, 30)

        for event_name, event_info in self.events.items():
            num_slots = event_info.get("slots", 1)
            winning_times[event_name] = {}
            log.info(f"Processing event: {event_name} (type: {event_info['type']}, slots: {num_slots})")

            # Handle locked events - fixed time, no voting
            if event_info["type"] == "locked":
                fixed_time = event_info.get("fixed_time")
                days = event_info.get("days", [])
                if fixed_time and days:
                    # Locked events only have one slot (the fixed time on the specified day)
                    day = days[0]
                    winning_times[event_name][0] = ((day, fixed_time), 9999, [])  # High points to ensure priority
                    log.info(f"  Locked event: {day} at {fixed_time}")
                continue

            # Special handling for weekly events with multiple slots (Breaking Army, Showdown)
            # Pool all votes together and select top 2
            if event_info["type"] == "weekly" and num_slots > 1:
                # Pool votes from all slots
                point_totals = {}

                # Process each user's vote (pool both slots together)
                for user_id, user_selections in selections.items():
                    if event_name not in user_selections:
                        continue

                    selection = user_selections[event_name]

                    # Collect all voted times from all slots for this user
                    voted_entries = []
                    if isinstance(selection, list):
                        for slot_data in selection:
                            if slot_data:
                                voted_time = slot_data.get("time")
                                voted_day = slot_data.get("day")
                                if voted_time and voted_day:
                                    voted_entries.append((voted_day, voted_time))
                    else:
                        # Single-slot format
                        voted_time = selection.get("time")
                        voted_day = selection.get("day")
                        if voted_time and voted_day:
                            voted_entries.append((voted_day, voted_time))

                    # Award points for each voted entry
                    for voted_day, voted_time in voted_entries:
                        # Main points for the voted day
                        is_weighted = event_name != "Guild War"
                        for target_time in all_times:
                            points = self._calculate_weighted_points(voted_time, target_time, weighted=is_weighted)
                            if points > 0:
                                key = (voted_day, target_time)
                                point_totals[key] = point_totals.get(key, 0) + points

                # Sort by points (desc), then by distance to Saturday (asc), then by time (desc)
                def saturday_distance(day_name: str) -> int:
                    """Calculate distance from Saturday (0 = Saturday, 1 = Fri/Sun, etc.)"""
                    day_index = self.days_of_week.index(day_name)
                    saturday_index = 5  # Saturday
                    return min(abs(day_index - saturday_index), 7 - abs(day_index - saturday_index))

                if point_totals:
                    sorted_entries = sorted(
                        point_totals.items(),
                        key=lambda x: (-x[1], saturday_distance(x[0][0]), -self._time_to_sort_key(x[0][1])),
                    )

                    # Assign top 2 to slots
                    for slot_index in range(min(num_slots, len(sorted_entries))):
                        winner_key, winner_points = sorted_entries[slot_index]
                        winning_times[event_name][slot_index] = (winner_key, winner_points, sorted_entries[:3])
                        log.info(f"  Slot {slot_index}: {winner_key[0]} at {winner_key[1]} with {winner_points} points")

            else:
                # Original slot-by-slot logic for other event types
                for slot_index in range(num_slots):
                    # Dictionary to store points: key -> total_points
                    point_totals = {}

                    # Process each user's vote
                    for user_id, user_selections in selections.items():
                        if event_name not in user_selections:
                            continue

                        selection = user_selections[event_name]
                        is_weighted = event_name != "Guild War"

                        # Get the voted time for this slot
                        voted_time = None
                        voted_day = None

                        if isinstance(selection, list):
                            if slot_index < len(selection) and selection[slot_index]:
                                slot_data = selection[slot_index]
                                voted_time = slot_data["time"]
                                voted_day = slot_data.get("day")
                        else:
                            # Single-slot format
                            if slot_index == 0:
                                if isinstance(selection, str):
                                    voted_time = selection
                                    voted_day = None
                                else:
                                    voted_time = selection["time"]
                                    voted_day = selection.get("day")

                        if not voted_time:
                            continue

                        # Calculate points for all possible times
                        if event_info["type"] == "daily":
                            # Daily events
                            for target_time in all_times:
                                points = self._calculate_weighted_points(voted_time, target_time, weighted=is_weighted)
                                if points > 0:
                                    key = ("Daily", target_time)
                                    point_totals[key] = point_totals.get(key, 0) + points

                        elif event_info["type"] == "fixed_days":
                            # Fixed-day events
                            if event_info["slots"] > 1 and voted_day:
                                # Multi-slot: specific day
                                for target_time in all_times:
                                    points = self._calculate_weighted_points(voted_time, target_time, weighted=is_weighted)
                                    if points > 0:
                                        key = (voted_day, target_time)
                                        point_totals[key] = point_totals.get(key, 0) + points
                            else:
                                # Single slot for all fixed days
                                for target_time in all_times:
                                    points = self._calculate_weighted_points(voted_time, target_time, weighted=is_weighted)
                                    if points > 0:
                                        key = ("Fixed", target_time)
                                        point_totals[key] = point_totals.get(key, 0) + points

                        else:
                            # Weekly events (single slot only, legacy path)
                            if not voted_day:
                                continue

                            # Main points for the voted day
                            for target_time in all_times:
                                points = self._calculate_weighted_points(voted_time, target_time, weighted=is_weighted)
                                if points > 0:
                                    key = (voted_day, target_time)
                                    point_totals[key] = point_totals.get(key, 0) + points

                            # Special case: 1 point to same time on all other days
                            if is_weighted:
                                for day in self.days_of_week:
                                    if day != voted_day:
                                        key = (day, voted_time)
                                        point_totals[key] = point_totals.get(key, 0) + 1

                    # Select winner (highest points, latest time for ties)
                    if point_totals:
                        # Sort by points (descending) then by time (descending for tie-breaking)
                        sorted_entries = sorted(
                            point_totals.items(),
                            key=lambda x: (x[1], x[0][1]),  # Sort by points, then by time
                            reverse=True
                        )

                        winner_key, winner_points = sorted_entries[0]
                        winning_times[event_name][slot_index] = (winner_key, winner_points, sorted_entries[:3])
                    else:
                        # Auto-populate with default times if no votes
                        defaults = event_info.get("default_times", {})
                        if defaults:
                            default_winner = None

                            if event_info["type"] == "daily":
                                if "default" in defaults:
                                    default_winner = (("Daily", defaults["default"]), 0, [])

                            elif event_info["type"] == "fixed_days":
                                if event_info["slots"] > 1:
                                    if slot_index < len(event_info.get("days", [])):
                                        day_name = event_info["days"][slot_index]
                                        if day_name in defaults:
                                            default_winner = ((day_name, defaults[day_name]), 0, [])
                                else:
                                    if "default" in defaults:
                                        default_winner = (("Fixed", defaults["default"]), 0, [])
                                    elif defaults:
                                        # Use the first available default
                                        key = list(defaults.keys())[0]
                                        default_winner = (("Fixed", defaults[key]), 0, [])

                            else:
                                # For once/weekly types, map slots to sorted defaults
                                def get_day_index(d):
                                    try:
                                        return self.days_of_week.index(d)
                                    except ValueError:
                                        return 999

                                sorted_defaults = sorted(
                                    [(k, v) for k, v in defaults.items() if k != "default"],
                                    key=lambda x: get_day_index(x[0])
                                )

                                if num_slots > 1:
                                    if slot_index < len(sorted_defaults):
                                        day, time = sorted_defaults[slot_index]
                                        default_winner = ((day, time), 0, [])
                                elif sorted_defaults:
                                    day, time = sorted_defaults[0]
                                    default_winner = ((day, time), 0, [])

                            if default_winner:
                                winning_times[event_name][slot_index] = default_winner
                                log.info(f"  Slot {slot_index}: Auto-populated default {default_winner[0]}")

        # Resolve conflicts between events based on priority
        winning_times = self._resolve_event_conflicts(winning_times)

        return winning_times

    def _resolve_event_conflicts(self, winning_times: Dict) -> Dict:
        """Resolve conflicts between events based on priority bonus system

        When events conflict at the same time:
        - Higher priority events get +3 point bonus
        - After bonus, higher points wins
        - If still tied, use regular tiebreak rules

        Args:
            winning_times: Initial winning times from voting

        Returns:
            Adjusted winning times with conflicts resolved
        """
        log.info("=== Starting conflict resolution ===")

        # Build a mapping of (day, time) -> [(event_name, slot_index, points, priority)]
        time_slot_candidates = {}

        for event_name, event_info in self.events.items():
            if event_name not in winning_times:
                continue

            priority = event_info.get("priority", 0)

            for slot_index, slot_data in winning_times[event_name].items():
                winner_key, winner_points, all_entries = slot_data
                day, time = winner_key

                # Get all days this event affects
                affected_days = self._get_affected_days(event_name, day)

                # Register this event for all time slots it occupies
                for affected_day in affected_days:
                    # Find all 30-min slots this event occupies
                    from datetime import datetime, timedelta
                    current_time = datetime.strptime(time, "%H:%M")
                    duration = event_info.get("duration", 30)
                    slots_needed = max(1, duration // 30)

                    for i in range(slots_needed):
                        slot_time = current_time + timedelta(minutes=i * 30)
                        slot_time_str = slot_time.strftime("%H:%M")
                        slot_key = (affected_day, slot_time_str)

                        if slot_key not in time_slot_candidates:
                            time_slot_candidates[slot_key] = []

                        time_slot_candidates[slot_key].append({
                            'event_name': event_name,
                            'slot_index': slot_index,
                            'points': winner_points,
                            'priority': priority,
                            'start_time': time,
                            'all_entries': all_entries
                        })

        # Resolve conflicts for each time slot
        occupied_by = {}  # {(day, time): event_name} - tracks which event won each slot
        adjusted_winning_times = {}
        events_needing_reassignment = set()  # Events that lost their preferred time

        for slot_key, candidates in time_slot_candidates.items():
            if len(candidates) == 1:
                # No conflict, event gets this time
                candidate = candidates[0]
                occupied_by[slot_key] = candidate['event_name']
            else:
                # Conflict! Check if Party can coexist with other events
                conflict_msg = [f"{c['event_name']} slot {c['slot_index']}" for c in candidates]
                log.info(f"Conflict at {slot_key}: {conflict_msg}")
                party_candidate = None
                other_candidates = []

                for candidate in candidates:
                    if candidate['event_name'] == 'Party':
                        party_candidate = candidate
                    else:
                        other_candidates.append(candidate)

                # If Party is involved, allow coexistence (like Guild War)
                # Only Party can share cells with other events
                # Other events cannot share cells with each other
                if party_candidate and len(other_candidates) > 0:
                    # Both Party and the other event(s) keep their times
                    # Mark all as occupying this slot (for table splitting)
                    log.info(f"  Party coexistence allowed - all events keep their times")
                    for candidate in candidates:
                        occupied_by[slot_key] = candidate['event_name']
                    # Don't mark anyone for reassignment - they can coexist
                else:
                    # Standard conflict resolution when Party is not involved
                    # Apply priority bonuses and resolve
                    max_priority = max(c['priority'] for c in candidates)

                    for candidate in candidates:
                        # Higher priority gets +3 bonus
                        if candidate['priority'] == max_priority:
                            candidate['adjusted_points'] = candidate['points'] + 3
                        else:
                            candidate['adjusted_points'] = candidate['points']

                    # Sort by adjusted points (desc), then by priority (desc), then by time (desc for tiebreak)
                    candidates.sort(key=lambda x: (-x['adjusted_points'], -x['priority'], -self._time_to_sort_key(x['start_time'])))

                    winner = candidates[0]
                    occupied_by[slot_key] = winner['event_name']
                    log.info(f"  Winner: {winner['event_name']} slot {winner['slot_index']} ({winner['adjusted_points']} pts)")

                    # Mark losers for reassignment
                    for loser in candidates[1:]:
                        events_needing_reassignment.add((loser['event_name'], loser['slot_index']))
                        log.info(f"  Loser needs reassignment: {loser['event_name']} slot {loser['slot_index']}")

        # Assign winning times to events
        # First pass: Add all winners to adjusted_winning_times
        for event_name, event_info in self.events.items():
            if event_name not in winning_times:
                continue

            adjusted_winning_times[event_name] = {}

            for slot_index, slot_data in winning_times[event_name].items():
                # Check if this event needs reassignment
                if (event_name, slot_index) not in events_needing_reassignment:
                    # Event won its preferred time
                    adjusted_winning_times[event_name][slot_index] = slot_data

        # Second pass: Process losers and find alternatives
        for event_name, event_info in self.events.items():
            if event_name not in winning_times:
                continue

            for slot_index, slot_data in winning_times[event_name].items():
                winner_key, winner_points, all_entries = slot_data
                day, time = winner_key

                # Check if this event needs reassignment
                if (event_name, slot_index) in events_needing_reassignment:
                    # Event needs to find alternative time
                    log.info(f"Reassigning {event_name} slot {slot_index} from {winner_key}")
                    selected_entry = None
                    for candidate_key, candidate_points in all_entries:
                        if self._is_time_available(event_name, candidate_key, occupied_by, slot_index, adjusted_winning_times):
                            selected_entry = (candidate_key, candidate_points)
                            log.info(f"  Found alternative: {candidate_key[0]} at {candidate_key[1]} ({candidate_points} pts)")
                            # Mark this time as occupied
                            self._mark_time_occupied(event_name, candidate_key, occupied_by)
                            # Update adjusted_winning_times immediately so next slot can check against it
                            adjusted_winning_times[event_name][slot_index] = (selected_entry[0], selected_entry[1], all_entries)
                            break

                    if not selected_entry:
                        # Fallback to original
                        log.warning(f"  No alternative found! Keeping original time {winner_key}")
                        adjusted_winning_times[event_name][slot_index] = slot_data

        return adjusted_winning_times

    def _get_affected_days(self, event_name: str, day: str) -> list:
        """Get list of days affected by an event

        Args:
            event_name: Name of the event
            day: Day key from winning time

        Returns:
            List of day names affected
        """
        event_info = self.events[event_name]

        if event_info["type"] == "daily" or day == "Daily":
            return self.days_of_week
        elif event_info["type"] == "fixed_days":
            if day in self.days_of_week:
                return [day]
            else:
                return event_info.get("days", [])
        else:
            return [day] if day in self.days_of_week else []

    def _is_time_available(self, event_name: str, time_key: tuple, occupied_by: Dict, current_slot_index: Optional[int] = None, adjusted_winning_times: Optional[Dict] = None) -> bool:
        """Check if a time slot is available for an event

        Args:
            event_name: Name of the event
            time_key: (day, time) tuple
            occupied_by: Dictionary mapping slot keys to event names
            current_slot_index: Index of the slot being placed (for multi-slot events)
            adjusted_winning_times: Current winning times to check for same-event conflicts

        Returns:
            True if available, False otherwise
        """
        day, time = time_key
        event_info = self.events[event_name]
        affected_days = self._get_affected_days(event_name, day)

        # For multi-slot weekly events, check if another slot from the same event is already on this day
        if event_info.get("type") == "once" and event_info.get("slots", 1) > 1:
            if adjusted_winning_times and event_name in adjusted_winning_times:
                for slot_idx, slot_data in adjusted_winning_times[event_name].items():
                    # Don't check against the current slot being placed
                    if current_slot_index is not None and slot_idx == current_slot_index:
                        continue
                    winner_key, _, _ = slot_data
                    existing_day, existing_time = winner_key
                    # If same event already has a slot on this day, reject
                    if existing_day == day:
                        log.debug(f"    Rejected {time_key}: {event_name} slot {slot_idx} already on {existing_day} at {existing_time}")
                        return False

        from datetime import datetime, timedelta
        current_time = datetime.strptime(time, "%H:%M")
        duration = event_info.get("duration", 30)
        slots_needed = max(1, duration // 30)

        for affected_day in affected_days:
            for i in range(slots_needed):
                slot_time = current_time + timedelta(minutes=i * 30)
                slot_time_str = slot_time.strftime("%H:%M")
                slot_key = (affected_day, slot_time_str)

                if slot_key in occupied_by and occupied_by[slot_key] != event_name:
                    occupying_event = occupied_by[slot_key]
                    # Only Party can coexist with other events (for table splitting)
                    # Other events cannot share cells with each other
                    if event_name == 'Party' or occupying_event == 'Party':
                        continue
                    # Other events cannot share slots
                    return False

        return True

    def _mark_time_occupied(self, event_name: str, time_key: tuple, occupied_by: Dict):
        """Mark a time slot as occupied by an event

        Args:
            event_name: Name of the event
            time_key: (day, time) tuple
            occupied_by: Dictionary to update
        """
        day, time = time_key
        event_info = self.events[event_name]
        affected_days = self._get_affected_days(event_name, day)

        from datetime import datetime, timedelta
        current_time = datetime.strptime(time, "%H:%M")
        duration = event_info.get("duration", 30)
        slots_needed = max(1, duration // 30)

        for affected_day in affected_days:
            for i in range(slots_needed):
                slot_time = current_time + timedelta(minutes=i * 30)
                slot_time_str = slot_time.strftime("%H:%M")
                slot_key = (affected_day, slot_time_str)
                occupied_by[slot_key] = event_name

    def _time_to_sort_key(self, time_str: str) -> int:
        """Convert time string to sortable integer for sorting

        Args:
            time_str: Time in HH:MM format

        Returns:
            Integer representing minutes since 17:00 (start of event window)
        """
        hour, minute = map(int, time_str.split(':'))
        # Handle wraparound: times 00:00-02:59 are treated as next day
        if hour < 3:
            hour += 24
        # Convert to minutes since 17:00
        return (hour - 17) * 60 + minute

    def _calculate_weighted_points(self, voted_time: str, target_time: str, weighted: bool = True) -> int:
        """Calculate weighted points based on time difference

        Args:
            voted_time: Time the user voted for (HH:MM)
            target_time: Time to calculate points for (HH:MM)
            weighted: Whether to include weighted points for nearby times (default: True)

        Returns:
            Points: 5 for exact match, 2 for ±30min, 1 for ±60min, 0 otherwise.
            If weighted is False, returns 5 for exact match, 0 otherwise.
        """
        # Convert time strings to minutes since midnight (handles wrap-around)
        def time_to_minutes(time_str: str) -> int:
            """Convert HH:MM to minutes since midnight"""
            parts = time_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1])
            # Handle times after midnight (00:00, 01:00, etc.) as next day
            if hours < 17:  # Times 00:00-16:59 are considered next day
                hours += 24
            return hours * 60 + minutes

        voted_mins = time_to_minutes(voted_time)
        target_mins = time_to_minutes(target_time)

        # Calculate absolute difference in minutes
        diff_minutes = abs(target_mins - voted_mins)

        if diff_minutes == 0:
            return 5  # Exact match
        
        if not weighted:
            return 0
            
        elif diff_minutes == 30:
            return 2  # 30 minutes off
        elif diff_minutes == 60:
            return 1  # 1 hour off
        else:
            return 0  # Too far off

    def _is_time_blocked_for_event(self, time_str: str, duration: int, event_name: str) -> bool:
        """Check if a time slot would overlap with an event-specific blocked period

        Args:
            time_str: Start time in HH:MM format
            duration: Event duration in minutes
            event_name: Name of the event

        Returns:
            True if the time is blocked, False otherwise
        """
        # Check if this event has blocked times
        if event_name not in self.event_blocked_times:
            return False

        blocked = self.event_blocked_times[event_name]
        blocked_start_str = blocked["start"]
        blocked_end_str = blocked["end"]

        # Parse times - handle times past midnight
        def parse_time_to_minutes(time_str: str) -> int:
            """Convert HH:MM to minutes since start of day"""
            parts = time_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1])
            # Handle next-day times (00:00-02:00 should be treated as 24:00-26:00)
            if hours < 3:  # Assume times 00:00-02:59 are next day
                hours += 24
            return hours * 60 + minutes

        # Convert event start time to minutes
        event_start_mins = parse_time_to_minutes(time_str)
        event_end_mins = event_start_mins + duration

        # Convert blocked period to minutes
        blocked_start_mins = parse_time_to_minutes(blocked_start_str)
        blocked_end_mins = parse_time_to_minutes(blocked_end_str)

        # Check for overlap
        # Two ranges overlap if: start1 < end2 AND start2 < end1
        return event_start_mins < blocked_end_mins and blocked_start_mins < event_end_mins

    def generate_time_options(self, start_hour: int = 17, end_hour: int = 26, interval: int = 30, duration: int = 0, event_name: Optional[str] = None) -> List[str]:
        """Generate time options in HH:MM format

        Args:
            start_hour: Starting hour (default 17)
            end_hour: Ending hour (default 26, which represents 02:00 next day)
            interval: Interval in minutes (default 30)
            duration: Event duration in minutes (default 0). If > 0, filters out times that would extend past end_hour.
            event_name: Event name (optional). If specified, filters out times blocked for this event.

        Returns:
            List of time strings in HH:MM format (handles times past midnight as 00:00, 00:30, etc.)
        """
        times = []
        
        # Handle float start_hour (e.g., 20.5 for 20:30)
        current_hour = int(start_hour)
        current_minute = int((start_hour - current_hour) * 60)

        while current_hour < end_hour or (current_hour == end_hour and current_minute == 0):
            # Convert hours >= 24 to next-day format (24 -> 00, 25 -> 01, etc.)
            display_hour = current_hour if current_hour < 24 else current_hour - 24
            time_str = f"{display_hour:02d}:{current_minute:02d}"

            # If we've reached the end hour exactly, stop unless it's the very first entry
            if current_hour == end_hour and current_minute > 0:
                break
            
            # If duration is specified, check if event would complete before end_hour
            if duration > 0:
                # Calculate end time
                end_minute = current_minute + duration
                end_hour_calc = current_hour
                while end_minute >= 60:
                    end_minute -= 60
                    end_hour_calc += 1

                # Only include time if event ends at or before end_hour
                if end_hour_calc < end_hour or (end_hour_calc == end_hour and end_minute == 0):
                    # Check if this time is blocked for the specific event
                    if event_name and not self._is_time_blocked_for_event(time_str, duration, event_name):
                        times.append(time_str)
                    elif not event_name:
                        times.append(time_str)
            else:
                times.append(time_str)

            current_minute += interval
            if current_minute >= 60:
                current_minute = 0
                current_hour += 1

        return times

    def _time_ranges_overlap(self, start1: dt_time, end1: dt_time, start2: dt_time, end2: dt_time) -> bool:
        """Check if two time ranges overlap"""
        return start1 < end2 and start2 < end1

    def _get_event_time_range(self, event_name: str, start_time_str: str) -> Tuple[dt_time, dt_time]:
        """Get the start and end time for an event based on its duration"""
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        duration = self.events[event_name]["duration"]

        # Convert to datetime for calculation
        start_dt = datetime.combine(datetime.today(), start_time)
        end_dt = start_dt + timedelta(minutes=duration)

        return start_time, end_dt.time()

    def is_time_blocked(self, day: Optional[str], time_str: str, event_name: str) -> Tuple[bool, Optional[str]]:
        """Check if a time is in the blocked times list or event-specific blocked periods"""
        # First, check event-specific blocked times
        if event_name in self.event_blocked_times:
            blocked = self.event_blocked_times[event_name]
            if self._is_time_blocked_for_event(time_str, self.events[event_name]["duration"], event_name):
                return True, f"This time conflicts with {event_name}'s blocked period ({blocked['start']}-{blocked['end']})"

        # Then check day-specific blocked times (Guild Wars)
        if not day:
            # For daily events, check all days
            for blocked in self.blocked_times:
                blocked_start = datetime.strptime(blocked["start"], "%H:%M").time()
                blocked_end = datetime.strptime(blocked["end"], "%H:%M").time()
                event_start, event_end = self._get_event_time_range(event_name, time_str)

                if self._time_ranges_overlap(event_start, event_end, blocked_start, blocked_end):
                    return True, f"This time conflicts with a blocked period on {blocked['day']}"
        else:
            # For weekly events, only check the selected day
            for blocked in self.blocked_times:
                if blocked["day"] == day:
                    blocked_start = datetime.strptime(blocked["start"], "%H:%M").time()
                    blocked_end = datetime.strptime(blocked["end"], "%H:%M").time()
                    event_start, event_end = self._get_event_time_range(event_name, time_str)

                    if self._time_ranges_overlap(event_start, event_end, blocked_start, blocked_end):
                        return True, f"This time conflicts with a blocked period (Sat & Sun 20:30-22:00)"

        return False, None

    def check_time_conflict(
        self,
        user_selections: Dict,
        event_name: str,
        new_day: Optional[str],
        new_time: str,
        current_slot_index: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if a new selection conflicts with existing selections

        Args:
            user_selections: User's current selections
            event_name: Event being selected
            new_day: Day for new selection (None for daily events)
            new_time: Time for new selection
            current_slot_index: Index of current slot being edited (to skip self-check)

        Returns:
            (has_conflict: bool, conflict_message: Optional[str])
        """
        # First check if the time is blocked (skip for Party events)
        if event_name != "Party":
            is_blocked, block_msg = self.is_time_blocked(new_day, new_time, event_name)
            if is_blocked:
                return True, block_msg

        # Get time range for new event
        new_start, new_end = self._get_event_time_range(event_name, new_time)

        for existing_event, selection in user_selections.items():
            # Handle multi-slot selections
            slots_to_check = []
            if isinstance(selection, list):
                # Multi-slot event
                for idx, slot_data in enumerate(selection):
                    if slot_data:  # Slot might be None if not yet selected
                        # Skip checking current slot against itself
                        if existing_event == event_name and current_slot_index is not None and idx == current_slot_index:
                            continue
                        slots_to_check.append((slot_data, f"{existing_event} slot {idx + 1}"))
            else:
                # Single slot event (legacy or Party)
                if existing_event == event_name and current_slot_index is not None:
                    continue  # Skip checking against itself
                slots_to_check.append((selection, existing_event))

            for slot_data, slot_label in slots_to_check:
                existing_time = slot_data["time"]
                existing_day = slot_data.get("day")
                existing_start, existing_end = self._get_event_time_range(existing_event, existing_time)

                new_event_type = self.events[event_name]["type"]
                existing_event_type = self.events[existing_event]["type"]

                # Skip conflict checking if either event is Party (daily events don't conflict with others)
                if event_name == "Party" or existing_event == "Party":
                    continue

                # Daily events conflict with all events if times overlap
                if new_event_type == "daily":
                    if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                        return True, f"This time conflicts with your {slot_label} selection"

                elif existing_event_type == "daily":
                    # Any event conflicts with daily events if time ranges overlap
                    if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                        if new_day:
                            return True, f"This time conflicts with your {slot_label} selection on {new_day}"
                        else:
                            return True, f"This time conflicts with your {slot_label} selection"

                # Fixed-day events conflict with weekly/fixed-day events on shared days
                elif new_event_type == "fixed_days":
                    new_event_days = self.events[event_name]["days"]

                    if existing_event_type == "fixed_days":
                        # For multi-slot fixed-day events, compare the specific days for each slot
                        # (new_day is the day for the slot being selected, existing_day is from the existing slot)
                        if new_day and existing_day:
                            # Both have specific days - only conflict if same day and times overlap
                            if new_day == existing_day and self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                                return True, f"This time conflicts with your {slot_label} selection"
                        else:
                            # Fallback to checking event day lists if specific days aren't set
                            existing_event_days = self.events[existing_event]["days"]
                            shared_days = set(new_event_days) & set(existing_event_days)
                            if shared_days and self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                                return True, f"This time conflicts with your {slot_label} selection"
                    elif existing_event_type == "once":
                        # Check if the existing weekly event's day is in our fixed days
                        if existing_day in new_event_days:
                            if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                                return True, f"This time conflicts with your {slot_label} selection on {existing_day}"

                elif existing_event_type == "fixed_days":
                    # Weekly event vs fixed-day event
                    existing_event_days = self.events[existing_event]["days"]
                    if new_day in existing_event_days:
                        if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                            return True, f"This conflicts with your {slot_label} selection on {new_day}"

                else:
                    # Both are weekly events - only conflict if same day and time ranges overlap
                    if new_day and existing_day and new_day == existing_day:
                        if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                            return True, f"This conflicts with your {slot_label} selection on {existing_day}"

        return False, None

# Force update
