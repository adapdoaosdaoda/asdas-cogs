import discord
from typing import Optional, Dict, List
from datetime import datetime


class EventPollView(discord.ui.View):
    """Main view with buttons for each event type"""

    def __init__(self, cog, guild_id: int, creator_id: int, events: Dict, days: List[str], blocked_times: List[Dict]):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.creator_id = creator_id
        self.events = events
        self.days = days
        self.blocked_times = blocked_times
        self.poll_id: Optional[str] = None

        # Create buttons for each event - all in one horizontal row
        event_names = list(events.keys())
        for idx, event_name in enumerate(event_names):
            # Determine button style based on event
            if "Party" in event_name:
                button_style = discord.ButtonStyle.success  # Green
            elif "Breaking Army" in event_name:
                button_style = discord.ButtonStyle.primary  # Blue
            elif "Showdown" in event_name:
                button_style = discord.ButtonStyle.danger  # Red
            else:
                button_style = discord.ButtonStyle.secondary  # Grey

            button = discord.ui.Button(
                label=event_name,
                style=button_style,
                emoji=events[event_name]["emoji"],
                custom_id=f"event_poll:{event_name}",
                row=0  # All buttons in row 0 (horizontal)
            )
            button.callback = self._create_event_callback(event_name)
            self.add_item(button)

    def _create_event_callback(self, event_name: str):
        async def callback(interaction: discord.Interaction):
            # Get user's current selections
            polls = await self.cog.config.guild_from_id(self.guild_id).polls()
            if not self.poll_id or self.poll_id not in polls:
                await interaction.response.send_message(
                    "This poll is no longer active!",
                    ephemeral=True
                )
                return

            poll_data = polls[self.poll_id]
            user_id_str = str(interaction.user.id)
            user_selections = poll_data["selections"].get(user_id_str, {})

            # Check event type
            event_info = self.events[event_name]

            if event_info["type"] == "daily":
                # Party event - show time selector directly
                view = TimeSelectView(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    poll_id=self.poll_id,
                    user_id=interaction.user.id,
                    event_name=event_name,
                    day=None,  # No day for daily events
                    user_selections=user_selections,
                    events=self.events
                )
                await interaction.response.send_message(
                    f"Select a time for **{event_name}** (18:00-24:00):",
                    view=view,
                    ephemeral=True
                )
            else:
                # Weekly event - show day selector first
                view = DaySelectView(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    poll_id=self.poll_id,
                    user_id=interaction.user.id,
                    event_name=event_name,
                    user_selections=user_selections,
                    events=self.events,
                    days=self.days
                )
                await interaction.response.send_message(
                    f"Select a day for **{event_name}**:",
                    view=view,
                    ephemeral=True
                )

        return callback


class DaySelectView(discord.ui.View):
    """View for selecting a day of the week"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, user_selections: Dict, events: Dict, days: List[str]):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.user_selections = user_selections
        self.events = events
        self.days = days

        # Create select menu for days
        options = []
        for day in days:
            options.append(
                discord.SelectOption(
                    label=day,
                    value=day,
                    emoji="📅"
                )
            )

        select = discord.ui.Select(
            placeholder="Choose a day...",
            options=options,
            custom_id=f"day_select:{event_name}"
        )
        select.callback = self._day_selected
        self.add_item(select)

        # Add cancel button
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="❌"
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _day_selected(self, interaction: discord.Interaction):
        """Handle day selection"""
        selected_day = interaction.data["values"][0]

        # Show time selector
        view = TimeSelectView(
            cog=self.cog,
            guild_id=self.guild_id,
            poll_id=self.poll_id,
            user_id=self.user_id,
            event_name=self.event_name,
            day=selected_day,
            user_selections=self.user_selections,
            events=self.events
        )

        await interaction.response.edit_message(
            content=f"Select a time for **{self.event_name}** on **{selected_day}**:",
            view=view
        )

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )

    async def on_timeout(self):
        """Handle timeout"""
        pass


class TimeSelectView(discord.ui.View):
    """View for selecting a time"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, day: Optional[str], user_selections: Dict, events: Dict):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.day = day
        self.user_selections = user_selections
        self.events = events

        # Generate time options
        event_info = events[event_name]
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval)

        # Create select menu(s) for times - split into multiple if too many options
        max_options_per_select = 25
        time_chunks = [times[i:i + max_options_per_select] for i in range(0, len(times), max_options_per_select)]

        for chunk_idx, time_chunk in enumerate(time_chunks):
            options = []
            for time_str in time_chunk:
                options.append(
                    discord.SelectOption(
                        label=time_str,
                        value=time_str,
                        emoji="🕐"
                    )
                )

            select = discord.ui.Select(
                placeholder=f"Choose a time ({time_chunk[0]} - {time_chunk[-1]})...",
                options=options,
                custom_id=f"time_select:{event_name}:{chunk_idx}",
                row=chunk_idx
            )
            select.callback = self._time_selected
            self.add_item(select)

        # Add clear button if user already has a selection
        if event_name in user_selections:
            clear_btn = discord.ui.Button(
                label="Clear Selection",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=len(time_chunks)
            )
            clear_btn.callback = self._clear_selection
            self.add_item(clear_btn)

        # Add cancel button
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=len(time_chunks)
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _time_selected(self, interaction: discord.Interaction):
        """Handle time selection"""
        selected_time = interaction.data["values"][0]

        # Check for conflicts
        has_conflict, conflict_msg = self.cog.check_time_conflict(
            self.user_selections,
            self.event_name,
            self.day,
            selected_time
        )

        if has_conflict:
            await interaction.response.send_message(
                f"⚠️ **Conflict detected!**\n{conflict_msg}\n\nPlease choose a different time or clear your conflicting selection first.",
                ephemeral=True
            )
            return

        # Save the selection
        poll_data = None
        async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
            if self.poll_id not in polls:
                await interaction.response.send_message(
                    "This poll is no longer active!",
                    ephemeral=True
                )
                return

            user_id_str = str(self.user_id)
            if user_id_str not in polls[self.poll_id]["selections"]:
                polls[self.poll_id]["selections"][user_id_str] = {}

            # Store the selection
            selection_data = {"time": selected_time}
            if self.day:
                selection_data["day"] = self.day

            polls[self.poll_id]["selections"][user_id_str][self.event_name] = selection_data
            poll_data = polls[self.poll_id]

        # Create confirmation message
        if self.day:
            selection_text = f"**{self.event_name}** on **{self.day}** at **{selected_time}**"
        else:
            selection_text = f"**{self.event_name}** at **{selected_time}** (daily)"

        # Show user's current selections
        current_selections = await self._get_user_selections_text()

        await interaction.response.edit_message(
            content=f"✅ Selection saved!\n\n{selection_text}\n\n**Your current selections:**\n{current_selections}",
            view=None
        )

        # Update the poll embed to show updated results
        if poll_data:
            try:
                channel = interaction.guild.get_channel(poll_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(poll_data["message_id"])
                    updated_embed = await self.cog._create_poll_embed(
                        poll_data["title"],
                        self.guild_id,
                        self.poll_id
                    )
                    updated_embed.set_footer(text="Click the buttons below to set your preferences")
                    await message.edit(embed=updated_embed)
            except Exception:
                # Silently fail if we can't update the poll message
                pass

    async def _clear_selection(self, interaction: discord.Interaction):
        """Clear the user's selection for this event"""
        poll_data = None
        async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
            if self.poll_id not in polls:
                await interaction.response.send_message(
                    "This poll is no longer active!",
                    ephemeral=True
                )
                return

            user_id_str = str(self.user_id)
            if user_id_str in polls[self.poll_id]["selections"]:
                if self.event_name in polls[self.poll_id]["selections"][user_id_str]:
                    del polls[self.poll_id]["selections"][user_id_str][self.event_name]

            poll_data = polls[self.poll_id]

        current_selections = await self._get_user_selections_text()

        await interaction.response.edit_message(
            content=f"🗑️ Cleared your selection for **{self.event_name}**\n\n**Your current selections:**\n{current_selections}",
            view=None
        )

        # Update the poll embed to show updated results
        if poll_data:
            try:
                channel = interaction.guild.get_channel(poll_data["channel_id"])
                if channel:
                    message = await channel.fetch_message(poll_data["message_id"])
                    updated_embed = await self.cog._create_poll_embed(
                        poll_data["title"],
                        self.guild_id,
                        self.poll_id
                    )
                    updated_embed.set_footer(text="Click the buttons below to set your preferences")
                    await message.edit(embed=updated_embed)
            except Exception:
                # Silently fail if we can't update the poll message
                pass

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )

    async def _get_user_selections_text(self) -> str:
        """Get formatted text of user's current selections"""
        polls = await self.cog.config.guild_from_id(self.guild_id).polls()
        if self.poll_id not in polls:
            return "None"

        user_id_str = str(self.user_id)
        selections = polls[self.poll_id]["selections"].get(user_id_str, {})

        if not selections:
            return "None"

        lines = []
        for event_name, selection in selections.items():
            emoji = self.events[event_name]["emoji"]
            if "day" in selection:
                lines.append(f"{emoji} {event_name}: {selection['day']} at {selection['time']}")
            else:
                lines.append(f"{emoji} {event_name}: {selection['time']} (daily)")

        return "\n".join(lines)

    async def on_timeout(self):
        """Handle timeout"""
        pass
