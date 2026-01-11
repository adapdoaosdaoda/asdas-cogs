import discord
from typing import Optional, Dict, List
from datetime import datetime


class DismissibleView(discord.ui.View):
    """Simple view with a close button for dismissible messages"""

    def __init__(self):
        super().__init__(timeout=180)

        close_btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
        close_btn.callback = self._close
        self.add_item(close_btn)

    async def _close(self, interaction: discord.Interaction):
        """Handle close button"""
        await interaction.response.edit_message(view=None)
        await interaction.delete_original_response()


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
        """Show current poll results with category buttons"""
        # Get poll_id from the message
        poll_id = str(interaction.message.id)

        # Get poll data
        polls = await self.cog.config.guild_from_id(self.guild_id).polls()
        if poll_id not in polls:
            await interaction.response.send_message(
                "This poll is no longer active!",
                view=DismissibleView(),
                ephemeral=True
            )
            return

        poll_data = polls[poll_id]
        selections = poll_data.get("selections", {})

        # Calculate winning times using weighted point system
        winning_times = self.cog._calculate_winning_times_weighted(selections)

        # Format intro text with rules
        intro_text = self.cog.format_results_intro(selections)

        # Create view with event category buttons
        results_view = ResultsCategoryView(self.cog, self.guild_id, poll_id, winning_times, selections, self.events)

        # Send intro with category buttons as ephemeral message
        await interaction.response.send_message(
            intro_text,
            view=results_view,
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

            # Check event type and show appropriate modal
            event_info = self.events[event_name]
            timezone_display = self.cog.timezone_display

            if event_info["type"] == "daily":
                # Party event - single time selection
                view = PartyModal(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    poll_id=poll_id,
                    user_id=interaction.user.id,
                    event_name=event_name,
                    user_selections=user_selections,
                    events=self.events
                )
                await interaction.response.send_message(
                    f"**{event_name}** - Select your preferred time\nTimezone: {timezone_display}",
                    view=view,
                    ephemeral=True
                )
            elif event_info["type"] == "fixed_days":
                # Hero's Realm / Sword Trial - multiple fixed days
                view = FixedDaysModal(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    poll_id=poll_id,
                    user_id=interaction.user.id,
                    event_name=event_name,
                    user_selections=user_selections,
                    events=self.events
                )
                await interaction.response.send_message(
                    f"**{event_name}** - Select your preferred times\nTimezone: {timezone_display}",
                    view=view,
                    ephemeral=True
                )
            else:
                # Breaking Army / Showdown - 2 slots with day+time
                view = WeeklyEventModal(
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
                    f"**{event_name}** - Select your preferred times\nTimezone: {timezone_display}",
                    view=view,
                    ephemeral=True
                )

        return callback


class PartyModal(discord.ui.View):
    """Modal for Party event - single time dropdown"""

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
        self.selected_time = None

        # Get current selection if exists
        current_selection = user_selections.get(event_name)

        # Generate time options
        event_info = events[event_name]
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration)

        # Get timezone display
        timezone_display = self.cog.timezone_display

        # Create time dropdown - split into chunks if needed
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
                custom_id=f"time_select:{chunk_idx}",
                row=chunk_idx
            )
            time_select.callback = self._time_selected
            self.add_item(time_select)

        # Add buttons
        button_row = len(time_chunks)

        submit_btn = discord.ui.Button(
            label="Save",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=button_row
        )
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

        if current_selection:
            clear_btn = discord.ui.Button(
                label="Clear",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=button_row
            )
            clear_btn.callback = self._clear_selection
            self.add_item(clear_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=button_row
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _time_selected(self, interaction: discord.Interaction):
        """Handle time selection"""
        self.selected_time = interaction.data["values"][0]
        await interaction.response.defer()

    async def _submit(self, interaction: discord.Interaction):
        """Handle submit"""
        if not self.selected_time:
            await interaction.response.send_message(
                "⚠️ Please select a time before saving!",
                view=DismissibleView(),
                ephemeral=True
            )
            return

        # Check for conflicts
        has_conflict, conflict_msg = self.cog.check_time_conflict(
            self.user_selections,
            self.event_name,
            None,  # No day for daily events
            self.selected_time,
            0  # Single slot
        )

        if has_conflict:
            await interaction.response.send_message(
                f"⚠️ **Conflict detected!**\n{conflict_msg}\n\nPlease choose a different time or clear your conflicting selection first.",
                view=DismissibleView(),
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
            polls[self.poll_id]["selections"][user_id_str][self.event_name] = {"time": self.selected_time}
            poll_data = polls[self.poll_id]

        # Update the poll embed
        if poll_data:
            await self._update_poll_display(interaction, poll_data)

        # Auto-dismiss the ephemeral message
        await interaction.response.edit_message(
            content=f"✅ Selection saved for **{self.event_name}**!",
            view=None
        )
        await interaction.delete_original_response()

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

        # Update the poll embed
        if poll_data:
            await self._update_poll_display(interaction, poll_data)

        # Auto-dismiss the ephemeral message
        await interaction.response.edit_message(
            content=f"🗑️ Cleared selection for **{self.event_name}**",
            view=None
        )
        await interaction.delete_original_response()

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )
        await interaction.delete_original_response()

    async def _update_poll_display(self, interaction: discord.Interaction, poll_data: Dict):
        """Update the poll embed and calendar"""
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

            # Update any results messages for this poll
            await self.cog._update_results_messages(interaction.guild, poll_data, self.poll_id)
        except Exception:
            pass

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


class FixedDaysModal(discord.ui.View):
    """Modal for Hero's Realm / Sword Trial - one time dropdown per fixed day"""

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
        self.selected_times = {}  # {day: time}

        # Get current selections if exist
        current_selections = user_selections.get(event_name)

        # Generate time options
        event_info = events[event_name]
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration)

        # Get timezone display
        timezone_display = self.cog.timezone_display

        # Create a time dropdown for each fixed day
        days = event_info["days"]
        for row_idx, day in enumerate(days):
            # Get current time for this day if exists
            current_time = None
            if current_selections and isinstance(current_selections, list):
                if row_idx < len(current_selections) and current_selections[row_idx]:
                    current_time = current_selections[row_idx].get("time")

            # Create options for this day's dropdown
            time_options = []
            for time_str in times[:25]:  # Limit to 25 options
                time_options.append(
                    discord.SelectOption(
                        label=time_str,
                        value=time_str,
                        emoji="🕐",
                        default=(current_time == time_str)
                    )
                )

            day_select = discord.ui.Select(
                placeholder=f"{day[:3]} - Choose a time... {timezone_display}",
                options=time_options,
                custom_id=f"day_select:{day}",
                row=row_idx
            )
            day_select.callback = self._create_time_callback(day)
            self.add_item(day_select)

        # Add buttons
        button_row = len(days)

        submit_btn = discord.ui.Button(
            label="Save",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=button_row
        )
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

        if current_selections:
            clear_btn = discord.ui.Button(
                label="Clear",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=button_row
            )
            clear_btn.callback = self._clear_selection
            self.add_item(clear_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=button_row
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    def _create_time_callback(self, day: str):
        """Create a callback for a specific day's time selection"""
        async def callback(interaction: discord.Interaction):
            self.selected_times[day] = interaction.data["values"][0]
            await interaction.response.defer()
        return callback

    async def _submit(self, interaction: discord.Interaction):
        """Handle submit"""
        if not self.selected_times:
            await interaction.response.send_message(
                "⚠️ Please select at least one time before saving!",
                view=DismissibleView(),
                ephemeral=True
            )
            return

        # Save the selections
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

            # Store as list format
            event_info = self.events[self.event_name]
            days = event_info["days"]
            selections_list = []

            for day in days:
                if day in self.selected_times:
                    selections_list.append({"time": self.selected_times[day]})
                else:
                    # Keep existing selection if available, otherwise None
                    existing = polls[self.poll_id]["selections"][user_id_str].get(self.event_name, [])
                    idx = days.index(day)
                    if isinstance(existing, list) and idx < len(existing):
                        selections_list.append(existing[idx])
                    else:
                        selections_list.append(None)

            polls[self.poll_id]["selections"][user_id_str][self.event_name] = selections_list
            poll_data = polls[self.poll_id]

        # Update the poll embed
        if poll_data:
            await self._update_poll_display(interaction, poll_data)

        # Auto-dismiss the ephemeral message
        selected_text = ", ".join([f"{day[:3]} at {time}" for day, time in self.selected_times.items()])
        await interaction.response.edit_message(
            content=f"✅ Selection saved for **{self.event_name}**: {selected_text}",
            view=None
        )
        await interaction.delete_original_response()

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

        # Update the poll embed
        if poll_data:
            await self._update_poll_display(interaction, poll_data)

        # Auto-dismiss the ephemeral message
        await interaction.response.edit_message(
            content=f"🗑️ Cleared selection for **{self.event_name}**",
            view=None
        )
        await interaction.delete_original_response()

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )
        await interaction.delete_original_response()

    async def _update_poll_display(self, interaction: discord.Interaction, poll_data: Dict):
        """Update the poll embed and calendar"""
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

            # Update any results messages for this poll
            await self.cog._update_results_messages(interaction.guild, poll_data, self.poll_id)
        except Exception:
            pass

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


class WeeklyEventModal(discord.ui.View):
    """Modal for Breaking Army / Showdown - 2 slots with day+time dropdowns each"""

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
        # Get current selections if exist
        current_selections = user_selections.get(event_name)
        current_slot1 = None
        current_slot2 = None
        if current_selections and isinstance(current_selections, list):
            current_slot1 = current_selections[0] if len(current_selections) > 0 else None
            current_slot2 = current_selections[1] if len(current_selections) > 1 else None

        # Initialize selected values from existing selections (so user can edit without re-selecting everything)
        self.selected_slot1_day = current_slot1.get("day") if current_slot1 and isinstance(current_slot1, dict) else None
        self.selected_slot1_time = current_slot1.get("time") if current_slot1 and isinstance(current_slot1, dict) else None
        self.selected_slot2_day = current_slot2.get("day") if current_slot2 and isinstance(current_slot2, dict) else None
        self.selected_slot2_time = current_slot2.get("time") if current_slot2 and isinstance(current_slot2, dict) else None

        # Generate time options
        event_info = events[event_name]
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration)

        # Get timezone display
        timezone_display = self.cog.timezone_display

        # Slot 1 Day dropdown (row 0)
        day_options_1 = []
        for day in days:
            day_options_1.append(
                discord.SelectOption(
                    label=day,
                    value=day,
                    emoji="📅",
                    default=(current_slot1 and current_slot1.get("day") == day)
                )
            )

        slot1_day_select = discord.ui.Select(
            placeholder="Slot 1: Choose a day...",
            options=day_options_1,
            custom_id="slot1_day_select",
            row=0
        )
        slot1_day_select.callback = self._slot1_day_selected
        self.add_item(slot1_day_select)

        # Slot 1 Time dropdown (row 1)
        time_options_1 = []
        for time_str in times[:25]:  # Limit to 25 options
            time_options_1.append(
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(current_slot1 and current_slot1.get("time") == time_str)
                )
            )

        slot1_time_select = discord.ui.Select(
            placeholder=f"Slot 1: Choose a time... {timezone_display}",
            options=time_options_1,
            custom_id="slot1_time_select",
            row=1
        )
        slot1_time_select.callback = self._slot1_time_selected
        self.add_item(slot1_time_select)

        # Slot 2 Day dropdown (row 2)
        day_options_2 = []
        for day in days:
            day_options_2.append(
                discord.SelectOption(
                    label=day,
                    value=day,
                    emoji="📅",
                    default=(current_slot2 and current_slot2.get("day") == day)
                )
            )

        slot2_day_select = discord.ui.Select(
            placeholder="Slot 2: Choose a day...",
            options=day_options_2,
            custom_id="slot2_day_select",
            row=2
        )
        slot2_day_select.callback = self._slot2_day_selected
        self.add_item(slot2_day_select)

        # Slot 2 Time dropdown (row 3)
        time_options_2 = []
        for time_str in times[:25]:  # Limit to 25 options
            time_options_2.append(
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(current_slot2 and current_slot2.get("time") == time_str)
                )
            )

        slot2_time_select = discord.ui.Select(
            placeholder=f"Slot 2: Choose a time... {timezone_display}",
            options=time_options_2,
            custom_id="slot2_time_select",
            row=3
        )
        slot2_time_select.callback = self._slot2_time_selected
        self.add_item(slot2_time_select)

        # Add buttons (row 4)
        submit_btn = discord.ui.Button(
            label="Save",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=4
        )
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

        if current_selections:
            clear_btn = discord.ui.Button(
                label="Clear",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=4
            )
            clear_btn.callback = self._clear_selection
            self.add_item(clear_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=4
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _slot1_day_selected(self, interaction: discord.Interaction):
        """Handle slot 1 day selection"""
        self.selected_slot1_day = interaction.data["values"][0]
        await interaction.response.defer()

    async def _slot1_time_selected(self, interaction: discord.Interaction):
        """Handle slot 1 time selection"""
        self.selected_slot1_time = interaction.data["values"][0]
        await interaction.response.defer()

    async def _slot2_day_selected(self, interaction: discord.Interaction):
        """Handle slot 2 day selection"""
        self.selected_slot2_day = interaction.data["values"][0]
        await interaction.response.defer()

    async def _slot2_time_selected(self, interaction: discord.Interaction):
        """Handle slot 2 time selection"""
        self.selected_slot2_time = interaction.data["values"][0]
        await interaction.response.defer()

    async def _submit(self, interaction: discord.Interaction):
        """Handle submit"""
        # Check if at least one complete slot is selected
        has_slot1 = self.selected_slot1_day and self.selected_slot1_time
        has_slot2 = self.selected_slot2_day and self.selected_slot2_time

        if not has_slot1 and not has_slot2:
            await interaction.response.send_message(
                "⚠️ Please select at least one complete slot (day + time) before saving!",
                view=DismissibleView(),
                ephemeral=True
            )
            return

        # Check for conflicts for each slot
        if has_slot1:
            has_conflict, conflict_msg = self.cog.check_time_conflict(
                self.user_selections,
                self.event_name,
                self.selected_slot1_day,
                self.selected_slot1_time,
                0
            )
            if has_conflict:
                await interaction.response.send_message(
                    f"⚠️ **Conflict detected in Slot 1!**\n{conflict_msg}\n\nPlease choose a different time or clear your conflicting selection first.",
                    view=DismissibleView(),
                    ephemeral=True
                )
                return

        if has_slot2:
            has_conflict, conflict_msg = self.cog.check_time_conflict(
                self.user_selections,
                self.event_name,
                self.selected_slot2_day,
                self.selected_slot2_time,
                1
            )
            if has_conflict:
                await interaction.response.send_message(
                    f"⚠️ **Conflict detected in Slot 2!**\n{conflict_msg}\n\nPlease choose a different time or clear your conflicting selection first.",
                    view=DismissibleView(),
                    ephemeral=True
                )
                return

        # Save the selections
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

            # Get existing selections to preserve slots we're not updating
            existing = polls[self.poll_id]["selections"][user_id_str].get(self.event_name, [None, None])
            if not isinstance(existing, list):
                existing = [None, None]

            # Update slots
            selections_list = [
                {"day": self.selected_slot1_day, "time": self.selected_slot1_time} if has_slot1 else existing[0],
                {"day": self.selected_slot2_day, "time": self.selected_slot2_time} if has_slot2 else (existing[1] if len(existing) > 1 else None)
            ]

            polls[self.poll_id]["selections"][user_id_str][self.event_name] = selections_list
            poll_data = polls[self.poll_id]

        # Update the poll embed
        if poll_data:
            await self._update_poll_display(interaction, poll_data)

        # Auto-dismiss the ephemeral message
        selection_parts = []
        if has_slot1:
            selection_parts.append(f"Slot 1: {self.selected_slot1_day} at {self.selected_slot1_time}")
        if has_slot2:
            selection_parts.append(f"Slot 2: {self.selected_slot2_day} at {self.selected_slot2_time}")

        await interaction.response.edit_message(
            content=f"✅ Selection saved for **{self.event_name}**!\n{chr(10).join(selection_parts)}",
            view=None
        )
        await interaction.delete_original_response()

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

        # Update the poll embed
        if poll_data:
            await self._update_poll_display(interaction, poll_data)

        # Auto-dismiss the ephemeral message
        await interaction.response.edit_message(
            content=f"🗑️ Cleared selection for **{self.event_name}**",
            view=None
        )
        await interaction.delete_original_response()

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        await interaction.response.edit_message(
            content="Selection cancelled.",
            view=None
        )
        await interaction.delete_original_response()

    async def _update_poll_display(self, interaction: discord.Interaction, poll_data: Dict):
        """Update the poll embed and calendar"""
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

            # Update any results messages for this poll
            await self.cog._update_results_messages(interaction.guild, poll_data, self.poll_id)
        except Exception:
            pass

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

class EventResultsView(discord.ui.View):
    """View with Return and Close buttons for individual event results"""

    def __init__(self, cog, guild_id: int, poll_id: str, winning_times: Dict, selections: Dict, events: Dict):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.winning_times = winning_times
        self.selections = selections
        self.events = events

        # Return button
        return_btn = discord.ui.Button(
            label="Return to Results",
            style=discord.ButtonStyle.primary,
            emoji="↩️"
        )
        return_btn.callback = self._return_to_results
        self.add_item(return_btn)

        # Close button
        close_btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
        close_btn.callback = self._close
        self.add_item(close_btn)

    async def _return_to_results(self, interaction: discord.Interaction):
        """Return to main results view"""
        # Dismiss current event results message
        await interaction.response.edit_message(view=None)
        await interaction.delete_original_response()

        # Recreate the results view
        intro_text = self.cog.format_results_intro(self.selections)
        results_view = ResultsCategoryView(
            self.cog, self.guild_id, self.poll_id,
            self.winning_times, self.selections, self.events
        )

        # Send new results message
        await interaction.followup.send(
            intro_text,
            view=results_view,
            ephemeral=True
        )

    async def _close(self, interaction: discord.Interaction):
        """Close the event results"""
        await interaction.response.edit_message(view=None)
        await interaction.delete_original_response()


class ResultsCategoryView(discord.ui.View):
    """View with buttons for each event category to show results"""

    def __init__(self, cog, guild_id: int, poll_id: str, winning_times: Dict, selections: Dict, events: Dict):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.winning_times = winning_times
        self.selections = selections
        self.events = events

        # Row 0: Close, Hero's Realm, Sword Trial
        # Row 1: Party, Breaking Army, Showdown

        # Add close button first (row 0)
        close_btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=0
        )
        close_btn.callback = self._close
        self.add_item(close_btn)

        # Add buttons for each event in specific rows
        for event_name, event_info in events.items():
            # Determine button style and row based on event
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
                emoji=event_info["emoji"],
                custom_id=f"results:{event_name}",
                row=row
            )
            button.callback = self._create_results_callback(event_name)
            self.add_item(button)

    def _create_results_callback(self, event_name: str):
        async def callback(interaction: discord.Interaction):
            # Dismiss the results overview message
            await interaction.response.edit_message(view=None)
            await interaction.delete_original_response()

            # Format results for this event
            event_results = self.cog.format_event_results(event_name, self.winning_times, self.selections)

            # Create view with Return and Close buttons
            event_results_view = EventResultsView(
                self.cog, self.guild_id, self.poll_id,
                self.winning_times, self.selections, self.events
            )

            # Send event results as new ephemeral message
            await interaction.followup.send(
                content=event_results,
                view=event_results_view,
                ephemeral=True
            )

        return callback

    async def _close(self, interaction: discord.Interaction):
        """Close the results view"""
        await interaction.response.edit_message(view=None)
        await interaction.delete_original_response()

    async def on_timeout(self):
        """Handle timeout"""
        pass

