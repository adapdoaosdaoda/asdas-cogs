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
from pathlib import Path
import importlib

from .views import EventPollView
from . import calendar_renderer


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
        )

        # Event definitions (ordered: Hero's Realm, Sword Trial, Party, Breaking Army, Showdown)
        # Priority order for calendar display (higher number = higher priority)
        self.events = {
            "Hero's Realm": {
                "type": "fixed_days",
                "days": ["Wednesday", "Friday", "Saturday", "Sunday"],
                "time_range": (17, 26),  # 17:00 to 02:00 (26 = 02:00 next day)
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 4,  # 4 slots: one for each day (Wed, Fri, Sat, Sun)
                "color": discord.Color.greyple(),
                "emoji": "🛡️",
                "priority": 5  # Highest priority
            },
            "Sword Trial": {
                "type": "fixed_days",
                "days": ["Wednesday", "Friday", "Saturday", "Sunday"],
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 4,  # 4 slots: one for each day (Wed, Fri, Sat, Sun)
                "color": discord.Color.greyple(),
                "emoji": "⚔️",
                "priority": 4
            },
            "Party": {
                "type": "daily",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,  # 30 minute intervals
                "duration": 10,  # 10 minutes
                "slots": 1,  # Single time slot
                "color": discord.Color.green(),
                "emoji": "🎉",
                "priority": 2
            },
            "Breaking Army": {
                "type": "once",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color.blue(),
                "emoji": "⚡",
                "priority": 3
            },
            "Showdown": {
                "type": "once",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color.red(),
                "emoji": "🏆",
                "priority": 1  # Lowest priority
            }
        }

        # Guild Wars - blocked time event (Sat & Sun 20:30-22:00)
        self.guild_wars_emoji = "🏰"

        self.days_of_week = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        ]

        # Blocked time slots: Saturday and Sunday 20:30 - 22:00
        self.blocked_times = [
            {"day": "Saturday", "start": "20:30", "end": "22:00"},
            {"day": "Sunday", "start": "20:30", "end": "22:00"}
        ]

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
        await self.bot.wait_until_ready()
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            polls = guild_data.get("polls", {})
            for poll_id, poll_data in polls.items():
                await self._restore_poll_view(guild, poll_data, poll_id)

        self.backup_task.start()
        self.weekly_results_update.start()
        self.weekly_calendar_update.start()

    def cog_unload(self):
        """Called when the cog is unloaded"""
        self.backup_task.cancel()
        self.weekly_results_update.cancel()
        self.weekly_calendar_update.cancel()

    def _get_embed_color(self, guild: discord.Guild) -> discord.Color:
        """Get the bot's color in the guild, or fallback to default"""
        try:
            if guild and guild.me:
                # Use the bot's top role color if it's not default
                if guild.me.color != discord.Color.default():
                    return guild.me.color
        except:
            pass
        # Fallback to default color
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
        except Exception as e:
            # Silently fail if we can't restore the view
            print(f"Could not restore poll view for poll {poll_id}: {e}")

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

            for slot_index, slot_data in event_slots.items():
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
                        if event_info["type"] == "daily":
                            key = selection["time"]
                        elif event_info["type"] == "fixed_days":
                            days_str = ", ".join([d[:3] for d in event_info["days"]])
                            key = f"{selection['time']} ({days_str})"
                        else:
                            key = f"{selection['day']} at {selection['time']}"

                        if key not in event_results:
                            event_results[key] = []
                        event_results[key].append(f"<@{user_id}>")

            # Add to embed
            if event_results:
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
        embed, calendar_file = await self._create_weekly_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Send the weekly calendar message with image
        calendar_msg = await ctx.send(embed=embed, file=calendar_file)

        # Store weekly calendar message ID in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
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
        embed, calendar_file = await self._create_weekly_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Update the message
        await message.edit(embed=embed, attachments=[calendar_file])

        # Store weekly calendar message ID in poll data for auto-updating
        async with self.config.guild(ctx.guild).polls() as polls:
            if poll_id in polls:
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

        await ctx.send(f"✅ Successfully overwrote message with results: {message.jump_url}")

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
            color=self._get_embed_color(guild)
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

    async def _create_weekly_calendar_embed(self, poll_data: Dict, guild_id: int, poll_id: str) -> Tuple[discord.Embed, discord.File]:
        """Create a weekly calendar embed with image and poll link (updates only on Monday 10AM)

        Returns:
            Tuple of (embed, file) where file is the calendar image
        """
        title = poll_data["title"]
        channel_id = poll_data["channel_id"]
        message_id = poll_data["message_id"]

        # Get guild for color
        guild = self.bot.get_guild(guild_id)

        # Create embed
        embed = discord.Embed(
            title="📅 Event Calendar",
            description=f"[Click here to vote in the poll](https://discord.com/channels/{guild_id}/{channel_id}/{message_id})",
            color=self._get_embed_color(guild)
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

        return embed, calendar_file

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

    async def _update_weekly_calendar_messages(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Update all weekly calendar messages associated with this poll"""
        weekly_calendar_messages = poll_data.get("weekly_calendar_messages", [])

        for cal_msg_data in weekly_calendar_messages:
            try:
                channel = guild.get_channel(cal_msg_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(cal_msg_data["message_id"])
                    updated_embed, calendar_file = await self._create_weekly_calendar_embed(poll_data, guild.id, poll_id)
                    await message.edit(embed=updated_embed, attachments=[calendar_file])
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
            description="Click an event button below to vote for your preferred times.",
            color=self._get_embed_color(guild)
        )

        # Get poll data if it exists
        polls = await self.config.guild_from_id(guild_id).polls()
        selections = {}
        if poll_id and poll_id in polls:
            selections = polls[poll_id].get("selections", {})

        # Show event info at the top
        embed.add_field(
            name="📋 Events",
            value=(
                "🛡️ **Hero's Realm** - Wed/Fri/Sat/Sun (30 min)\n"
                "⚔️ **Sword Trial** - Wed/Fri/Sat/Sun (30 min)\n"
                "🎉 **Party** - Daily (10 min)\n"
                "⚡ **Breaking Army** - Weekly (60 min, 2 slots)\n"
                "🏆 **Showdown** - Weekly (60 min, 2 slots)\n\n"
                "🏰 **Guild War** - Sat & Sun 20:30-22:00 (blocked)"
            ),
            inline=False
        )

        # Calculate winning times (most votes) for each event and slot
        winning_times = {}
        for event_name, event_info in self.events.items():
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
                                if event_info["type"] == "daily":
                                    key = ("Daily", selection["time"])
                                elif event_info["type"] == "fixed_days":
                                    key = ("Fixed", selection["time"])
                                else:
                                    key = (selection.get("day", "Unknown"), selection["time"])
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
            "• 3 points: 30 minutes before/after your voted time",
            "• 1 point: 1 hour before/after your voted time",
            "• For Breaking Army & Showdown: +1 point to same time on all other days",
            "",
            "**Event priority and tiebreak rules:**",
            "• Priority order: Hero's Realm (5) > Sword Trial (4) > Party (3) > Breaking Army (2) > Showdown (1)",
            "• When events conflict: Higher priority gets +5 bonus points",
            "• After bonus, higher points wins the time slot",
            "• If still tied: Breaking Army/Showdown prefer Saturday, then later time; others prefer later time",
            "",
            "**Click a button below to see that event's votes:**",
        ]
        return "\n".join(summary_lines)

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
            "• 3 points: 30 minutes before/after your voted time",
            "• 1 point: 1 hour before/after your voted time",
            "• For Breaking Army & Showdown: +1 point to same time on all other days",
            "",
            "**Event priority and tiebreak rules:**",
            "• Priority order: Hero's Realm (5) > Sword Trial (4) > Party (3) > Breaking Army (2) > Showdown (1)",
            "• When events conflict: Higher priority gets +5 bonus points",
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
        winning_times = {}

        # Generate all possible times
        all_times = self.generate_time_options(17, 26, 30)

        for event_name, event_info in self.events.items():
            num_slots = event_info["slots"]
            winning_times[event_name] = {}

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
                        for target_time in all_times:
                            points = self._calculate_weighted_points(voted_time, target_time)
                            if points > 0:
                                key = (voted_day, target_time)
                                point_totals[key] = point_totals.get(key, 0) + points

                        # Special case: 1 point to same time on all other days
                        for day in self.days_of_week:
                            if day != voted_day:
                                key = (day, voted_time)
                                point_totals[key] = point_totals.get(key, 0) + 1

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
                                voted_time = selection["time"]
                                voted_day = selection.get("day")

                        if not voted_time:
                            continue

                        # Calculate points for all possible times
                        if event_info["type"] == "daily":
                            # Daily events
                            for target_time in all_times:
                                points = self._calculate_weighted_points(voted_time, target_time)
                                if points > 0:
                                    key = ("Daily", target_time)
                                    point_totals[key] = point_totals.get(key, 0) + points

                        elif event_info["type"] == "fixed_days":
                            # Fixed-day events
                            if event_info["slots"] > 1 and voted_day:
                                # Multi-slot: specific day
                                for target_time in all_times:
                                    points = self._calculate_weighted_points(voted_time, target_time)
                                    if points > 0:
                                        key = (voted_day, target_time)
                                        point_totals[key] = point_totals.get(key, 0) + points
                            else:
                                # Single slot for all fixed days
                                for target_time in all_times:
                                    points = self._calculate_weighted_points(voted_time, target_time)
                                    if points > 0:
                                        key = ("Fixed", target_time)
                                        point_totals[key] = point_totals.get(key, 0) + points

                        else:
                            # Weekly events (single slot only, legacy path)
                            if not voted_day:
                                continue

                            # Main points for the voted day
                            for target_time in all_times:
                                points = self._calculate_weighted_points(voted_time, target_time)
                                if points > 0:
                                    key = (voted_day, target_time)
                                    point_totals[key] = point_totals.get(key, 0) + points

                            # Special case: 1 point to same time on all other days
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

        # Resolve conflicts between events based on priority
        winning_times = self._resolve_event_conflicts(winning_times)

        return winning_times

    def _resolve_event_conflicts(self, winning_times: Dict) -> Dict:
        """Resolve conflicts between events based on priority bonus system

        When events conflict at the same time:
        - Higher priority events get +5 point bonus
        - After bonus, higher points wins
        - If still tied, use regular tiebreak rules

        Args:
            winning_times: Initial winning times from voting

        Returns:
            Adjusted winning times with conflicts resolved
        """
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
                    for candidate in candidates:
                        occupied_by[slot_key] = candidate['event_name']
                    # Don't mark anyone for reassignment - they can coexist
                else:
                    # Standard conflict resolution when Party is not involved
                    # Apply priority bonuses and resolve
                    max_priority = max(c['priority'] for c in candidates)

                    for candidate in candidates:
                        # Higher priority gets +5 bonus
                        if candidate['priority'] == max_priority:
                            candidate['adjusted_points'] = candidate['points'] + 5
                        else:
                            candidate['adjusted_points'] = candidate['points']

                    # Sort by adjusted points (desc), then by priority (desc), then by time (desc for tiebreak)
                    candidates.sort(key=lambda x: (-x['adjusted_points'], -x['priority'], -self._time_to_sort_key(x['start_time'])))

                    winner = candidates[0]
                    occupied_by[slot_key] = winner['event_name']

                    # Mark losers for reassignment
                    for loser in candidates[1:]:
                        events_needing_reassignment.add((loser['event_name'], loser['slot_index']))

        # Assign winning times to events
        for event_name, event_info in self.events.items():
            if event_name not in winning_times:
                continue

            adjusted_winning_times[event_name] = {}

            for slot_index, slot_data in winning_times[event_name].items():
                winner_key, winner_points, all_entries = slot_data
                day, time = winner_key

                # Check if this event needs reassignment
                if (event_name, slot_index) in events_needing_reassignment:
                    # Event needs to find alternative time
                    selected_entry = None
                    for candidate_key, candidate_points in all_entries:
                        if self._is_time_available(event_name, candidate_key, occupied_by):
                            selected_entry = (candidate_key, candidate_points)
                            # Mark this time as occupied
                            self._mark_time_occupied(event_name, candidate_key, occupied_by)
                            break

                    if selected_entry:
                        adjusted_winning_times[event_name][slot_index] = (selected_entry[0], selected_entry[1], all_entries)
                    else:
                        # Fallback to original
                        adjusted_winning_times[event_name][slot_index] = slot_data
                else:
                    # Event won its preferred time
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

    def _is_time_available(self, event_name: str, time_key: tuple, occupied_by: Dict) -> bool:
        """Check if a time slot is available for an event

        Args:
            event_name: Name of the event
            time_key: (day, time) tuple
            occupied_by: Dictionary mapping slot keys to event names

        Returns:
            True if available, False otherwise
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

    def _calculate_weighted_points(self, voted_time: str, target_time: str) -> int:
        """Calculate weighted points based on time difference

        Args:
            voted_time: Time the user voted for (HH:MM)
            target_time: Time to calculate points for (HH:MM)

        Returns:
            Points: 5 for exact match, 3 for ±30min, 1 for ±60min, 0 otherwise
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
        elif diff_minutes == 30:
            return 3  # 30 minutes off
        elif diff_minutes == 60:
            return 1  # 1 hour off
        else:
            return 0  # Too far off

    def generate_time_options(self, start_hour: int = 17, end_hour: int = 26, interval: int = 30, duration: int = 0) -> List[str]:
        """Generate time options in HH:MM format

        Args:
            start_hour: Starting hour (default 17)
            end_hour: Ending hour (default 26, which represents 02:00 next day)
            interval: Interval in minutes (default 30)
            duration: Event duration in minutes (default 0). If > 0, filters out times that would extend past end_hour.

        Returns:
            List of time strings in HH:MM format (handles times past midnight as 00:00, 00:30, etc.)
        """
        times = []
        current_hour = start_hour
        current_minute = 0

        while current_hour < end_hour:
            # Convert hours >= 24 to next-day format (24 -> 00, 25 -> 01, etc.)
            display_hour = current_hour if current_hour < 24 else current_hour - 24
            time_str = f"{display_hour:02d}:{current_minute:02d}"

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
        """Check if a time is in the blocked times list"""
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
