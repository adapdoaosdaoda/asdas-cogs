"""Modal forms for event poll voting"""

import discord
from typing import Dict, Optional
from datetime import datetime


class EventVotingModal(discord.ui.Modal):
    """Modal for voting on a single event's time slots"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 event_name: str, event_info: Dict, user_selections: Dict, events: Dict):
        super().__init__(title=f"Vote: {event_name}")

        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.event_info = event_info
        self.user_selections = user_selections
        self.events = events

        # Get current selection for this event
        current_selection = user_selections.get(event_name)

        # Create text inputs based on event type
        event_type = event_info["type"]
        num_slots = event_info["slots"]

        if event_type == "daily":
            # Daily event - single time input
            current_time = ""
            if current_selection and isinstance(current_selection, dict):
                current_time = current_selection.get("time", "")

            self.time_input = discord.ui.TextInput(
                label="Time (HH:MM, 18:00-24:00)",
                placeholder="e.g., 18:00, 20:30",
                default=current_time,
                required=False,
                max_length=5
            )
            self.add_item(self.time_input)

        elif event_type == "fixed_days":
            # Fixed-day event - time inputs for each day
            days = event_info["days"]

            if num_slots > 1:
                # Multi-slot: one input per day
                self.time_inputs = []
                for idx, day in enumerate(days[:5]):  # Max 5 inputs for modal limit
                    current_time = ""
                    if current_selection and isinstance(current_selection, list):
                        if idx < len(current_selection) and current_selection[idx]:
                            current_time = current_selection[idx].get("time", "")

                    time_input = discord.ui.TextInput(
                        label=f"{day[:3]} Time (HH:MM)",
                        placeholder="e.g., 18:00",
                        default=current_time,
                        required=False,
                        max_length=5
                    )
                    self.time_inputs.append((day, time_input))
                    self.add_item(time_input)
            else:
                # Single slot for all days
                current_time = ""
                if current_selection and isinstance(current_selection, dict):
                    current_time = current_selection.get("time", "")

                days_str = "/".join([d[:3] for d in days])
                self.time_input = discord.ui.TextInput(
                    label=f"Time for {days_str} (HH:MM)",
                    placeholder="e.g., 18:00",
                    default=current_time,
                    required=False,
                    max_length=5
                )
                self.add_item(self.time_input)

        else:
            # Weekly event - day and time inputs
            self.time_inputs = []
            for slot_idx in range(num_slots):
                current_value = ""
                if current_selection and isinstance(current_selection, list):
                    if slot_idx < len(current_selection) and current_selection[slot_idx]:
                        slot = current_selection[slot_idx]
                        current_value = f"{slot.get('day', '')} {slot.get('time', '')}".strip()

                label = f"Slot {slot_idx + 1}" if num_slots > 1 else "Day and Time"
                time_input = discord.ui.TextInput(
                    label=f"{label} (Day HH:MM)",
                    placeholder="e.g., Monday 18:00, Fri 20:30",
                    default=current_value,
                    required=False,
                    max_length=20
                )
                self.time_inputs.append(time_input)
                self.add_item(time_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        try:
            # Parse inputs based on event type
            event_type = self.event_info["type"]
            num_slots = self.event_info["slots"]
            new_selections = []

            if event_type == "daily":
                # Parse single time input
                time_str = self.time_input.value.strip()
                if time_str:
                    if not self._validate_time_format(time_str):
                        await interaction.response.send_message(
                            f"❌ Invalid time format: '{time_str}'. Use HH:MM (e.g., 18:00)",
                            ephemeral=True
                        )
                        return

                    # Check conflict
                    has_conflict, conflict_msg = self.cog.check_time_conflict(
                        self.user_selections,
                        self.event_name,
                        None,  # No day for daily events
                        time_str,
                        0
                    )

                    if has_conflict:
                        await interaction.response.send_message(
                            f"⚠️ **Conflict detected!**\n{conflict_msg}",
                            ephemeral=True
                        )
                        return

                    new_selection = {"time": time_str}
                else:
                    new_selection = None

            elif event_type == "fixed_days":
                days = self.event_info["days"]

                if num_slots > 1:
                    # Multi-slot: parse each day's time
                    for idx, (day, time_input) in enumerate(self.time_inputs):
                        time_str = time_input.value.strip()
                        if time_str:
                            if not self._validate_time_format(time_str):
                                await interaction.response.send_message(
                                    f"❌ Invalid time format for {day}: '{time_str}'. Use HH:MM (e.g., 18:00)",
                                    ephemeral=True
                                )
                                return

                            # Check conflict
                            has_conflict, conflict_msg = self.cog.check_time_conflict(
                                self.user_selections,
                                self.event_name,
                                day,
                                time_str,
                                idx
                            )

                            if has_conflict:
                                await interaction.response.send_message(
                                    f"⚠️ **Conflict detected for {day}!**\n{conflict_msg}",
                                    ephemeral=True
                                )
                                return

                            new_selections.append({"time": time_str, "day": day})
                        else:
                            new_selections.append(None)

                    # If all slots are empty, treat as clearing the selection
                    if all(s is None for s in new_selections):
                        new_selection = None
                    else:
                        new_selection = new_selections
                else:
                    # Single slot for all days
                    time_str = self.time_input.value.strip()
                    if time_str:
                        if not self._validate_time_format(time_str):
                            await interaction.response.send_message(
                                f"❌ Invalid time format: '{time_str}'. Use HH:MM (e.g., 18:00)",
                                ephemeral=True
                            )
                            return

                        # Check conflict (for fixed-day events, check against None since it applies to all days)
                        has_conflict, conflict_msg = self.cog.check_time_conflict(
                            self.user_selections,
                            self.event_name,
                            None,
                            time_str,
                            0
                        )

                        if has_conflict:
                            await interaction.response.send_message(
                                f"⚠️ **Conflict detected!**\n{conflict_msg}",
                                ephemeral=True
                            )
                            return

                        new_selection = {"time": time_str}
                    else:
                        new_selection = None

            else:
                # Weekly event - parse day and time for each slot
                for slot_idx, time_input in enumerate(self.time_inputs):
                    input_str = time_input.value.strip()
                    if input_str:
                        # Parse "Day HH:MM" format
                        parts = input_str.split()
                        if len(parts) < 2:
                            await interaction.response.send_message(
                                f"❌ Invalid format for slot {slot_idx + 1}: '{input_str}'. Use 'Day HH:MM' (e.g., Monday 18:00)",
                                ephemeral=True
                            )
                            return

                        day_str = parts[0]
                        time_str = parts[1]

                        # Validate day
                        day = self._parse_day(day_str)
                        if not day:
                            await interaction.response.send_message(
                                f"❌ Invalid day for slot {slot_idx + 1}: '{day_str}'. Use full or 3-letter day names (e.g., Monday, Mon)",
                                ephemeral=True
                            )
                            return

                        # Validate time
                        if not self._validate_time_format(time_str):
                            await interaction.response.send_message(
                                f"❌ Invalid time format for slot {slot_idx + 1}: '{time_str}'. Use HH:MM (e.g., 18:00)",
                                ephemeral=True
                            )
                            return

                        # Check conflict
                        has_conflict, conflict_msg = self.cog.check_time_conflict(
                            self.user_selections,
                            self.event_name,
                            day,
                            time_str,
                            slot_idx
                        )

                        if has_conflict:
                            await interaction.response.send_message(
                                f"⚠️ **Conflict detected for slot {slot_idx + 1}!**\n{conflict_msg}",
                                ephemeral=True
                            )
                            return

                        new_selections.append({"day": day, "time": time_str})
                    else:
                        new_selections.append(None)

                # If all slots are empty, treat as clearing the selection
                if all(s is None for s in new_selections):
                    new_selection = None
                else:
                    new_selection = new_selections

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

                # Save or clear the selection
                if new_selection is None:
                    # Clear selection
                    if self.event_name in polls[self.poll_id]["selections"][user_id_str]:
                        del polls[self.poll_id]["selections"][user_id_str][self.event_name]
                else:
                    polls[self.poll_id]["selections"][user_id_str][self.event_name] = new_selection

                poll_data = polls[self.poll_id]

            # Create confirmation message
            if new_selection is None:
                confirmation = f"🗑️ Cleared your selection for **{self.event_name}**"
            else:
                confirmation = f"✅ Selection saved for **{self.event_name}**!"

            # Show user's current selections
            current_selections = await self._get_user_selections_text()

            await interaction.response.send_message(
                f"{confirmation}\n\n**Your current selections:**\n{current_selections}",
                ephemeral=True
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

                    # Update calendar messages
                    await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)
                except Exception:
                    # Silently fail if we can't update
                    pass

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    def _validate_time_format(self, time_str: str) -> bool:
        """Validate time format (HH:MM)"""
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    def _parse_day(self, day_str: str) -> Optional[str]:
        """Parse day string to full day name"""
        day_str = day_str.lower().strip()

        days_map = {
            "mon": "Monday", "monday": "Monday",
            "tue": "Tuesday", "tuesday": "Tuesday",
            "wed": "Wednesday", "wednesday": "Wednesday",
            "thu": "Thursday", "thursday": "Thursday",
            "fri": "Friday", "friday": "Friday",
            "sat": "Saturday", "saturday": "Saturday",
            "sun": "Sunday", "sunday": "Sunday"
        }

        return days_map.get(day_str)

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
