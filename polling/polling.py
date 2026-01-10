from redbot.core import commands, Config
from redbot.core.bot import Red
import discord
from typing import Optional, Dict, List, Tuple
from datetime import datetime, time as dt_time, timedelta

from .views import EventPollView


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
        self.events = {
            "Hero's Realm": {
                "type": "fixed_days",
                "days": ["Wednesday", "Friday", "Saturday", "Sunday"],
                "time_range": (18, 24),
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 1,
                "color": discord.Color.greyple(),
                "emoji": "🛡️"
            },
            "Sword Trial": {
                "type": "fixed_days",
                "days": ["Wednesday", "Friday", "Saturday", "Sunday"],
                "time_range": (18, 24),
                "interval": 30,
                "duration": 30,  # 30 minutes
                "slots": 1,
                "color": discord.Color.greyple(),
                "emoji": "⚔️"
            },
            "Party": {
                "type": "daily",
                "time_range": (18, 24),  # 18:00 to 24:00
                "interval": 30,  # 30 minute intervals
                "duration": 10,  # 10 minutes
                "slots": 1,  # Single time slot
                "color": discord.Color.green(),
                "emoji": "🎉"
            },
            "Breaking Army": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color.blue(),
                "emoji": "⚡"
            },
            "Showdown": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color.red(),
                "emoji": "🏆"
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

    @eventpoll.command(name="results")
    async def show_results(self, ctx: commands.Context, message_id: int):
        """Show the results of a poll

        Example: [p]eventpoll results 123456789
        """
        poll_id = str(message_id)
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
            color=discord.Color.green()
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
    async def end_poll(self, ctx: commands.Context, message_id: int):
        """End a poll and remove it from the database

        Example: [p]eventpoll end 123456789
        """
        poll_id = str(message_id)
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
    async def clear_user_votes(self, ctx: commands.Context, message_id: int, user: discord.Member):
        """Clear a user's votes from a poll

        Example: [p]eventpoll clear 123456789 @user
        """
        poll_id = str(message_id)
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

    async def _create_poll_embed(self, title: str, guild_id: int, poll_id: str) -> discord.Embed:
        """Create calendar-style embed showing winning times"""
        embed = discord.Embed(
            title=f"📅 {title}",
            description="Vote for your preferred times by clicking the buttons below!",
            color=discord.Color.blue()
        )

        # Get poll data if it exists
        polls = await self.config.guild_from_id(guild_id).polls()
        selections = {}
        if poll_id and poll_id in polls:
            selections = polls[poll_id].get("selections", {})

        if not selections:
            # No votes yet, show event info
            embed.add_field(
                name="📋 Events",
                value=(
                    "🛡️ **Hero's Realm** - Wed/Fri/Sat/Sun (30 min, 1 slot)\n"
                    "⚔️ **Sword Trial** - Wed/Fri/Sat/Sun (30 min, 1 slot)\n"
                    "🎉 **Party** - Daily (10 min, 1 slot)\n"
                    "⚡ **Breaking Army** - Weekly (1 hour, 2 slots)\n"
                    "🏆 **Showdown** - Weekly (1 hour, 2 slots)\n\n"
                    "🏰 **Guild Wars** - Sat & Sun 20:30-22:00 (blocked)\n"
                    "⚠️ Events cannot have conflicting times"
                ),
                inline=False
            )
            return embed

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

        # Create visual calendar table
        calendar_table = self._create_calendar_table(winning_times)
        if calendar_table:
            embed.add_field(
                name="📊 Weekly Calendar View",
                value=calendar_table,
                inline=False
            )

        # Add summary of each event
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

        embed.add_field(
            name="🏆 Current Winners",
            value="\n".join(summary_lines),
            inline=False
        )

        embed.set_footer(text=f"Total voters: {len(selections)}")

        return embed

    def _create_calendar_table(self, winning_times: Dict) -> str:
        """Create a visual Unicode calendar table showing the weekly schedule"""
        # Build a data structure: {time: {day: [emojis]}}
        schedule = {}
        times = self.generate_time_options(18, 24, 30)

        for time_slot in times:
            schedule[time_slot] = {day: [] for day in self.days_of_week}

        # Populate schedule with winning events
        for event_name, event_info in self.events.items():
            emoji = event_info["emoji"]
            event_slots = winning_times.get(event_name, {})

            for slot_index, slot_winners in event_slots.items():
                winners, votes = slot_winners

                for winner_day, winner_time in winners:
                    if event_info["type"] == "daily":
                        # Daily events appear on all days
                        for day in self.days_of_week:
                            if event_info["slots"] > 1:
                                schedule[winner_time][day].append(f"{emoji}{slot_index + 1}")
                            else:
                                schedule[winner_time][day].append(emoji)
                    elif event_info["type"] == "fixed_days":
                        # Fixed-day events appear on their configured days
                        for day in event_info["days"]:
                            if event_info["slots"] > 1:
                                schedule[winner_time][day].append(f"{emoji}{slot_index + 1}")
                            else:
                                schedule[winner_time][day].append(emoji)
                    else:
                        # Weekly events appear only on their specific day
                        if event_info["slots"] > 1:
                            schedule[winner_time][winner_day].append(f"{emoji}{slot_index + 1}")
                        else:
                            schedule[winner_time][winner_day].append(emoji)

        # Add Guild Wars emoji to blocked time slots
        for blocked in self.blocked_times:
            blocked_day = blocked["day"]
            blocked_start = blocked["start"]
            blocked_end = blocked["end"]

            # Parse blocked times
            start_time = datetime.strptime(blocked_start, "%H:%M")
            end_time = datetime.strptime(blocked_end, "%H:%M")

            # Add Guild Wars emoji to all time slots in the blocked range
            for time_slot in times:
                slot_time = datetime.strptime(time_slot, "%H:%M")
                # Check if this time slot is within the blocked range (inclusive start, exclusive end)
                if start_time <= slot_time < end_time:
                    schedule[time_slot][blocked_day].append(self.guild_wars_emoji)

        # Build the table using code block for monospace formatting
        lines = []

        # Header row
        lines.append("```")
        header = "Time  │ Mon │ Tue │ Wed │ Thu │ Fri │ Sat │ Sun"
        lines.append(header)
        lines.append("─" * len(header))

        # Data rows - only show rows with events
        for time_slot in times:
            row_data = schedule[time_slot]
            has_events = any(row_data.values())

            if has_events:
                row = f"{time_slot} │"
                for day in self.days_of_week:
                    events = row_data[day]
                    if events:
                        # Join multiple events with space
                        cell = "".join(events[:2])  # Limit to 2 events per cell
                    else:
                        cell = "  "
                    row += f" {cell:3} │"
                lines.append(row)

        lines.append("```")

        return "\n".join(lines) if len(lines) > 3 else ""

    def generate_time_options(self, start_hour: int = 18, end_hour: int = 24, interval: int = 30) -> List[str]:
        """Generate time options in HH:MM format"""
        times = []
        current_hour = start_hour
        current_minute = 0

        while current_hour < end_hour or (current_hour == end_hour and current_minute == 0):
            times.append(f"{current_hour:02d}:{current_minute:02d}")

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
        # First check if the time is blocked
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
                        # Check if any days overlap
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
