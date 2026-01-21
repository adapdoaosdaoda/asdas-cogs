import discord
from typing import Optional, Dict, List
from datetime import datetime
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

# Import voting modals
from .voting_modals import CombinedSimpleEventsModal, BreakingArmyVoteModal, ShowdownVoteModal, SwordTrialVoteModal

log = logging.getLogger("red.asdas-cogs.polling")


# City to timezone mapping for common city names
CITY_TIMEZONE_MAP = {
    # Europe
    'london': 'Europe/London',
    'paris': 'Europe/Paris',
    'berlin': 'Europe/Berlin',
    'rome': 'Europe/Rome',
    'madrid': 'Europe/Madrid',
    'amsterdam': 'Europe/Amsterdam',
    'vienna': 'Europe/Vienna',
    'stockholm': 'Europe/Stockholm',
    'oslo': 'Europe/Oslo',
    'helsinki': 'Europe/Helsinki',
    'dublin': 'Europe/Dublin',
    'lisbon': 'Europe/Lisbon',
    'athens': 'Europe/Athens',
    'prague': 'Europe/Prague',
    'warsaw': 'Europe/Warsaw',
    'moscow': 'Europe/Moscow',
    'istanbul': 'Europe/Istanbul',

    # Americas
    'new york': 'America/New_York',
    'nyc': 'America/New_York',
    'los angeles': 'America/Los_Angeles',
    'la': 'America/Los_Angeles',
    'chicago': 'America/Chicago',
    'toronto': 'America/Toronto',
    'vancouver': 'America/Vancouver',
    'mexico city': 'America/Mexico_City',
    'sao paulo': 'America/Sao_Paulo',
    'buenos aires': 'America/Argentina/Buenos_Aires',
    'santiago': 'America/Santiago',
    'bogota': 'America/Bogota',
    'lima': 'America/Lima',
    'denver': 'America/Denver',
    'phoenix': 'America/Phoenix',
    'seattle': 'America/Los_Angeles',
    'miami': 'America/New_York',
    'boston': 'America/New_York',
    'washington': 'America/New_York',
    'montreal': 'America/Toronto',

    # Asia
    'tokyo': 'Asia/Tokyo',
    'beijing': 'Asia/Shanghai',
    'shanghai': 'Asia/Shanghai',
    'hong kong': 'Asia/Hong_Kong',
    'singapore': 'Asia/Singapore',
    'seoul': 'Asia/Seoul',
    'bangkok': 'Asia/Bangkok',
    'jakarta': 'Asia/Jakarta',
    'manila': 'Asia/Manila',
    'kuala lumpur': 'Asia/Kuala_Lumpur',
    'mumbai': 'Asia/Kolkata',
    'delhi': 'Asia/Kolkata',
    'dubai': 'Asia/Dubai',
    'riyadh': 'Asia/Riyadh',
    'tel aviv': 'Asia/Jerusalem',
    'taipei': 'Asia/Taipei',

    # Oceania
    'sydney': 'Australia/Sydney',
    'melbourne': 'Australia/Melbourne',
    'brisbane': 'Australia/Brisbane',
    'perth': 'Australia/Perth',
    'auckland': 'Pacific/Auckland',
    'wellington': 'Pacific/Auckland',

    # Africa
    'cairo': 'Africa/Cairo',
    'johannesburg': 'Africa/Johannesburg',
    'cape town': 'Africa/Johannesburg',
    'nairobi': 'Africa/Nairobi',
    'lagos': 'Africa/Lagos',
    'casablanca': 'Africa/Casablanca',
}


class DismissibleView(discord.ui.View):
    """Simple view with a close button for dismissible messages"""

    def __init__(self):
        super().__init__(timeout=180)

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

        # Row 0: Party / Catch-up / Guild War (Blue), Sword Trial (Blue)
        # Row 1: Breaking Army (Blue), Showdown (Blue)
        # Row 2: Results (Grey)
        
        # Party / Catch-up / Guild War button (Blue) - Row 0
        general_button = discord.ui.Button(
            label="Party / Catch-up / Guild War",
            style=discord.ButtonStyle.primary,
            emoji="📋",
            custom_id="event_poll:simple_events",
            row=0
        )
        general_button.callback = self._create_simple_events_callback()
        self.add_item(general_button)

        # Sword Trial button (Blue) - Row 0
        if "Sword Trial" in events:
            st_button = discord.ui.Button(
                label="Sword Trial",
                style=discord.ButtonStyle.primary,
                emoji=events["Sword Trial"]["emoji"],
                custom_id="event_poll:Sword Trial",
                row=0
            )
            st_button.callback = self._create_event_callback("Sword Trial")
            self.add_item(st_button)

        # Breaking Army button (Blue) - Row 1
        if "Breaking Army" in events:
            ba_button = discord.ui.Button(
                label="Breaking Army",
                style=discord.ButtonStyle.primary,
                emoji=events["Breaking Army"]["emoji"],
                custom_id="event_poll:Breaking Army",
                row=1
            )
            ba_button.callback = self._create_event_callback("Breaking Army")
            self.add_item(ba_button)

        # Showdown button (Blue) - Row 1
        if "Showdown" in events:
            sd_button = discord.ui.Button(
                label="Showdown",
                style=discord.ButtonStyle.primary,
                emoji=events["Showdown"]["emoji"],
                custom_id="event_poll:Showdown",
                row=1
            )
            sd_button.callback = self._create_event_callback("Showdown")
            self.add_item(sd_button)

        # Row 2: Results button (Grey)
        results_button = discord.ui.Button(
            label="Results",
            style=discord.ButtonStyle.secondary,
            emoji="🏆",
            custom_id="event_poll:results",
            row=2
        )
        results_button.callback = self._show_results
        self.add_item(results_button)

    def _create_simple_events_callback(self):
        """Create callback for combined simple events button"""
        async def callback(interaction: discord.Interaction):
            try:
                # Get poll_id from the message
                poll_id = str(interaction.message.id)

                # Get user's current selections
                polls = await self.cog.config.guild_from_id(self.guild_id).polls()
                if poll_id not in polls:
                    await interaction.response.send_message(
                        "This poll is no longer active!",
                        view=DismissibleView(),
                        ephemeral=True
                    )
                    return

                poll_data = polls[poll_id]
                user_id_str = str(interaction.user.id)
                user_selections = poll_data["selections"].get(user_id_str, {})

                # Open combined modal for Events
                modal = CombinedSimpleEventsModal(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    poll_id=poll_id,
                    user_id=interaction.user.id,
                    user_selections=user_selections,
                    events=self.events,
                    days=self.days
                )
                await interaction.response.send_modal(modal)

            except discord.HTTPException as e:
                log.error(f"Failed to respond to simple events vote interaction for user {interaction.user.id}: {e}")
            except discord.Forbidden as e:
                log.error(f"Missing permissions to respond to simple events vote interaction for user {interaction.user.id}: {e}")
            except Exception as e:
                log.error(f"Unexpected error in simple events vote interaction for user {interaction.user.id}: {e}", exc_info=True)

        return callback

    async def _show_results(self, interaction: discord.Interaction):
        """Show current poll results with category buttons"""
        try:
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

            # Format all results inline (no buttons needed)
            results_text = self.cog.format_all_results_inline(winning_times, selections)

            # Send results as ephemeral message with no view
            await interaction.response.send_message(
                results_text,
                ephemeral=True
            )
        except discord.HTTPException as e:
            log.error(f"Failed to show results for user {interaction.user.id}: {e}")
        except discord.Forbidden as e:
            log.error(f"Missing permissions to show results for user {interaction.user.id}: {e}")
        except Exception as e:
            log.error(f"Unexpected error showing results for user {interaction.user.id}: {e}", exc_info=True)

    def _create_event_callback(self, event_name: str):
        async def callback(interaction: discord.Interaction):
            try:
                # Get poll_id from the message (for persistent views)
                poll_id = str(interaction.message.id)

                # Get user's current selections
                polls = await self.cog.config.guild_from_id(self.guild_id).polls()
                if poll_id not in polls:
                    await interaction.response.send_message(
                        "This poll is no longer active!",
                        view=DismissibleView(),
                        ephemeral=True
                    )
                    return

                poll_data = polls[poll_id]
                user_id_str = str(interaction.user.id)
                user_selections = poll_data["selections"].get(user_id_str, {})

                # Check event type and show appropriate modal
                event_info = self.events[event_name]
                available_days = event_info.get("days", self.days)

                # Determine which modal to use
                if event_name == "Breaking Army":
                    modal = BreakingArmyVoteModal(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        event_name=event_name,
                        user_selections=user_selections,
                        events=self.events,
                        days=available_days
                    )
                    await interaction.response.send_modal(modal)

                elif event_name == "Showdown":
                    modal = ShowdownVoteModal(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        event_name=event_name,
                        user_selections=user_selections,
                        events=self.events,
                        days=available_days
                    )
                    await interaction.response.send_modal(modal)

                elif event_name == "Sword Trial":
                    modal = SwordTrialVoteModal(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        user_selections=user_selections,
                        events=self.events
                    )
                    await interaction.response.send_modal(modal)

                else:
                    # Fallback (General)
                    modal = CombinedSimpleEventsModal(
                        cog=self.cog,
                        guild_id=self.guild_id,
                        poll_id=poll_id,
                        user_id=interaction.user.id,
                        user_selections=user_selections,
                        events=self.events,
                        days=available_days
                    )
                    await interaction.response.send_modal(modal)

            except discord.HTTPException as e:
                log.error(f"Failed to respond to {event_name} vote interaction for user {interaction.user.id}: {e}")
            except discord.Forbidden as e:
                log.error(f"Missing permissions to respond to {event_name} vote interaction for user {interaction.user.id}: {e}")
            except Exception as e:
                log.error(f"Unexpected error in {event_name} vote interaction for user {interaction.user.id}: {e}", exc_info=True)

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
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

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

            time_select = discord.ui.Select(min_values=0, 
                placeholder="Choose a time...",
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
        try:
            self.selected_time = interaction.data["values"][0]
            await interaction.response.defer()
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                log.error(f"Rate limited when selecting time for user {interaction.user.id}: {e}")
            else:
                log.error(f"Failed to defer time selection for user {interaction.user.id}: {e}")
        except Exception as e:
            log.error(f"Unexpected error in time selection for user {interaction.user.id}: {e}", exc_info=True)

    async def _submit(self, interaction: discord.Interaction):
        """Handle submit"""
        try:
            if not self.selected_time:
                await interaction.response.send_message(
                    "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                    view=DismissibleView(),
                    ephemeral=True
                )
                try:
                    await interaction.delete_original_response()
                except:
                    pass
                return

            # Defer the response to avoid timeout
            await interaction.response.defer()

            # Save the selection
            poll_data = None
            async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
                if self.poll_id not in polls:
                    await interaction.followup.send(
                        "This poll is no longer active!",
                        view=DismissibleView(),
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
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                # Message was already deleted or interaction expired, which is fine
                pass
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                log.error(f"Rate limited when saving {self.event_name} vote for user {self.user_id}: {e}")
                try:
                    await interaction.response.send_message(
                        "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                        view=DismissibleView(),
                        ephemeral=True
                    )
                except:
                    # If we can't respond, try followup
                    try:
                        await interaction.followup.send(
                            "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                            view=DismissibleView(),
                            ephemeral=True
                        )
                    except:
                        pass
            else:
                log.error(f"Failed to save {self.event_name} vote for user {self.user_id}: {e}")
        except discord.Forbidden as e:
            log.error(f"Missing permissions to save {self.event_name} vote for user {self.user_id}: {e}")
        except Exception as e:
            log.error(f"Unexpected error saving {self.event_name} vote for user {self.user_id}: {e}", exc_info=True)

    async def _clear_selection(self, interaction: discord.Interaction):
        """Clear the user's selection for this event"""
        # Defer the response
        await interaction.response.defer()

        poll_data = None
        async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
            if self.poll_id not in polls:
                await interaction.followup.send(
                    "This poll is no longer active!",
                    view=DismissibleView(),
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
        try:
            await interaction.edit_original_response(
                content=f"🗑️ Cleared selection for **{self.event_name}**",
                view=None
            )
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            # Message was already deleted or interaction expired, which is fine
            pass

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        try:
            await interaction.response.edit_message(
                content="Selection cancelled.",
                view=None
            )
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            # Message was already deleted or interaction expired, which is fine
            pass

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

            # Update any live calendar messages for this poll
            await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)

            # Check if we need to create initial weekly snapshot (for first vote)
            await self.cog._check_and_create_initial_snapshot(interaction.guild, self.poll_id)
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
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

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

            day_select = discord.ui.Select(min_values=0, 
                placeholder="Choose a time...",
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
        try:
            if not self.selected_times:
                await interaction.response.send_message(
                    "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                    view=DismissibleView(),
                    ephemeral=True
                )
                try:
                    await interaction.delete_original_response()
                except:
                    pass
                return

            # Defer the response to avoid timeout
            await interaction.response.defer()

            # Save the selections
            poll_data = None
            async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
                if self.poll_id not in polls:
                    await interaction.followup.send(
                        "This poll is no longer active!",
                        view=DismissibleView(),
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
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                # Message was already deleted or interaction expired, which is fine
                pass
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                log.error(f"Rate limited when saving {self.event_name} vote for user {self.user_id}: {e}")
                try:
                    await interaction.response.send_message(
                        "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                        view=DismissibleView(),
                        ephemeral=True
                    )
                except:
                    # If we can't respond, try followup
                    try:
                        await interaction.followup.send(
                            "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                            view=DismissibleView(),
                            ephemeral=True
                        )
                    except:
                        pass
            else:
                log.error(f"Failed to save {self.event_name} vote for user {self.user_id}: {e}")
        except discord.Forbidden as e:
            log.error(f"Missing permissions to save {self.event_name} vote for user {self.user_id}: {e}")
        except Exception as e:
            log.error(f"Unexpected error saving {self.event_name} vote for user {self.user_id}: {e}", exc_info=True)

    async def _clear_selection(self, interaction: discord.Interaction):
        """Clear the user's selection for this event"""
        # Defer the response
        await interaction.response.defer()

        poll_data = None
        async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
            if self.poll_id not in polls:
                await interaction.followup.send(
                    "This poll is no longer active!",
                    view=DismissibleView(),
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
        try:
            await interaction.edit_original_response(
                content=f"🗑️ Cleared selection for **{self.event_name}**",
                view=None
            )
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            # Message was already deleted or interaction expired, which is fine
            pass

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        try:
            await interaction.response.edit_message(
                content="Selection cancelled.",
                view=None
            )
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            # Message was already deleted or interaction expired, which is fine
            pass

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

            # Update any live calendar messages for this poll
            await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)

            # Check if we need to create initial weekly snapshot (for first vote)
            await self.cog._check_and_create_initial_snapshot(interaction.guild, self.poll_id)
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
    """Modal for Breaking Army / Showdown / Hero's Realm (Catch-up) - 1-2 slots with day+time dropdowns each"""

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

        # Get event info and number of slots
        event_info = events[event_name]
        self.num_slots = event_info.get("slots", 2)

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
        start_hour, end_hour = event_info["time_range"]
        interval = event_info["interval"]
        duration = event_info["duration"]
        times = self.cog.generate_time_options(start_hour, end_hour, interval, duration, event_name)

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

        slot1_day_select = discord.ui.Select(min_values=0, 
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

        slot1_time_select = discord.ui.Select(min_values=0, 
            placeholder=f"Slot 1: Choose a time... {timezone_display}",
            options=time_options_1,
            custom_id="slot1_time_select",
            row=1
        )
        slot1_time_select.callback = self._slot1_time_selected
        self.add_item(slot1_time_select)

        # Only add Slot 2 if event has 2 slots
        if self.num_slots >= 2:
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

            slot2_day_select = discord.ui.Select(min_values=0, 
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

            slot2_time_select = discord.ui.Select(min_values=0, 
                placeholder=f"Slot 2: Choose a time... {timezone_display}",
                options=time_options_2,
                custom_id="slot2_time_select",
                row=3
            )
            slot2_time_select.callback = self._slot2_time_selected
            self.add_item(slot2_time_select)

        # Add buttons (row 4 for 2-slot events, row 2 for 1-slot events)
        button_row = 4 if self.num_slots >= 2 else 2
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
        try:
            # Check if at least one complete slot is selected
            has_slot1 = self.selected_slot1_day and self.selected_slot1_time
            has_slot2 = self.selected_slot2_day and self.selected_slot2_time

            if not has_slot1 and not has_slot2:
                await interaction.response.send_message(
                    "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                    view=DismissibleView(),
                    ephemeral=True
                )
                try:
                    await interaction.delete_original_response()
                except:
                    pass
                return

            # Defer the response to avoid timeout
            await interaction.response.defer()

            # Save the selections
            poll_data = None
            async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
                if self.poll_id not in polls:
                    await interaction.followup.send(
                        "This poll is no longer active!",
                        view=DismissibleView(),
                        ephemeral=True
                    )
                    return

                user_id_str = str(self.user_id)
                if user_id_str not in polls[self.poll_id]["selections"]:
                    polls[self.poll_id]["selections"][user_id_str] = {}

                # Get existing selections to preserve slots we're not updating
                if self.num_slots == 1:
                    # For 1-slot events, store as single-item list
                    selections_list = [
                        {"day": self.selected_slot1_day, "time": self.selected_slot1_time} if has_slot1 else None
                    ]
                else:
                    # For 2-slot events, store as two-item list
                    existing = polls[self.poll_id]["selections"][user_id_str].get(self.event_name, [None, None])
                    if not isinstance(existing, list):
                        existing = [None, None]

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
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                # Message was already deleted or interaction expired, which is fine
                pass
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                log.error(f"Rate limited when saving {self.event_name} vote for user {self.user_id}: {e}")
                try:
                    await interaction.response.send_message(
                        "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                        view=DismissibleView(),
                        ephemeral=True
                    )
                except:
                    # If we can't respond, try followup
                    try:
                        await interaction.followup.send(
                            "⏳ The bot is currently being rate-limited by Discord. Please try again in a few minutes.",
                            view=DismissibleView(),
                            ephemeral=True
                        )
                    except:
                        pass
            else:
                log.error(f"Failed to save {self.event_name} vote for user {self.user_id}: {e}")
        except discord.Forbidden as e:
            log.error(f"Missing permissions to save {self.event_name} vote for user {self.user_id}: {e}")
        except Exception as e:
            log.error(f"Unexpected error saving {self.event_name} vote for user {self.user_id}: {e}", exc_info=True)

    async def _clear_selection(self, interaction: discord.Interaction):
        """Clear the user's selection for this event"""
        # Defer the response
        await interaction.response.defer()

        poll_data = None
        async with self.cog.config.guild_from_id(self.guild_id).polls() as polls:
            if self.poll_id not in polls:
                await interaction.followup.send(
                    "This poll is no longer active!",
                    view=DismissibleView(),
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
        try:
            await interaction.edit_original_response(
                content=f"🗑️ Cleared selection for **{self.event_name}**",
                view=None
            )
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            # Message was already deleted or interaction expired, which is fine
            pass

    async def _cancel(self, interaction: discord.Interaction):
        """Handle cancel"""
        try:
            await interaction.response.edit_message(
                content="Selection cancelled.",
                view=None
            )
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            # Message was already deleted or interaction expired, which is fine
            pass

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

            # Update any live calendar messages for this poll
            await self.cog._update_calendar_messages(interaction.guild, poll_data, self.poll_id)

            # Check if we need to create initial weekly snapshot (for first vote)
            await self.cog._check_and_create_initial_snapshot(interaction.guild, self.poll_id)
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
    """View with Return button for individual event results"""

    def __init__(self, cog, guild_id: int, poll_id: str, winning_times: Dict, selections: Dict, events: Dict):
        super().__init__(timeout=None)  # No timeout - don't auto-close
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

    async def _return_to_results(self, interaction: discord.Interaction):
        """Return to main results view"""
        # Recreate the results view
        intro_text = self.cog.format_results_intro(self.selections)
        results_view = ResultsCategoryView(
            self.cog, self.guild_id, self.poll_id,
            self.winning_times, self.selections, self.events
        )

        # Edit the message with the new results view
        await interaction.response.edit_message(
            content=intro_text,
            view=results_view
        )


class ResultsCategoryView(discord.ui.View):
    """View with buttons for each event category to show results"""

    def __init__(self, cog, guild_id: int, poll_id: str, winning_times: Dict, selections: Dict, events: Dict):
        super().__init__(timeout=None)  # No timeout - don't auto-close
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.winning_times = winning_times
        self.selections = selections
        self.events = events

        # Row 0: Hero's Realm, Sword Trial
        # Row 1: Party, Breaking Army, Showdown

        # Add buttons for each event in specific rows
        for event_name, event_info in events.items():
            # Skip locked events in results (they always show in calendar)
            if event_info.get("type") == "locked":
                continue

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
            # Format results for this event
            event_results = self.cog.format_event_results(event_name, self.winning_times, self.selections)

            # Create view with Return button
            event_results_view = EventResultsView(
                self.cog, self.guild_id, self.poll_id,
                self.winning_times, self.selections, self.events
            )

            # Edit the message to show event results
            await interaction.response.edit_message(
                content=event_results,
                view=event_results_view
            )

        return callback



class TimezoneModal(discord.ui.Modal, title="Generate Calendar in Your Timezone"):
    """Modal for entering timezone"""

    timezone_input = discord.ui.TextInput(
        label="Timezone",
        placeholder="e.g., London, New York, Tokyo, or US/Eastern",
        style=discord.TextStyle.short,
        required=True,
        max_length=45
    )
    
    def __init__(self, cog, guild_id: int, poll_id: str, is_weekly: bool = False):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.is_weekly = is_weekly

    async def on_submit(self, interaction: discord.Interaction):
        """Handle timezone submission and generate calendar"""
        import pytz
        from io import BytesIO

        user_input = self.timezone_input.value.strip()

        # Try to map city name to timezone first
        normalized_input = user_input.lower()
        if normalized_input in CITY_TIMEZONE_MAP:
            timezone_str = CITY_TIMEZONE_MAP[normalized_input]
        else:
            timezone_str = user_input

        # Validate timezone
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            await interaction.response.send_message(
                f"❌ Unknown timezone or city: `{user_input}`\n\n"
                f"You can use city names like:\n"
                f"• London, Paris, Berlin\n"
                f"• New York, Los Angeles, Chicago\n"
                f"• Tokyo, Singapore, Sydney\n\n"
                f"Or standard timezone formats like:\n"
                f"• US/Eastern, US/Pacific\n"
                f"• Europe/London, Asia/Tokyo\n\n"
                f"See full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                view=DismissibleView(),
                ephemeral=True
            )
            return

        # Get poll data
        polls = await self.cog.config.guild_from_id(self.guild_id).polls()
        if self.poll_id not in polls:
            await interaction.response.send_message(
                "❌ This poll is no longer active!",
                view=DismissibleView(),
                ephemeral=True
            )
            return

        poll_data = polls[self.poll_id]

        # Calculate winning times - use cached snapshot for weekly calendars
        # Always get selections for total voter count
        selections = poll_data.get("selections", {})

        if self.is_weekly:
            # Use cached winning_times snapshot from Monday 10 AM
            winning_times = poll_data.get("weekly_snapshot_winning_times", {})
            if not winning_times:
                # Fallback to live data if no snapshot exists yet
                winning_times = self.cog._calculate_winning_times_weighted(selections)
        else:
            # Use live selections for real-time calendars
            winning_times = self.cog._calculate_winning_times_weighted(selections)

        # Convert to calendar data format first
        from datetime import datetime
        from .calendar_renderer import CalendarRenderer

        # Convert winning times to calendar data format
        calendar_data = self.cog._prepare_calendar_data(winning_times)

        # Create calendar renderer with user's timezone
        user_tz_renderer = CalendarRenderer(timezone=timezone_str)

        # Convert calendar data from server timezone to user timezone
        server_tz = pytz.timezone('Europe/Berlin')  # Server Time (UTC+1)
        user_tz = pytz.timezone(timezone_str)

        converted_calendar_data = {}
        for event_name, day_times in calendar_data.items():
            converted_calendar_data[event_name] = {}
            for day, time_str in day_times.items():
                # Parse time in server timezone
                hour, minute = map(int, time_str.split(':'))
                # Create a datetime object (use arbitrary date)
                dt_server = server_tz.localize(datetime(2024, 1, 1, hour, minute))
                # Convert to user timezone
                dt_user = dt_server.astimezone(user_tz)
                # Format back to HH:MM
                converted_time = dt_user.strftime("%H:%M")
                # Handle day changes due to timezone conversion
                day_offset = (dt_user.day - dt_server.day) % 7
                days_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                day_idx = days_list.index(day) if day in days_list else 0
                new_day_idx = (day_idx + day_offset) % 7
                new_day = days_list[new_day_idx]

                converted_calendar_data[event_name][new_day] = converted_time

        # Also convert blocked times (Guild War) to user timezone
        converted_blocked_times = []
        for blocked in self.cog.blocked_times:
            # Parse start and end times
            start_hour, start_minute = map(int, blocked['start'].split(':'))
            end_hour, end_minute = map(int, blocked['end'].split(':'))

            # Convert start time
            dt_start_server = server_tz.localize(datetime(2024, 1, 1, start_hour, start_minute))
            dt_start_user = dt_start_server.astimezone(user_tz)

            # Convert end time
            dt_end_server = server_tz.localize(datetime(2024, 1, 1, end_hour, end_minute))
            dt_end_user = dt_end_server.astimezone(user_tz)

            # Handle day changes
            day_offset_start = (dt_start_user.day - dt_start_server.day) % 7
            day_offset_end = (dt_end_user.day - dt_end_server.day) % 7
            days_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

            # Convert start day
            orig_day = blocked['day']
            if orig_day in days_list:
                day_idx = days_list.index(orig_day)
                new_day_idx = (day_idx + day_offset_start) % 7
                new_day = days_list[new_day_idx]
            else:
                new_day = orig_day

            converted_blocked_times.append({
                'day': new_day,
                'start': dt_start_user.strftime("%H:%M"),
                'end': dt_end_user.strftime("%H:%M")
            })

        # Generate calendar image with the user's timezone
        image_buffer = user_tz_renderer.render_calendar(
            converted_calendar_data,
            self.cog.events,
            converted_blocked_times,
            len(selections)
        )
        
        # Create embed
        embed = discord.Embed(
            title=f"📅 Calendar ({timezone_str})",
            description=f"This calendar shows times in **{timezone_str}** timezone.",
            color=self.cog._get_embed_color(interaction.guild)
        )
        
        # Create file attachment
        calendar_file = discord.File(image_buffer, filename=f"calendar_{timezone_str.replace('/', '_')}.png")
        embed.set_image(url=f"attachment://calendar_{timezone_str.replace('/', '_')}.png")
        
        # Send as ephemeral message with dismissible view
        await interaction.response.send_message(
            embed=embed,
            file=calendar_file,
            view=DismissibleView(),
            ephemeral=True
        )


class CalendarTimezoneView(discord.ui.View):
    """View with timezone button for calendar embeds"""

    def __init__(self, cog, guild_id: int, poll_id: str, is_weekly: bool = False, poll_url: Optional[str] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.is_weekly = is_weekly

        # Add link button if URL provided
        if poll_url:
            link_button = discord.ui.Button(
                label="Vote Here",
                style=discord.ButtonStyle.link,
                url=poll_url
            )
            self.add_item(link_button)

        # Add timezone button
        timezone_button = discord.ui.Button(
            label="View in My Timezone",
            style=discord.ButtonStyle.secondary,
            emoji="🌍",
            custom_id=f"calendar_timezone:{poll_id}"
        )
        timezone_button.callback = self._show_timezone_modal
        self.add_item(timezone_button)

    async def _show_timezone_modal(self, interaction: discord.Interaction):
        """Show the timezone input modal"""
        modal = TimezoneModal(self.cog, self.guild_id, self.poll_id, is_weekly=self.is_weekly)
        await interaction.response.send_modal(modal)
