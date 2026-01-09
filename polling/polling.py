from redbot.core import commands, Config
from redbot.core.bot import Red
import discord
from typing import Optional, Dict, List, Tuple
from datetime import datetime, time as dt_time

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
                "color": discord.Color.purple(),
                "emoji": "🎉"
            },
            "Breaking Army #1": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "color": discord.Color.red(),
                "emoji": "⚔️"
            },
            "Breaking Army #2": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "color": discord.Color.red(),
                "emoji": "⚔️"
            },
            "Showdown #1": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "color": discord.Color.orange(),
                "emoji": "🏆"
            },
            "Showdown #2": {
                "type": "once",
                "time_range": (18, 24),
                "interval": 30,
                "color": discord.Color.orange(),
                "emoji": "🏆"
            }
        }

        self.days_of_week = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
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
        view = EventPollView(self, ctx.guild.id, ctx.author.id, self.events, self.days_of_week)

        # Create the initial embed
        embed = discord.Embed(
            title=f"📅 {title}",
            description=(
                "Select your preferred time for each event using the buttons below.\n\n"
                "**Events:**\n"
                "🎉 **Party** - Daily event (18:00-24:00)\n"
                "⚔️ **Breaking Army #1** - Weekly event\n"
                "⚔️ **Breaking Army #2** - Weekly event\n"
                "🏆 **Showdown #1** - Weekly event\n"
                "🏆 **Showdown #2** - Weekly event\n\n"
                "⚠️ You cannot select conflicting times for different events!"
            ),
            color=discord.Color.blue()
        )
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
        # For Party (daily event), we need to check if the time conflicts with any other event
        # For weekly events, we need to check if day+time conflicts

        for existing_event, selection in user_selections.items():
            if existing_event == event_name:
                # Skip checking against itself
                continue

            existing_time = selection["time"]
            existing_day = selection.get("day")

            # Convert times to comparable format
            new_time_obj = datetime.strptime(new_time, "%H:%M").time()
            existing_time_obj = datetime.strptime(existing_time, "%H:%M").time()

            # Party is daily, so it conflicts with any event on any day at the same time
            if self.events[event_name]["type"] == "daily":
                # Party conflicts with all events at the same time
                if new_time == existing_time:
                    return True, f"This time conflicts with your {existing_event} selection"

            elif self.events[existing_event]["type"] == "daily":
                # Any event conflicts with Party if same time
                if new_time == existing_time:
                    if new_day:
                        return True, f"This time conflicts with your Party selection on {new_day}"
                    else:
                        return True, f"This time conflicts with your Party selection"

            else:
                # Both are weekly events - only conflict if same day and same time
                if new_day and existing_day and new_day == existing_day and new_time == existing_time:
                    return True, f"This conflicts with your {existing_event} selection on {existing_day}"

        return False, None
