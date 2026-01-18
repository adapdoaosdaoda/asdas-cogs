"""Voting modals using modalpatch for rich modal support"""

import discord
from typing import Dict, List
import logging

# Import modalpatch components
try:
    from discord.ui import Modal, TextDisplay, StringSelect
except ImportError:
    # Fallback if modalpatch not loaded
    from discord.ui import Modal
    try:
        from discord.ui import StringSelect
    except ImportError:
        from discord.ui import Select as StringSelect
    TextDisplay = None

log = logging.getLogger("red.asdas-cogs.polling")


class SimpleEventVoteModal(Modal, title="Vote for Event Times"):
    """Modal for Party, Hero's Realm (Catch-up), and Sword Trial votes

    This modal handles:
    - Party: Daily time vote
    - Hero's Realm (Catch-up): Single day+time vote (Mon-Sat)
    - Sword Trial: Two day votes (Wed, Fri) with times
    """

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int, event_name: str,
                 user_selections: Dict, events: Dict, days: List[str] = None):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.user_selections = user_selections
        self.events = events
        self.days = days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # Update modal title
        self.title = f"Vote: {event_name}"

        # Get event info
        event_info = events[event_name]
        timezone_display = cog.timezone_display

        # Add header
        if TextDisplay:
            self.add_item(TextDisplay(
                content=f"Select your preferred times\nTimezone: {timezone_display}",
                style=1
            ))

        # Generate time options
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

        # Get current selections
        current_selections = user_selections.get(event_name)

        if event_info["type"] == "daily":
            # Party - single time selection
            time_options = [
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(current_selections == time_str if current_selections else False)
                )
                for time_str in times[:25]  # Discord limit of 25 options
            ]

            self.time_select = StringSelect(
                placeholder=f"Choose a time... {timezone_display}",
                options=time_options,
                custom_id="party_time_select"
            )
            self.add_item(self.time_select)

        elif event_info["type"] == "once":
            # Hero's Realm (Catch-up) - day + time selection
            available_days = event_info.get("days", self.days)
            current_day = None
            current_time = None

            if current_selections and isinstance(current_selections, list) and len(current_selections) > 0:
                if isinstance(current_selections[0], dict):
                    current_day = current_selections[0].get("day")
                    current_time = current_selections[0].get("time")

            # Day selection
            day_options = [
                discord.SelectOption(
                    label=day,
                    value=day,
                    emoji="📅",
                    default=(day == current_day)
                )
                for day in available_days
            ]

            self.day_select = StringSelect(
                placeholder="Choose a day...",
                options=day_options,
                custom_id="hero_day_select"
            )
            self.add_item(self.day_select)

            # Time selection
            time_options = [
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(time_str == current_time)
                )
                for time_str in times[:25]
            ]

            self.time_select = StringSelect(
                placeholder=f"Choose a time... {timezone_display}",
                options=time_options,
                custom_id="hero_time_select"
            )
            self.add_item(self.time_select)

        elif event_info["type"] == "fixed_days":
            # Sword Trial - multiple fixed days (Wed, Fri)
            fixed_days = event_info.get("days", [])
            self.day_selects = {}

            for idx, day in enumerate(fixed_days[:2]):  # Max 2 days to stay under 5-item limit
                current_time = None
                if current_selections and isinstance(current_selections, list):
                    if idx < len(current_selections) and current_selections[idx]:
                        current_time = current_selections[idx].get("time")

                time_options = [
                    discord.SelectOption(
                        label=time_str,
                        value=time_str,
                        emoji="🕐",
                        default=(time_str == current_time)
                    )
                    for time_str in times[:25]
                ]

                day_select = StringSelect(
                    placeholder=f"{day[:3]} - Choose a time... {timezone_display}",
                    options=time_options,
                    custom_id=f"sword_day_{idx}_select"
                )
                self.day_selects[day] = day_select
                self.add_item(day_select)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        try:
            event_info = self.events[self.event_name]

            # Defer the response
            await interaction.response.defer()

            # Build selections based on event type
            if event_info["type"] == "daily":
                # Party - single time string
                if self.time_select.values:
                    selection = self.time_select.values[0]
                else:
                    selection = None

            elif event_info["type"] == "once":
                # Hero's Realm (Catch-up) - single day+time dict in list
                if self.day_select.values and self.time_select.values:
                    selection = [{
                        "day": self.day_select.values[0],
                        "time": self.time_select.values[0]
                    }]
                else:
                    selection = None

            elif event_info["type"] == "fixed_days":
                # Sword Trial - list of day+time dicts
                fixed_days = event_info.get("days", [])
                selection = []
                for day in fixed_days:
                    if day in self.day_selects:
                        day_select = self.day_selects[day]
                        if day_select.values:
                            selection.append({"time": day_select.values[0]})
                        else:
                            selection.append(None)
                    else:
                        selection.append(None)

            # Save to config
            async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
                if self.poll_id not in polls:
                    await interaction.followup.send(
                        "This poll is no longer active!",
                        ephemeral=True
                    )
                    return

                user_id_str = str(self.user_id)
                if user_id_str not in polls[self.poll_id]["selections"]:
                    polls[self.poll_id]["selections"][user_id_str] = {}

                polls[self.poll_id]["selections"][user_id_str][self.event_name] = selection
                poll_data = polls[self.poll_id]

            # Update the poll embed
            await self.cog._update_poll_message(self.guild_id, self.poll_id, poll_data)

            # Send confirmation
            if selection:
                await interaction.followup.send(
                    f"✅ Your vote for **{self.event_name}** has been saved!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Please select all required options.",
                    ephemeral=True
                )

        except Exception as e:
            log.error(f"Error in SimpleEventVoteModal.on_submit: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An error occurred while saving your vote. Please try again.",
                    ephemeral=True
                )
            except:
                pass


class BreakingArmyVoteModal(Modal, title="Vote: Breaking Army"):
    """Modal for Breaking Army votes (2 slots with day+time)"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int, event_name: str,
                 user_selections: Dict, events: Dict, days: List[str]):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.user_selections = user_selections
        self.events = events
        self.days = days

        # Get event info
        event_info = events[event_name]
        timezone_display = cog.timezone_display

        # Add header
        if TextDisplay:
            self.add_item(TextDisplay(
                content=f"Select your 2 preferred slots\nTimezone: {timezone_display}",
                style=1
            ))

        # Generate time options
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

        # Get current selections
        current_selections = user_selections.get(event_name, [None, None])
        current_slot1 = current_selections[0] if len(current_selections) > 0 else None
        current_slot2 = current_selections[1] if len(current_selections) > 1 else None

        # Slot 1 - Day
        day_options_1 = [
            discord.SelectOption(
                label=day,
                value=day,
                emoji="📅",
                default=(current_slot1 and current_slot1.get("day") == day)
            )
            for day in days
        ]

        self.slot1_day_select = StringSelect(
            placeholder="Slot 1: Choose a day...",
            options=day_options_1,
            custom_id="ba_slot1_day_select"
        )
        self.add_item(self.slot1_day_select)

        # Slot 1 - Time
        time_options_1 = [
            discord.SelectOption(
                label=time_str,
                value=time_str,
                emoji="🕐",
                default=(current_slot1 and current_slot1.get("time") == time_str)
            )
            for time_str in times[:25]
        ]

        self.slot1_time_select = StringSelect(
            placeholder=f"Slot 1: Choose a time... {timezone_display}",
            options=time_options_1,
            custom_id="ba_slot1_time_select"
        )
        self.add_item(self.slot1_time_select)

        # Slot 2 - Day
        day_options_2 = [
            discord.SelectOption(
                label=day,
                value=day,
                emoji="📅",
                default=(current_slot2 and current_slot2.get("day") == day)
            )
            for day in days
        ]

        self.slot2_day_select = StringSelect(
            placeholder="Slot 2: Choose a day...",
            options=day_options_2,
            custom_id="ba_slot2_day_select"
        )
        self.add_item(self.slot2_day_select)

        # Slot 2 - Time
        time_options_2 = [
            discord.SelectOption(
                label=time_str,
                value=time_str,
                emoji="🕐",
                default=(current_slot2 and current_slot2.get("time") == time_str)
            )
            for time_str in times[:25]
        ]

        self.slot2_time_select = StringSelect(
            placeholder=f"Slot 2: Choose a time... {timezone_display}",
            options=time_options_2,
            custom_id="ba_slot2_time_select"
        )
        self.add_item(self.slot2_time_select)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        try:
            # Defer the response
            await interaction.response.defer()

            # Build selections
            has_slot1 = self.slot1_day_select.values and self.slot1_time_select.values
            has_slot2 = self.slot2_day_select.values and self.slot2_time_select.values

            if not (has_slot1 or has_slot2):
                await interaction.followup.send(
                    "❌ Please select at least one complete slot (day + time).",
                    ephemeral=True
                )
                return

            selection = [
                {
                    "day": self.slot1_day_select.values[0],
                    "time": self.slot1_time_select.values[0]
                } if has_slot1 else None,
                {
                    "day": self.slot2_day_select.values[0],
                    "time": self.slot2_time_select.values[0]
                } if has_slot2 else None
            ]

            # Save to config
            async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
                if self.poll_id not in polls:
                    await interaction.followup.send(
                        "This poll is no longer active!",
                        ephemeral=True
                    )
                    return

                user_id_str = str(self.user_id)
                if user_id_str not in polls[self.poll_id]["selections"]:
                    polls[self.poll_id]["selections"][user_id_str] = {}

                polls[self.poll_id]["selections"][user_id_str][self.event_name] = selection
                poll_data = polls[self.poll_id]

            # Update the poll embed
            await self.cog._update_poll_message(self.guild_id, self.poll_id, poll_data)

            # Send confirmation
            await interaction.followup.send(
                f"✅ Your votes for **{self.event_name}** have been saved!",
                ephemeral=True
            )

        except Exception as e:
            log.error(f"Error in BreakingArmyVoteModal.on_submit: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An error occurred while saving your vote. Please try again.",
                    ephemeral=True
                )
            except:
                pass


class ShowdownVoteModal(Modal, title="Vote: Showdown"):
    """Modal for Showdown votes (2 slots with day+time)"""

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int, event_name: str,
                 user_selections: Dict, events: Dict, days: List[str]):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.event_name = event_name
        self.user_selections = user_selections
        self.events = events
        self.days = days

        # Get event info
        event_info = events[event_name]
        timezone_display = cog.timezone_display

        # Add header
        if TextDisplay:
            self.add_item(TextDisplay(
                content=f"Select your 2 preferred slots\nTimezone: {timezone_display}",
                style=1
            ))

        # Generate time options
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

        # Get current selections
        current_selections = user_selections.get(event_name, [None, None])
        current_slot1 = current_selections[0] if len(current_selections) > 0 else None
        current_slot2 = current_selections[1] if len(current_selections) > 1 else None

        # Slot 1 - Day
        day_options_1 = [
            discord.SelectOption(
                label=day,
                value=day,
                emoji="📅",
                default=(current_slot1 and current_slot1.get("day") == day)
            )
            for day in days
        ]

        self.slot1_day_select = StringSelect(
            placeholder="Slot 1: Choose a day...",
            options=day_options_1,
            custom_id="sd_slot1_day_select"
        )
        self.add_item(self.slot1_day_select)

        # Slot 1 - Time
        time_options_1 = [
            discord.SelectOption(
                label=time_str,
                value=time_str,
                emoji="🕐",
                default=(current_slot1 and current_slot1.get("time") == time_str)
            )
            for time_str in times[:25]
        ]

        self.slot1_time_select = StringSelect(
            placeholder=f"Slot 1: Choose a time... {timezone_display}",
            options=time_options_1,
            custom_id="sd_slot1_time_select"
        )
        self.add_item(self.slot1_time_select)

        # Slot 2 - Day
        day_options_2 = [
            discord.SelectOption(
                label=day,
                value=day,
                emoji="📅",
                default=(current_slot2 and current_slot2.get("day") == day)
            )
            for day in days
        ]

        self.slot2_day_select = StringSelect(
            placeholder="Slot 2: Choose a day...",
            options=day_options_2,
            custom_id="sd_slot2_day_select"
        )
        self.add_item(self.slot2_day_select)

        # Slot 2 - Time
        time_options_2 = [
            discord.SelectOption(
                label=time_str,
                value=time_str,
                emoji="🕐",
                default=(current_slot2 and current_slot2.get("time") == time_str)
            )
            for time_str in times[:25]
        ]

        self.slot2_time_select = StringSelect(
            placeholder=f"Slot 2: Choose a time... {timezone_display}",
            options=time_options_2,
            custom_id="sd_slot2_time_select"
        )
        self.add_item(self.slot2_time_select)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        try:
            # Defer the response
            await interaction.response.defer()

            # Build selections
            has_slot1 = self.slot1_day_select.values and self.slot1_time_select.values
            has_slot2 = self.slot2_day_select.values and self.slot2_time_select.values

            if not (has_slot1 or has_slot2):
                await interaction.followup.send(
                    "❌ Please select at least one complete slot (day + time).",
                    ephemeral=True
                )
                return

            selection = [
                {
                    "day": self.slot1_day_select.values[0],
                    "time": self.slot1_time_select.values[0]
                } if has_slot1 else None,
                {
                    "day": self.slot2_day_select.values[0],
                    "time": self.slot2_time_select.values[0]
                } if has_slot2 else None
            ]

            # Save to config
            async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
                if self.poll_id not in polls:
                    await interaction.followup.send(
                        "This poll is no longer active!",
                        ephemeral=True
                    )
                    return

                user_id_str = str(self.user_id)
                if user_id_str not in polls[self.poll_id]["selections"]:
                    polls[self.poll_id]["selections"][user_id_str] = {}

                polls[self.poll_id]["selections"][user_id_str][self.event_name] = selection
                poll_data = polls[self.poll_id]

            # Update the poll embed
            await self.cog._update_poll_message(self.guild_id, self.poll_id, poll_data)

            # Send confirmation
            await interaction.followup.send(
                f"✅ Your votes for **{self.event_name}** have been saved!",
                ephemeral=True
            )

        except Exception as e:
            log.error(f"Error in ShowdownVoteModal.on_submit: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An error occurred while saving your vote. Please try again.",
                    ephemeral=True
                )
            except:
                pass
