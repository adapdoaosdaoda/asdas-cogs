"""Voting modals using modalpatch for rich modal support"""

import discord
from typing import Dict, List
import logging

# Import modalpatch components
try:
    from discord.ui import Modal, TextDisplay, StringSelect, Label
except ImportError:
    # Fallback if modalpatch not loaded
    from discord.ui import Modal
    try:
        from discord.ui import StringSelect
    except ImportError:
        from discord.ui import Select as StringSelect
    TextDisplay = None
    Label = None

log = logging.getLogger("red.asdas-cogs.polling")


class CombinedSimpleEventsModal(Modal, title="Vote: Party / Hero's Realm / Sword Trial"):
    """Combined modal for Party, Hero's Realm (Catch-up), and Sword Trial votes

    All three events are voted for in a single modal with 5 dropdowns:
    - Party time
    - Hero's Realm day + time
    - Sword Trial Wed time + Fri time
    """

    def __init__(self, cog, guild_id: int, poll_id: str, user_id: int,
                 user_selections: Dict, events: Dict, days: List[str] = None):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.user_id = user_id
        self.user_selections = user_selections
        self.events = events
        self.days = days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        timezone_display = cog.timezone_display
        
        # Dynamically resolve Label class to handle load order issues
        Label_cls = Label or getattr(discord.ui, "Label", None)

        # Track which selects we create
        self.selects = {}

        # 1. Party - time only (daily event)
        if "Party" in events:
            party_info = events["Party"]
            times = cog.generate_time_options(
                party_info["time_range"][0],
                party_info["time_range"][1],
                party_info["interval"],
                party_info["duration"],
                "Party"
            )

            current_party = user_selections.get("Party")
            time_options = [
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(current_party == time_str if current_party else False)
                )
                for time_str in times[:25]
            ]

            party_select = StringSelect(
                placeholder=f"Choose a time... {timezone_display}",
                options=time_options,
                custom_id="party_time_select"
            )
            self.selects["Party"] = {"time": party_select}
            
            if Label_cls:
                self.add_item(Label_cls(
                    label="🎉 Party",
                    description="times in server time (UTC+1)",
                    child=party_select
                ))
            else:
                self.add_item(party_select)

        # 2. Hero's Realm (Catch-up) - day + time
        if "Hero's Realm (Catch-up)" in events:
            hero_info = events["Hero's Realm (Catch-up)"]
            available_days = hero_info.get("days", self.days)
            times = cog.generate_time_options(
                hero_info["time_range"][0],
                hero_info["time_range"][1],
                hero_info["interval"],
                hero_info["duration"],
                "Hero's Realm (Catch-up)"
            )

            current_hero = user_selections.get("Hero's Realm (Catch-up)")
            current_day = None
            current_time = None
            if current_hero and isinstance(current_hero, list) and len(current_hero) > 0:
                if isinstance(current_hero[0], dict):
                    current_day = current_hero[0].get("day")
                    current_time = current_hero[0].get("time")

            # Day select
            day_options = [
                discord.SelectOption(
                    label=day,
                    value=day,
                    emoji="📅",
                    default=(day == current_day)
                )
                for day in available_days
            ]

            hero_day_select = StringSelect(
                placeholder="Choose a day...",
                options=day_options,
                custom_id="hero_day_select"
            )
            
            if Label_cls:
                self.add_item(Label_cls(
                    label="🛡️ Hero's Realm (Catch-up) Day",
                    description="description: Monday - Saturday",
                    child=hero_day_select
                ))
            else:
                self.add_item(hero_day_select)

            # Time select
            time_options = [
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(time_str == current_time)
                )
                for time_str in times[:25]
            ]

            hero_time_select = StringSelect(
                placeholder=f"Choose a time... {timezone_display}",
                options=time_options,
                custom_id="hero_time_select"
            )
            self.selects["Hero's Realm (Catch-up)"] = {"day": hero_day_select, "time": hero_time_select}
            
            if Label_cls:
                self.add_item(Label_cls(
                    label="🛡️ Hero's Realm (Catch-up) Time",
                    description="description: times in server time (UTC+1)",
                    child=hero_time_select
                ))
            else:
                self.add_item(hero_time_select)

        # 3. Sword Trial - Wed time + Fri time
        if "Sword Trial" in events:
            sword_info = events["Sword Trial"]
            times = cog.generate_time_options(
                sword_info["time_range"][0],
                sword_info["time_range"][1],
                sword_info["interval"],
                sword_info["duration"],
                "Sword Trial"
            )

            current_sword = user_selections.get("Sword Trial")
            current_wed = None
            current_fri = None
            if current_sword and isinstance(current_sword, list):
                if len(current_sword) > 0 and current_sword[0]:
                    current_wed = current_sword[0].get("time")
                if len(current_sword) > 1 and current_sword[1]:
                    current_fri = current_sword[1].get("time")

            # Wednesday time
            wed_options = [
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(time_str == current_wed)
                )
                for time_str in times[:25]
            ]

            wed_select = StringSelect(
                placeholder=f"Choose a time... {timezone_display}",
                options=wed_options,
                custom_id="sword_wed_select"
            )
            
            if Label_cls:
                self.add_item(Label_cls(
                    label="⚔️ Sword Trial Wednesday Time",
                    description="description: times in server time (UTC+1)",
                    child=wed_select
                ))
            else:
                self.add_item(wed_select)

            # Friday time
            fri_options = [
                discord.SelectOption(
                    label=time_str,
                    value=time_str,
                    emoji="🕐",
                    default=(time_str == current_fri)
                )
                for time_str in times[:25]
            ]

            fri_select = StringSelect(
                placeholder=f"Choose a time... {timezone_display}",
                options=fri_options,
                custom_id="sword_fri_select"
            )
            self.selects["Sword Trial"] = {"wed": wed_select, "fri": fri_select}
            
            if Label_cls:
                self.add_item(Label_cls(
                    label="⚔️ Sword Trial Friday Time",
                    description="description: times in server time (UTC+1)",
                    child=fri_select
                ))
            else:
                self.add_item(fri_select)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission - save all three events"""
        try:
            await interaction.response.defer()

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

                # Save Party vote
                if "Party" in self.selects:
                    party_select = self.selects["Party"]["time"]
                    if party_select.values:
                        polls[self.poll_id]["selections"][user_id_str]["Party"] = party_select.values[0]

                # Save Hero's Realm vote
                if "Hero's Realm (Catch-up)" in self.selects:
                    day_select = self.selects["Hero's Realm (Catch-up)"]["day"]
                    time_select = self.selects["Hero's Realm (Catch-up)"]["time"]
                    if day_select.values and time_select.values:
                        polls[self.poll_id]["selections"][user_id_str]["Hero's Realm (Catch-up)"] = [{
                            "day": day_select.values[0],
                            "time": time_select.values[0]
                        }]

                # Save Sword Trial votes
                if "Sword Trial" in self.selects:
                    wed_select = self.selects["Sword Trial"]["wed"]
                    fri_select = self.selects["Sword Trial"]["fri"]
                    selections = []
                    # Wednesday (index 0)
                    if wed_select.values:
                        selections.append({"time": wed_select.values[0]})
                    else:
                        selections.append(None)
                    # Friday (index 1)
                    if fri_select.values:
                        selections.append({"time": fri_select.values[0]})
                    else:
                        selections.append(None)

                    polls[self.poll_id]["selections"][user_id_str]["Sword Trial"] = selections

                poll_data = polls[self.poll_id]

            # Update the poll embed
            await self.cog._update_poll_message(self.guild_id, self.poll_id, poll_data)

            # Send confirmation
            await interaction.followup.send(
                "✅ Your votes have been saved!",
                ephemeral=True
            )

        except Exception as e:
            log.error(f"Error in CombinedSimpleEventsModal.on_submit: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An error occurred while saving your votes. Please try again.",
                    ephemeral=True
                )
            except:
                pass


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

        # Get current selections
        current_selections = user_selections.get(event_name)
        
        # Dynamically resolve Label class to handle load order issues
        Label_cls = Label or getattr(discord.ui, "Label", None)

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
            if Label_cls:
                self.add_item(Label_cls(
                    label=f"🎉 {event_name}",
                    description=f"times in server time (UTC+1)",
                    child=self.time_select
                ))
            else:
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
            if Label_cls:
                self.add_item(Label_cls(
                    label=f"🛡️ {event_name} Day",
                    description="description: Monday - Saturday",
                    child=self.day_select
                ))
            else:
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
            if Label_cls:
                self.add_item(Label_cls(
                    label=f"🛡️ {event_name} Time",
                    description="description: times in server time (UTC+1)",
                    child=self.time_select
                ))
            else:
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
                if Label_cls:
                    self.add_item(Label_cls(
                        label=f"⚔️ {event_name} {day} Time",
                        description="description: times in server time (UTC+1)",
                        child=day_select
                    ))
                else:
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

        # Generate time options
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

        # Get current selections
        current_selections = user_selections.get(event_name, [None, None])
        current_slot1 = current_selections[0] if len(current_selections) > 0 else None
        current_slot2 = current_selections[1] if len(current_selections) > 1 else None
        
        # Dynamically resolve Label class to handle load order issues
        Label_cls = Label or getattr(discord.ui, "Label", None)

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
        if Label_cls:
            self.add_item(Label_cls(
                label="⚡ Breaking Army Slot 1 Day",
                description="Monday - Sunday",
                child=self.slot1_day_select
            ))
        else:
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
            placeholder=f"Slot 1: Choose a time... {cog.timezone_display}",
            options=time_options_1,
            custom_id="ba_slot1_time_select"
        )
        if Label_cls:
            self.add_item(Label_cls(
                label="⚡ Breaking Army Slot 1 Time",
                description="Times in Server Time (UTC+1)",
                child=self.slot1_time_select
            ))
        else:
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
        if Label_cls:
            self.add_item(Label_cls(
                label="⚡ Breaking Army Slot 2 Day",
                description="Monday - Sunday",
                child=self.slot2_day_select
            ))
        else:
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
            placeholder=f"Slot 2: Choose a time... {cog.timezone_display}",
            options=time_options_2,
            custom_id="ba_slot2_time_select"
        )
        if Label_cls:
            self.add_item(Label_cls(
                label="⚡ Breaking Army Slot 2 Time",
                description="Times in Server Time (UTC+1)",
                child=self.slot2_time_select
            ))
        else:
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

        # Generate time options
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

        # Get current selections
        current_selections = user_selections.get(event_name, [None, None])
        current_slot1 = current_selections[0] if len(current_selections) > 0 else None
        current_slot2 = current_selections[1] if len(current_selections) > 1 else None
        
        # Dynamically resolve Label class to handle load order issues
        Label_cls = Label or getattr(discord.ui, "Label", None)

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
        if Label_cls:
            self.add_item(Label_cls(
                label="🏆 Showdown Slot 1 Day",
                description="Monday - Sunday",
                child=self.slot1_day_select
            ))
        else:
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
            placeholder=f"Slot 1: Choose a time... {cog.timezone_display}",
            options=time_options_1,
            custom_id="sd_slot1_time_select"
        )
        if Label_cls:
            self.add_item(Label_cls(
                label="🏆 Showdown Slot 1 Time",
                description="Times in Server Time (UTC+1)",
                child=self.slot1_time_select
            ))
        else:
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
        if Label_cls:
            self.add_item(Label_cls(
                label="🏆 Showdown Slot 2 Day",
                description="Monday - Sunday",
                child=self.slot2_day_select
            ))
        else:
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
            placeholder=f"Slot 2: Choose a time... {cog.timezone_display}",
            options=time_options_2,
            custom_id="sd_slot2_time_select"
        )
        if Label_cls:
            self.add_item(Label_cls(
                label="🏆 Showdown Slot 2 Time",
                description="Times in Server Time (UTC+1)",
                child=self.slot2_time_select
            ))
        else:
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
