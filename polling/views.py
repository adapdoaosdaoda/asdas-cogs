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

        # Add Results button first (grey, row 0)
        results_button = discord.ui.Button(
            label="Results",
            style=discord.ButtonStyle.secondary,
            emoji="🏆",
            custom_id="event_poll:results",
            row=0
        )
        results_button.callback = self._show_results
        self.add_item(results_button)

        # Create buttons for each event in 2 rows
        # Row 0: Results, Hero's Realm, Sword Trial
        # Row 1: Party, Breaking Army, Showdown
        event_names = list(events.keys())
        for idx, event_name in enumerate(event_names):
            # Determine button style based on event
            if "Hero's Realm" in event_name:
                button_style = discord.ButtonStyle.secondary  # Grey
                row = 0
            elif "Sword Trial" in event_name:
                button_style = discord.ButtonStyle.secondary  # Grey
                row = 0
            elif "Party" in event_name:
                button_style = discord.ButtonStyle.success  # Green
                row = 1
            elif "Breaking Army" in event_name:
                button_style = discord.ButtonStyle.primary  # Blue
                row = 1
            elif "Showdown" in event_name:
                button_style = discord.ButtonStyle.danger  # Red
                row = 1
            else:
                button_style = discord.ButtonStyle.secondary  # Grey
                row = 1

            button = discord.ui.Button(
                label=event_name,
                style=button_style,
                emoji=events[event_name]["emoji"],
                custom_id=f"event_poll:{event_name}",
                row=row
            )
            button.callback = self._create_event_callback(event_name)
            self.add_item(button)

    async def _show_results(self, interaction: discord.Interaction):
        """Show current poll results"""
        # Get poll_id from the message
        poll_id = str(interaction.message.id)

        # Get poll data
        polls = await self.cog.config.guild_from_id(self.guild_id).polls()
        if poll_id not in polls:
            await interaction.response.send_message(
                "This poll is no longer active!",
                ephemeral=True
            )
            return

        poll_data = polls[poll_id]
        selections = poll_data.get("selections", {})

        # Calculate winning times using weighted point system
        winning_times = self.cog._calculate_winning_times_weighted(selections)

        # Format results using cog's method
        results_text = self.cog.format_results_summary_weighted(winning_times, selections)

        # Send results as ephemeral message
        await interaction.response.send_message(
            results_text,
            ephemeral=True
        )

    def _create_event_callback(self, event_name: str):
        async def callback(interaction: discord.Interaction):
            # Get poll_id from the message (for persistent views)
            poll_id = str(interaction.message.id)

            # Get user's current selections
            polls = await self.cog.config.guild_from_id(self.guild_id).polls()
            if poll_id not in polls:
                await interaction.response.send_message(
                    "This poll is no longer active!",
                    ephemeral=True
                )
                return

            poll_data = polls[poll_id]
            user_id_str = str(interaction.user.id)
            user_selections = poll_data["selections"].get(user_id_str, {})

            # Check event type
            event_info = self.events[event_name]
            timezone_display = self.cog.timezone_display

            if event_info["type"] == "daily":
                # Daily event - show time selector directly (single slot, no day)
                view = TimeSelectView(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    poll_id=poll_id,
                    user_id=interaction.user.id,
                    event_name=event_name,
                    day=None,  # No day for daily events
                    slot_index=0,  # Single slot
                    user_selections=user_selections,
                    events=self.events
                )
                await interaction.response.send_message(
                    f"**{event_name}** - Select a time\nTimezone: {timezone_display}",
                    view=view,
                    ephemeral=True
                )
            elif event_info["type"] == "fixed_days":
                # Fixed-day event - check if multi-slot
                if event_info["slots"] > 1:
                    # Multi-slot fixed-day event - show slot selector (each slot = one day)
                    view = FixedDaySlotSelectView(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        event_name=event_name,
                        user_selections=user_selections,
                        events=self.events
                    )
                    await interaction.response.send_message(
                        f"**{event_name}** - Select a day\nTimezone: {timezone_display}",
                        view=view,
                        ephemeral=True
                    )
                else:
                    # Single slot fixed-day event - show time selector directly
                    view = TimeSelectView(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        event_name=event_name,
                        day=None,  # No day selection for fixed-day events
                        slot_index=0,  # Single slot
                        user_selections=user_selections,
                        events=self.events
                    )
                    days_str = ", ".join([d[:3] for d in event_info["days"]])
                    await interaction.response.send_message(
                        f"**{event_name}** ({days_str}) - Select a time\nTimezone: {timezone_display}",
                        view=view,
                        ephemeral=True
                    )
            else:
                # Weekly event - check if multi-slot
                if event_info["slots"] > 1:
                    # Show slot selector first
                    view = SlotSelectView(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        event_name=event_name,
                        user_selections=user_selections,
                        events=self.events,
                        days=self.days
                    )
                    await interaction.response.send_message(
                        f"**{event_name}** - Select a slot\nTimezone: {timezone_display}",
                        view=view,
                        ephemeral=True
                    )
                else:
                    # Single slot weekly event - show day selector
                    view = DaySelectView(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        event_name=event_name,
                        slot_index=0,
                        user_selections=user_selections,
                        events=self.events,
                        days=self.days
                    )
                    await interaction.response.send_message(
                        f"**{event_name}** - Select a day\nTimezone: {timezone_display}",
                        view=view,
                        ephemeral=True
                    )

        return callback


class SlotSelectView(discord.ui.View):
    """View for selecting which slot to configure (for multi-slot events)"""

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

        num_slots = events[event_name]["slots"]

        # Create buttons for each slot
        for slot_index in range(num_slots):
            button = discord.ui.Button(
                label=f"Slot {slot_index + 1}",
                style=discord.ButtonStyle.secondary,
                row=0
            )
            button.callback = self._create_slot_callback(slot_index)
            self.add_item(button)

        # Add cancel button
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            row=1
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    def _create_slot_callback(self, slot_index: int):
        """Create a callback for a specific slot button"""
        async def callback(interaction: discord.Interaction):
            # Show combined day and time selector for this slot
            view = DayAndTimeSelectView(
                cog=self.cog,
                guild_id=self.guild_id,
                poll_id=self.poll_id,
                user_id=self.user_id,
                event_name=self.event_name,
                slot_index=slot_index,
                user_selections=self.user_selections,
                events=self.events,
                days=self.days
            )

            timezone_display = self.cog.timezone_display
            await interaction.response.edit_message(
                content=f"**{self.event_name}** Slot {slot_index + 1} - Select day and time\nTimezone: {timezone_display}",
                view=view
            )

        return callback

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )

    async def on_timeout(self):
        """Handle timeout"""
        pass


class FixedDaySlotSelectView(discord.ui.View):
    """View for selecting which slot to configure for fixed-day multi-slot events
    Each slot corresponds to one day from the event's days list"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, user_selections: Dict, events: Dict):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.user_selections = user_selections
        self.events = events

        event_info = events[event_name]
        num_slots = event_info["slots"]
        days = event_info["days"]

        # Create buttons for each slot - each slot represents a specific day
        for slot_index in range(num_slots):
            day = days[slot_index] if slot_index < len(days) else f"Day {slot_index + 1}"
            button = discord.ui.Button(
                label=f"{day[:3]}",  # Mon, Tue, Wed, etc.
                style=discord.ButtonStyle.secondary,
                row=0 if slot_index < 5 else 1
            )
            button.callback = self._create_slot_callback(slot_index, day)
            self.add_item(button)

        # Add cancel button
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            row=2
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    def _create_slot_callback(self, slot_index: int, day: str):
        """Create a callback for a specific slot button"""
        async def callback(interaction: discord.Interaction):
            # Show time selector for this slot/day
            view = TimeSelectView(
                cog=self.cog,
                guild_id=self.guild_id,
                poll_id=self.poll_id,
                user_id=self.user_id,
                event_name=self.event_name,
                day=day,  # Store the specific day for this slot
                slot_index=slot_index,
                user_selections=self.user_selections,
                events=self.events
            )

            timezone_display = self.cog.timezone_display
            await interaction.response.edit_message(
                content=f"**{self.event_name}** ({day}) - Select a time\nTimezone: {timezone_display}",
                view=view
            )

        return callback

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )

    async def on_timeout(self):
        """Handle timeout"""
        pass


class DaySelectView(discord.ui.View):
    """View for selecting a day of the week"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, slot_index: int, user_selections: Dict, events: Dict, days: List[str]):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.slot_index = slot_index
        self.user_selections = user_selections
        self.events = events
        self.days = days

        # Create 7 grey buttons for each day of the week
        # Discord allows max 5 buttons per row, so split across 2 rows
        for idx, day in enumerate(days):
            # Use abbreviated day names for button labels (3 letters)
            # Row 0: Mon-Fri (5 buttons), Row 1: Sat-Sun (2 buttons)
            button_row = 0 if idx < 5 else 1
            button = discord.ui.Button(
                label=day[:3],  # Mon, Tue, Wed, etc.
                style=discord.ButtonStyle.secondary,  # Grey
                row=button_row
            )
            button.callback = self._create_day_callback(day)
            self.add_item(button)

        # Add cancel button in third row
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            row=2
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    def _create_day_callback(self, day: str):
        """Create a callback for a specific day button"""
        async def callback(interaction: discord.Interaction):
            # Show time selector
            view = TimeSelectView(
                cog=self.cog,
                guild_id=self.guild_id,
                poll_id=self.poll_id,
                user_id=self.user_id,
                event_name=self.event_name,
                day=day,
                slot_index=self.slot_index,
                user_selections=self.user_selections,
                events=self.events
            )

            slot_text = f" Slot {self.slot_index + 1}" if self.events[self.event_name]["slots"] > 1 else ""
            timezone_display = self.cog.timezone_display
            await interaction.response.edit_message(
                content=f"**{self.event_name}**{slot_text} ({day}) - Select a time\nTimezone: {timezone_display}",
                view=view
            )

        return callback

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )

    async def on_timeout(self):
        """Handle timeout"""
        pass


class DayAndTimeSelectView(discord.ui.View):
    """View for selecting both day and time together (for weekly events)"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, slot_index: int, user_selections: Dict, events: Dict, days: List[str]):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.slot_index = slot_index
        self.user_selections = user_selections
        self.events = events
        self.days = days

        # Store selected values
        self.selected_day = None
        self.selected_time = None

        # Get current selection if exists
        current_selection = None
        if event_name in user_selections:
            selection = user_selections[event_name]
            if isinstance(selection, list) and slot_index < len(selection):
                current_selection = selection[slot_index]
            elif not isinstance(selection, list) and slot_index == 0:
                current_selection = selection

        # Create day dropdown
        day_options = []
        for day in days:
            day_options.append(
                discord.SelectOption(
                    label=day,
                    value=day,
                    emoji="📅",
                    default=(current_selection and current_selection.get("day") == day)
                )
            )

        day_select = discord.ui.Select(
            placeholder="Choose a day...",
            options=day_options,
            custom_id=f"day_select:{event_name}",
            row=0
        )
        day_select.callback = self._day_selected
        self.add_item(day_select)

        # Create time dropdown
        event_info = events[event_name]
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration)

        # Get timezone display
        timezone_display = self.cog.timezone_display

        # Split times into chunks if needed (max 25 options per select)
        max_options_per_select = 25
        time_chunks = [times[i:i + max_options_per_select] for i in range(0, len(times), max_options_per_select)]

        for chunk_idx, time_chunk in enumerate(time_chunks):
            time_options = []
            for time_str in time_chunk:
                time_options.append(
                    discord.SelectOption(
                        label=time_str,
                        value=time_str,
                        emoji="🕐",
                        default=(current_selection and current_selection.get("time") == time_str)
                    )
                )

            time_select = discord.ui.Select(
                placeholder=f"Choose a time ({time_chunk[0]} - {time_chunk[-1]}) {timezone_display}",
                options=time_options,
                custom_id=f"time_select:{event_name}:{chunk_idx}",
                row=1 + chunk_idx
            )
            time_select.callback = self._time_selected
            self.add_item(time_select)

        # Add submit button
        submit_btn = discord.ui.Button(
            label="Save",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=4
        )
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

        # Add clear button if user already has a selection
        if current_selection:
            clear_btn = discord.ui.Button(
                label="Clear Selection",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=4
            )
            clear_btn.callback = self._clear_selection
            self.add_item(clear_btn)

        # Add cancel button
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=4
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _day_selected(self, interaction: discord.Interaction):
        """Handle day selection"""
        self.selected_day = interaction.data["values"][0]
        await interaction.response.defer()

    async def _time_selected(self, interaction: discord.Interaction):
        """Handle time selection"""
        self.selected_time = interaction.data["values"][0]
        await interaction.response.defer()

    async def _submit(self, interaction: discord.Interaction):
        """Handle submit"""
        # Get current selections from dropdowns or use stored values
        if not self.selected_day or not self.selected_time:
            await interaction.response.send_message(
                "⚠️ Please select both a day and a time before saving!",
                ephemeral=True
            )
            return

        # Check for conflicts
        has_conflict, conflict_msg = self.cog.check_time_conflict(
            self.user_selections,
            self.event_name,
            self.selected_day,
            self.selected_time,
            self.slot_index
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
            selection_data = {"time": self.selected_time, "day": self.selected_day}

            # For multi-slot events, store as list
            event_info = self.events[self.event_name]
            if event_info["slots"] > 1:
                if self.event_name not in polls[self.poll_id]["selections"][user_id_str]:
                    polls[self.poll_id]["selections"][user_id_str][self.event_name] = [None] * event_info["slots"]

                polls[self.poll_id]["selections"][user_id_str][self.event_name][self.slot_index] = selection_data
            else:
                polls[self.poll_id]["selections"][user_id_str][self.event_name] = selection_data

            poll_data = polls[self.poll_id]

        # Create confirmation message
        slot_text = f" Slot {self.slot_index + 1}" if event_info["slots"] > 1 else ""
        selection_text = f"**{self.event_name}**{slot_text} on **{self.selected_day}** at **{self.selected_time}**"

        # Show user's current selections
        current_selections = await self._get_user_selections_text()

        await interaction.response.edit_message(
            content=f"✅ Selection saved!\n\n{selection_text}\n\n**Your current selections:**\n{current_selections}",
            view=None
        )

        # Update the poll embed
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

                # Update any calendar messages for this poll
                await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)
            except Exception:
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

        # Update the poll embed
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

                # Update any calendar messages for this poll
                await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)
            except Exception:
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
            event_type = self.events[event_name]["type"]

            # Handle both list (multi-slot) and dict (single-slot) formats
            if isinstance(selection, list):
                # Multi-slot event
                for idx, slot_data in enumerate(selection):
                    if slot_data:
                        if "day" in slot_data:
                            lines.append(f"{emoji} {event_name} #{idx + 1}: {slot_data['day']} at {slot_data['time']}")
                        elif event_type == "fixed_days":
                            day = self.events[event_name]["days"][idx] if idx < len(self.events[event_name]["days"]) else f"Day {idx + 1}"
                            lines.append(f"{emoji} {event_name} ({day[:3]}): {slot_data['time']}")
                        else:
                            lines.append(f"{emoji} {event_name} #{idx + 1}: {slot_data['time']} (daily)")
            else:
                # Single-slot event
                if "day" in selection:
                    lines.append(f"{emoji} {event_name}: {selection['day']} at {selection['time']}")
                elif event_type == "fixed_days":
                    days_str = "/".join([d[:3] for d in self.events[event_name]["days"]])
                    lines.append(f"{emoji} {event_name}: {selection['time']} ({days_str})")
                else:
                    lines.append(f"{emoji} {event_name}: {selection['time']} (daily)")

        return "\n".join(lines) if lines else "None"

    async def on_timeout(self):
        """Handle timeout"""
        pass


class TimeSelectView(discord.ui.View):
    """View for selecting a time"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, day: Optional[str], slot_index: int, user_selections: Dict, events: Dict):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.day = day
        self.slot_index = slot_index
        self.user_selections = user_selections
        self.events = events

        # Generate time options
        event_info = events[event_name]
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration)

        # Get timezone display
        timezone_display = self.cog.timezone_display

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
                placeholder=f"Choose a time ({time_chunk[0]} - {time_chunk[-1]}) {timezone_display}",
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
            selected_time,
            self.slot_index
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

            # For multi-slot events, store as list; for single-slot, store as dict
            event_info = self.events[self.event_name]
            if event_info["slots"] > 1:
                # Multi-slot event - use list format
                if self.event_name not in polls[self.poll_id]["selections"][user_id_str]:
                    # Initialize with None for each slot
                    polls[self.poll_id]["selections"][user_id_str][self.event_name] = [None] * event_info["slots"]

                polls[self.poll_id]["selections"][user_id_str][self.event_name][self.slot_index] = selection_data
            else:
                # Single-slot event - use dict format
                polls[self.poll_id]["selections"][user_id_str][self.event_name] = selection_data

            poll_data = polls[self.poll_id]

        # Create confirmation message
        slot_text = f" slot {self.slot_index + 1}" if event_info["slots"] > 1 else ""
        if self.day:
            selection_text = f"**{self.event_name}**{slot_text} on **{self.day}** at **{selected_time}**"
        elif event_info["type"] == "fixed_days":
            days_str = ", ".join([d[:3] for d in event_info["days"]])
            selection_text = f"**{self.event_name}**{slot_text} at **{selected_time}** ({days_str})"
        else:
            selection_text = f"**{self.event_name}**{slot_text} at **{selected_time}** (daily)"

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

                # Update any calendar messages for this poll
                await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)
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

                # Update any calendar messages for this poll
                await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)
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
            event_type = self.events[event_name]["type"]

            # Handle both list (multi-slot) and dict (single-slot) formats
            if isinstance(selection, list):
                # Multi-slot event
                for idx, slot_data in enumerate(selection):
                    if slot_data:  # Slot might be None if not yet selected
                        if "day" in slot_data:
                            lines.append(f"{emoji} {event_name} #{idx + 1}: {slot_data['day']} at {slot_data['time']}")
                        elif event_type == "fixed_days":
                            days_str = ", ".join([d[:3] for d in self.events[event_name]["days"]])
                            lines.append(f"{emoji} {event_name} #{idx + 1}: {slot_data['time']} ({days_str})")
                        else:
                            lines.append(f"{emoji} {event_name} #{idx + 1}: {slot_data['time']} (daily)")
            else:
                # Single-slot event
                if "day" in selection:
                    lines.append(f"{emoji} {event_name}: {selection['day']} at {selection['time']}")
                elif event_type == "fixed_days":
                    days_str = ", ".join([d[:3] for d in self.events[event_name]["days"]])
                    lines.append(f"{emoji} {event_name}: {selection['time']} ({days_str})")
                else:
                    lines.append(f"{emoji} {event_name}: {selection['time']} (daily)")

        return "\n".join(lines) if lines else "None"

    async def on_timeout(self):
        """Handle timeout"""
        pass
