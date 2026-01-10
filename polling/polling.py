from redbot.core import commands, Config
from redbot.core.bot import Red
import discord
from typing import Optional, Dict, List, Tuple, Union
from datetime import datetime, time as dt_time, timedelta
import os
import tempfile
import re

from .views import EventPollView
from .calendar_renderer import CalendarRenderer


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
                "priority": 3
            },
            "Breaking Army": {
                "type": "once",
                "time_range": (17, 26),  # 17:00 to 02:00
                "interval": 30,
                "duration": 60,  # 1 hour
                "slots": 2,  # Two weekly slots
                "color": discord.Color.blue(),
                "emoji": "⚡",
                "priority": 2
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
        self.calendar_renderer = CalendarRenderer(timezone=self.timezone_display)

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
            {event_name: {day: time}}
        """
        calendar_data = {}

        for event_name, event_info in self.events.items():
            calendar_data[event_name] = {}
            event_slots = winning_times.get(event_name, {})

            for slot_index, slot_data in event_slots.items():
                if not slot_data:
                    continue

                winner_key, points, all_entries = slot_data
                winner_day, winner_time = winner_key

                if event_info["type"] == "daily":
                    # Daily events appear on all days
                    for day in self.days_of_week:
                        calendar_data[event_name][day] = winner_time
                elif event_info["type"] == "fixed_days":
                    # Fixed-day events
                    if event_info["slots"] > 1:
                        # Multi-slot: winner_day is the specific day
                        calendar_data[event_name][winner_day] = winner_time
                    else:
                        # Single slot: appears on all configured days
                        for day in event_info["days"]:
                            calendar_data[event_name][day] = winner_time
                else:
                    # Weekly events appear only on their specific day
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
            color=discord.Color(0xcb4449)
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
        embed, calendar_file = await self._create_calendar_embed(poll_data, ctx.guild.id, poll_id)

        # Send the calendar message with image
        calendar_msg = await ctx.send(embed=embed, file=calendar_file)

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

    async def _create_calendar_embed(self, poll_data: Dict, guild_id: int, poll_id: str) -> Tuple[discord.Embed, discord.File]:
        """Create a calendar-only embed with image and poll link

        Returns:
            Tuple of (embed, file) where file is the calendar image
        """
        title = poll_data["title"]
        channel_id = poll_data["channel_id"]
        message_id = poll_data["message_id"]

        # Create embed
        embed = discord.Embed(
            title="📅 Event Calendar",
            description=f"[Click here to vote in the poll](https://discord.com/channels/{guild_id}/{channel_id}/{message_id})",
            color=discord.Color(0xcb4449)
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

        # Footer removed - timestamp and voter count now shown in calendar image

        return embed, calendar_file

    async def _update_calendar_messages(self, guild: discord.Guild, poll_data: Dict, poll_id: str):
        """Update all calendar messages associated with this poll"""
        calendar_messages = poll_data.get("calendar_messages", [])

        for cal_msg_data in calendar_messages:
            try:
                channel = guild.get_channel(cal_msg_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(cal_msg_data["message_id"])
                    updated_embed, calendar_file = await self._create_calendar_embed(poll_data, guild.id, poll_id)
                    await message.edit(embed=updated_embed, attachments=[calendar_file])
            except Exception:
                # Silently fail if we can't update a calendar message
                pass

    async def _create_poll_embed(self, title: str, guild_id: int, poll_id: str) -> discord.Embed:
        """Create calendar-style embed showing winning times"""
        embed = discord.Embed(
            title=f"📅 {title}",
            description="Vote for your preferred times by clicking the buttons below!",
            color=discord.Color(0xcb4449)
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

        embed.set_footer(text=f"Total voters: {len(selections)}")

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
            "• Priority order: Hero's Realm > Sword Trial > Breaking Army > Showdown (Party is separate)",
            "• Tiebreaker (same points): Breaking Army/Showdown prefer Saturday, then later time",
            "• Tiebreaker (other events): Later time wins",
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
            "• Priority order: Hero's Realm > Sword Trial > Breaking Army > Showdown (Party is separate)",
            "• Tiebreaker (same points): Breaking Army/Showdown prefer Saturday, then later time",
            "• Tiebreaker (other events): Later time wins",
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
        """Resolve conflicts between events based on priority

        Higher priority events get their preferred time.
        Lower priority events must pick next best non-conflicting time.

        Args:
            winning_times: Initial winning times from voting

        Returns:
            Adjusted winning times with conflicts resolved
        """
        # Sort events by priority (highest first)
        sorted_events = sorted(
            self.events.items(),
            key=lambda x: x[1].get("priority", 0),
            reverse=True
        )

        # Track occupied time slots: {day: [(start_time, end_time, event_name)]}
        occupied_slots = {day: [] for day in self.days_of_week}
        occupied_slots["Daily"] = []  # For daily events

        adjusted_winning_times = {}

        for event_name, event_info in sorted_events:
            if event_name not in winning_times:
                continue

            adjusted_winning_times[event_name] = {}

            for slot_index, slot_data in winning_times[event_name].items():
                winner_key, winner_points, all_entries = slot_data

                # Try to find a non-conflicting time from the sorted entries
                selected_entry = None
                for candidate_key, candidate_points in all_entries:
                    if self._check_event_conflict_with_occupied(
                        event_name, candidate_key, occupied_slots
                    ):
                        # This time conflicts, try next
                        continue
                    else:
                        # Found a non-conflicting time
                        selected_entry = (candidate_key, candidate_points)
                        break

                if selected_entry:
                    final_key, final_points = selected_entry
                    # Add this time to occupied slots
                    self._add_to_occupied_slots(event_name, final_key, occupied_slots)
                    # Store the adjusted winning time
                    adjusted_winning_times[event_name][slot_index] = (final_key, final_points, all_entries)
                else:
                    # No non-conflicting time found, keep original (shouldn't happen often)
                    adjusted_winning_times[event_name][slot_index] = slot_data

        return adjusted_winning_times

    def _check_event_conflict_with_occupied(
        self, event_name: str, time_key: tuple, occupied_slots: Dict
    ) -> bool:
        """Check if an event's time conflicts with already-occupied slots

        Args:
            event_name: Name of the event
            time_key: (day, time) tuple
            occupied_slots: Dictionary of occupied time slots

        Returns:
            True if conflict exists, False otherwise
        """
        day, time = time_key
        event_info = self.events[event_name]

        # Get time range for this event
        event_start, event_end = self._get_event_time_range(event_name, time)

        # Determine which days this event affects
        affected_days = []
        if event_info["type"] == "daily" or day == "Daily":
            affected_days = self.days_of_week
        elif event_info["type"] == "fixed_days":
            if day in self.days_of_week:
                # Multi-slot fixed-day event with specific day
                affected_days = [day]
            else:
                # Single-slot fixed-day event (day = "Fixed")
                affected_days = event_info.get("days", [])
        else:
            # Weekly event - specific day only
            affected_days = [day] if day in self.days_of_week else []

        # Check for conflicts on each affected day
        for check_day in affected_days:
            # Check against daily events
            for occupied_start, occupied_end, occupied_event in occupied_slots.get("Daily", []):
                if self._time_ranges_overlap(event_start, event_end, occupied_start, occupied_end):
                    return True

            # Check against events on this specific day
            for occupied_start, occupied_end, occupied_event in occupied_slots.get(check_day, []):
                if self._time_ranges_overlap(event_start, event_end, occupied_start, occupied_end):
                    return True

        return False

    def _add_to_occupied_slots(
        self, event_name: str, time_key: tuple, occupied_slots: Dict
    ):
        """Add an event's time to the occupied slots tracker

        Args:
            event_name: Name of the event
            time_key: (day, time) tuple
            occupied_slots: Dictionary of occupied time slots to update
        """
        day, time = time_key
        event_info = self.events[event_name]

        # Get time range for this event
        event_start, event_end = self._get_event_time_range(event_name, time)

        # Determine which days this event affects
        if event_info["type"] == "daily" or day == "Daily":
            # Daily events go in the "Daily" slot
            occupied_slots["Daily"].append((event_start, event_end, event_name))
        elif event_info["type"] == "fixed_days":
            if day in self.days_of_week:
                # Multi-slot fixed-day event with specific day
                occupied_slots[day].append((event_start, event_end, event_name))
            else:
                # Single-slot fixed-day event affects all its days
                for event_day in event_info.get("days", []):
                    occupied_slots[event_day].append((event_start, event_end, event_name))
        else:
            # Weekly event - specific day only
            if day in self.days_of_week:
                occupied_slots[day].append((event_start, event_end, event_name))

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
