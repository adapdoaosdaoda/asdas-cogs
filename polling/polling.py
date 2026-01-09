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

        # Event definitions
        self.events = {
            "Party": {
                "type": "daily",
                "time_range": (18, 24),  # 18:00 to 24:00
                "interval": 30,  # 30 minute intervals
                "duration": 10,  # 10 minutes
                "color": discord.Color.green(),
                "emoji": "🎉"
            },
            "Breaking Army #1": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "duration": 60,  # 1 hour
                "color": discord.Color.blue(),
                "emoji": "⚔️"
            },
            "Breaking Army #2": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "duration": 60,  # 1 hour
                "color": discord.Color.blue(),
                "emoji": "⚔️"
            },
            "Showdown #1": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "duration": 60,  # 1 hour
                "color": discord.Color.red(),
                "emoji": "🏆"
            },
            "Showdown #2": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "duration": 60,  # 1 hour
                "color": discord.Color.red(),
                "emoji": "🏆"
            }
        }

        self.days_of_week = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        ]

        # Blocked time slots: Saturday 20:30 - 22:30
        self.blocked_times = [
            {"day": "Saturday", "start": "20:30", "end": "22:30"}
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

            for user_id, user_selections in selections.items():
                if event_name in user_selections:
                    selection = user_selections[event_name]

                    # Format the selection string
                    if self.events[event_name]["type"] == "daily":
                        key = selection["time"]
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
                    "🎉 **Party** - Daily (10 min)\n"
                    "⚔️ **Breaking Army #1** - Weekly (1 hour)\n"
                    "⚔️ **Breaking Army #2** - Weekly (1 hour)\n"
                    "🏆 **Showdown #1** - Weekly (1 hour)\n"
                    "🏆 **Showdown #2** - Weekly (1 hour)\n\n"
                    "⚠️ Saturday 20:30-22:30 is blocked\n"
                    "⚠️ Events cannot have conflicting times"
                ),
                inline=False
            )
            return embed

        # Calculate winning times (most votes) for each event
        winning_times = {}
        for event_name in self.events.keys():
            vote_counts = {}

            for user_id, user_selections in selections.items():
                if event_name in user_selections:
                    selection = user_selections[event_name]

                    if self.events[event_name]["type"] == "daily":
                        key = ("Daily", selection["time"])
                    else:
                        key = (selection.get("day", "Unknown"), selection["time"])

                    vote_counts[key] = vote_counts.get(key, 0) + 1

            if vote_counts:
                # Get the selection(s) with most votes
                max_votes = max(vote_counts.values())
                winners = [k for k, v in vote_counts.items() if v == max_votes]
                winning_times[event_name] = (winners, max_votes)

        # Create calendar view
        calendar_lines = []
        for day in self.days_of_week:
            day_events = []

            for event_name, event_info in self.events.items():
                if event_name not in winning_times:
                    continue

                winners, votes = winning_times[event_name]
                emoji = event_info["emoji"]

                # Check if this event has a winner on this day
                for winner_day, winner_time in winners:
                    if event_info["type"] == "daily" or winner_day == day:
                        duration = event_info["duration"]
                        if event_info["type"] == "daily":
                            day_events.append(f"{emoji}{winner_time} ({votes}v)")
                        else:
                            day_events.append(f"{emoji}{winner_time} ({votes}v)")

            if day_events:
                calendar_lines.append(f"**{day[:3]}**: {' | '.join(day_events)}")
            else:
                calendar_lines.append(f"**{day[:3]}**: —")

        if calendar_lines:
            embed.add_field(
                name="📊 Current Leading Times (votes)",
                value="\n".join(calendar_lines),
                inline=False
            )

        # Add summary of each event
        summary_lines = []
        for event_name in self.events.keys():
            emoji = self.events[event_name]["emoji"]
            if event_name in winning_times:
                winners, votes = winning_times[event_name]
                if self.events[event_name]["type"] == "daily":
                    time_str = winners[0][1]
                    summary_lines.append(f"{emoji} **{event_name}**: {time_str} ({votes} votes)")
                else:
                    winner_strs = [f"{day} {time}" for day, time in winners]
                    summary_lines.append(f"{emoji} **{event_name}**: {winner_strs[0]} ({votes} votes)")
            else:
                summary_lines.append(f"{emoji} **{event_name}**: No votes yet")

        embed.add_field(
            name="🏆 Current Winners",
            value="\n".join(summary_lines),
            inline=False
        )

        embed.set_footer(text=f"Total voters: {len(selections)}")

        return embed

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
                        return True, f"This time conflicts with a blocked period (Sat 20:30-22:30)"

        return False, None

    def check_time_conflict(
        self,
        user_selections: Dict,
        event_name: str,
        new_day: Optional[str],
        new_time: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if a new selection conflicts with existing selections

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
            if existing_event == event_name:
                # Skip checking against itself
                continue

            existing_time = selection["time"]
            existing_day = selection.get("day")
            existing_start, existing_end = self._get_event_time_range(existing_event, existing_time)

            # Party is daily, so it conflicts with any event on any day if times overlap
            if self.events[event_name]["type"] == "daily":
                # Party conflicts with all events if time ranges overlap
                if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                    return True, f"This time conflicts with your {existing_event} selection"

            elif self.events[existing_event]["type"] == "daily":
                # Any event conflicts with Party if time ranges overlap
                if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                    if new_day:
                        return True, f"This time conflicts with your Party selection on {new_day}"
                    else:
                        return True, f"This time conflicts with your Party selection"

            else:
                # Both are weekly events - only conflict if same day and time ranges overlap
                if new_day and existing_day and new_day == existing_day:
                    if self._time_ranges_overlap(new_start, new_end, existing_start, existing_end):
                        return True, f"This conflicts with your {existing_event} selection on {existing_day}"

        return False, None
