"""Calendar image rendering using PIL with emoji support via pilmoji"""

from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Tuple
import io

try:
    from pilmoji import Pilmoji
    PILMOJI_AVAILABLE = True
except ImportError:
    PILMOJI_AVAILABLE = False


class CalendarRenderer:
    """Renders event calendar as an image"""

    # Color scheme
    BG_COLOR = (45, 52, 64)  # Dark background
    GRID_COLOR = (100, 110, 130)  # Grid lines
    HEADER_BG = (60, 70, 90)  # Header background
    HEADER_TEXT = (255, 255, 255)  # White header text
    TIME_TEXT = (200, 210, 230)  # Light gray time text
    CELL_BG = (55, 62, 75)  # Default cell background
    BLOCKED_BG = (90, 70, 50)  # Guild War cell background (Orangeish)
    LEGEND_BG = (50, 58, 70)  # Legend background

    # Event-specific cell background colors
    EVENT_BG_COLORS = {
        "Hero's Realm": (60, 80, 120),      # Blueish
        "Sword Trial": (70, 75, 85),        # Greyish
        "Party": (55, 80, 60),              # Greenish
        "Breaking Army": (90, 85, 55),      # Yellowish
        "Showdown": (90, 55, 55),           # Redish
        "Guild War": (90, 70, 50)           # Orangeish
    }

    # Event label mapping (text labels instead of emojis since PIL doesn't support emojis well)
    EVENT_LABELS = {
        "Hero's Realm": "HR",
        "Sword Trial": "ST",
        "Party": "P",
        "Breaking Army": "BA",
        "Showdown": "SD",
        "Guild War": "GW"
    }

    # Event colors for text
    EVENT_COLORS = {
        "Hero's Realm": (147, 197, 253),  # Light blue
        "Sword Trial": (196, 181, 253),    # Purple
        "Party": (253, 224, 71),           # Yellow
        "Breaking Army": (252, 165, 165),  # Light red
        "Showdown": (253, 186, 116),       # Orange
        "Guild War": (156, 163, 175)      # Gray
    }

    # Layout constants (increased for higher resolution)
    CELL_WIDTH = 200
    CELL_HEIGHT = 80
    TIME_COL_WIDTH = 140
    HEADER_HEIGHT = 80
    FOOTER_HEIGHT = 60
    PADDING = 20

    # Event name abbreviations for display
    EVENT_ABBREV = {
        "Hero's Realm": "Hero's Realm",
        "Sword Trial": "Sword Trial",
        "Party": "Party",
        "Breaking Army": "Breaking Army",
        "Showdown": "Showdown",
        "Guild War": "Guild War"
    }

    def __init__(self, timezone: str = "UTC"):
        """Initialize calendar renderer

        Args:
            timezone: Timezone string (not used in image anymore, kept for compatibility)
        """
        self.timezone = timezone

        # Try to load a nice font with larger sizes for better clarity
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            self.font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
        except:
            self.font = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_bold = ImageFont.load_default()
            self.font_large = ImageFont.load_default()

    def render_calendar(
        self,
        winning_times: Dict[str, Dict[str, str]],
        events: Dict,
        blocked_times: List[Dict] = None,
        total_voters: int = 0
    ) -> io.BytesIO:
        """Render calendar as PNG image

        Args:
            winning_times: Dict mapping event names to {day: time} for winning times
            events: Event configuration dict
            blocked_times: List of blocked time periods

        Returns:
            BytesIO object containing PNG image
        """
        if blocked_times is None:
            blocked_times = [
                {"day": "Saturday", "start": "20:30", "end": "22:00"},
                {"day": "Sunday", "start": "20:30", "end": "22:00"}
            ]

        # Build schedule data structure
        schedule = self._build_schedule(winning_times, events, blocked_times)

        # Calculate image dimensions
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Sort time slots with custom logic: times after midnight (00:xx, 01:xx) go after 23:xx
        def sort_time_key(time_str: str) -> int:
            """Convert time string to sortable integer (handle wraparound)"""
            hour, minute = map(int, time_str.split(':'))
            # Times 00:00-02:59 are treated as next day (add 24 hours)
            if hour < 3:
                hour += 24
            return hour * 60 + minute

        time_slots = sorted(schedule.keys(), key=sort_time_key)

        # Crop empty hours from extremities - find first and last slots with events
        time_slots = self._crop_empty_hours(time_slots, schedule, days)

        width = self.TIME_COL_WIDTH + (len(days) * self.CELL_WIDTH) + (2 * self.PADDING)
        height = self.HEADER_HEIGHT + (len(time_slots) * self.CELL_HEIGHT) + self.FOOTER_HEIGHT + (2 * self.PADDING)

        # Create image
        img = Image.new('RGB', (width, height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Initialize emoji positions list
        self._emoji_positions = []

        # Draw column headers (days)
        self._draw_day_headers(draw, days)

        # Draw time labels and calendar grid
        self._draw_calendar_grid(draw, days, time_slots, schedule, blocked_times, events)

        # Draw footer with timestamp and voter count
        self._draw_footer(draw, width, height, total_voters)

        # Render all emojis using pilmoji if available
        if PILMOJI_AVAILABLE:
            with Pilmoji(img) as pilmoji:
                # Draw calendar cell emojis
                for text_x, text_y, display_text, font in self._emoji_positions:
                    pilmoji.text((text_x, text_y), display_text, font=font, fill=self.HEADER_TEXT)
        else:
            # Fallback to text labels if pilmoji not available
            for text_x, text_y, display_text, font in self._emoji_positions:
                # Use text labels instead of emojis
                label_text = display_text
                # Try to extract label from text (fallback)
                for event_name, emoji in [("Hero's Realm", "🛡️"), ("Sword Trial", "⚔️"), ("Party", "🎉"), ("Breaking Army", "⚡"), ("Showdown", "🏆"), ("Guild War", "🏰")]:
                    if emoji in display_text:
                        label = self.EVENT_LABELS.get(event_name, "?")
                        label_text = display_text.replace(emoji, label)
                        break
                draw.text((text_x, text_y), label_text, font=font, fill=self.HEADER_TEXT)

        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        return buffer

    def _build_schedule(self, winning_times: Dict, events: Dict, blocked_times: List[Dict] = None) -> Dict[str, Dict[str, List]]:
        """Build schedule data structure from winning times

        Args:
            winning_times: Dict mapping event names to {day: time} for winning times
            events: Event configuration dict
            blocked_times: List of blocked time periods for Guild War

        Returns:
            Dict mapping time -> day -> [(priority, event_name, slot_num, start_time, duration)]
        """
        schedule = {}
        day_map = {
            "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed",
            "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"
        }

        for event_name, day_times in winning_times.items():
            event_info = events[event_name]
            priority = event_info.get("priority", 0)

            # Track slot numbers for multi-slot events
            day_slot_map = {}
            if event_info.get("slots", 1) > 1 and event_info.get("type") == "fixed_days":
                # For multi-slot fixed-day events, map days to slot numbers
                for idx, day in enumerate(event_info.get("days", [])):
                    day_slot_map[day] = idx + 1

            for day, time_str in day_times.items():
                # Handle special day types
                days_to_process = []
                if day == "Daily":
                    # Daily events appear on all days
                    days_to_process = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                elif day == "Fixed":
                    # Fixed-day events with single slot - expand to all configured days
                    fixed_days = event_info.get("days", [])
                    days_to_process = [day_map.get(d, d[:3]) for d in fixed_days]
                else:
                    # Regular day or multi-slot fixed-day event
                    short_day = day_map.get(day, day[:3])
                    days_to_process = [short_day]

                # Determine slot number for this event
                slot_num = day_slot_map.get(day, 0)  # 0 means single slot or not applicable

                # Calculate how many time slots this event spans (based on duration)
                duration = event_info.get("duration", 30)
                time_slots_spanned = max(1, duration // 30)

                # Generate all time slots for this event (e.g., 19:00 and 19:30 for 60-min event)
                from datetime import datetime, timedelta
                start_time = datetime.strptime(time_str, "%H:%M")
                time_slots_for_event = []
                for i in range(time_slots_spanned):
                    slot_time = start_time + timedelta(minutes=i * 30)
                    slot_time_str = slot_time.strftime("%H:%M")
                    time_slots_for_event.append(slot_time_str)

                # Add event to all relevant time slots and days
                for slot_time_str in time_slots_for_event:
                    if slot_time_str not in schedule:
                        schedule[slot_time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

                    for short_day in days_to_process:
                        if short_day in schedule[slot_time_str]:
                            schedule[slot_time_str][short_day].append((priority, event_name, slot_num, time_str, duration))

        # Generate all time slots from 17:00 to 02:00 (30 min intervals)
        all_times = []
        hour = 17
        minute = 0
        while hour < 26:  # 26 represents 02:00 next day
            display_hour = hour if hour < 24 else hour - 24
            all_times.append(f"{display_hour:02d}:{minute:02d}")
            minute += 30
            if minute >= 60:
                minute = 0
                hour += 1

        # Ensure all time slots exist
        for time_str in all_times:
            if time_str not in schedule:
                schedule[time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

        # Add Guild War events from blocked times
        if blocked_times:
            from datetime import datetime, timedelta
            for blocked in blocked_times:
                day_full = blocked["day"]
                short_day = day_map.get(day_full, day_full[:3])
                start_time_str = blocked["start"]
                end_time_str = blocked["end"]

                # Parse times
                start_dt = datetime.strptime(start_time_str, "%H:%M")
                end_dt = datetime.strptime(end_time_str, "%H:%M")

                # Calculate duration in minutes
                duration = int((end_dt - start_dt).total_seconds() / 60)

                # Generate all 30-min slots for Guild War
                current_dt = start_dt
                while current_dt < end_dt:
                    slot_time_str = current_dt.strftime("%H:%M")
                    if slot_time_str in schedule and short_day in schedule[slot_time_str]:
                        # Add Guild War event (priority 0, will be handled specially)
                        schedule[slot_time_str][short_day].append((0, "Guild War", 0, start_time_str, duration))
                    current_dt += timedelta(minutes=30)

        # Note: Events will be sorted dynamically at draw time based on position rules

        return schedule

    def _sort_events_for_display(self, events_in_cell: List, current_time: str) -> List:
        """Sort events for display based on dynamic ordering rules

        Rules:
        - Multi-slot events (Breaking Army, Showdown, Guild War) that START at current time: go second (Party first)
        - Multi-slot events that END at current time: go first (Party second)
        - Single slot events (Hero's Realm, Sword Trial): go second (Party first)

        Args:
            events_in_cell: List of (priority, event_name, slot_num, start_time, duration)
            current_time: Current time slot being displayed

        Returns:
            Sorted list of events
        """
        from datetime import datetime, timedelta

        def get_sort_key(event_tuple):
            priority, event_name, slot_num, start_time, duration = event_tuple

            # Party always uses its base priority with position adjustment
            if event_name == "Party":
                return (priority, 0)  # Party's position is determined relative to others

            # Parse times
            start_dt = datetime.strptime(start_time, "%H:%M")
            current_dt = datetime.strptime(current_time, "%H:%M")

            # Calculate event span
            time_slots_spanned = max(1, duration // 30)

            # Determine if this is the start or end of the event
            is_start = (current_time == start_time)

            # Calculate end time (last slot)
            end_dt = start_dt + timedelta(minutes=(time_slots_spanned - 1) * 30)
            end_time = end_dt.strftime("%H:%M")
            is_end = (current_time == end_time)

            # Multi-slot events
            if time_slots_spanned > 1:
                if is_start:
                    # Event starts here: should go second (lower effective priority)
                    return (priority - 10, 1)
                elif is_end:
                    # Event ends here: should go first (higher effective priority)
                    return (priority + 10, 0)
                else:
                    # Middle of event: use base priority
                    return (priority, 0)
            else:
                # Single slot events (Hero's Realm, Sword Trial): go second
                return (priority - 10, 1)

        # Separate Party and other events
        party_events = [e for e in events_in_cell if e[1] == "Party"]
        other_events = [e for e in events_in_cell if e[1] != "Party"]

        if not other_events:
            return party_events
        if not party_events:
            return sorted(other_events, key=get_sort_key, reverse=True)

        # Sort other events to determine which should go first
        other_sorted = sorted(other_events, key=get_sort_key, reverse=True)

        # Check the top non-Party event
        top_event = other_sorted[0]
        top_key = get_sort_key(top_event)

        # If the top event's position indicator is 1 (should go second), Party goes first
        if top_key[1] == 1:
            return party_events + other_sorted
        else:
            # Otherwise, other event goes first
            return other_sorted + party_events

    def _draw_timezone_header(self, draw: ImageDraw, width: int):
        """Draw timezone at top of calendar"""
        text = f"Schedule (Timezone: {self.timezone})"
        # Get text size for centering
        bbox = draw.textbbox((0, 0), text, font=self.font_large)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        y = self.PADDING
        draw.text((x, y), text, fill=self.HEADER_TEXT, font=self.font_large)

    def _draw_day_headers(self, draw: ImageDraw, days: List[str]):
        """Draw day column headers"""
        y = self.PADDING

        for i, day in enumerate(days):
            x = self.TIME_COL_WIDTH + (i * self.CELL_WIDTH) + self.PADDING

            # Draw header background
            draw.rectangle(
                [x, y, x + self.CELL_WIDTH, y + self.HEADER_HEIGHT],
                fill=self.HEADER_BG,
                outline=self.GRID_COLOR
            )

            # Draw day text (centered)
            bbox = draw.textbbox((0, 0), day, font=self.font_bold)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x + (self.CELL_WIDTH - text_width) // 2
            text_y = y + (self.HEADER_HEIGHT - text_height) // 2
            draw.text((text_x, text_y), day, fill=self.HEADER_TEXT, font=self.font_bold)

    def _draw_calendar_grid(
        self,
        draw: ImageDraw,
        days: List[str],
        time_slots: List[str],
        schedule: Dict,
        blocked_times: List[Dict],
        events: Dict
    ):
        """Draw the calendar grid with times and events"""
        start_y = self.HEADER_HEIGHT + self.PADDING

        day_full_names = {
            "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
            "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"
        }

        for row, time_str in enumerate(time_slots):
            y = start_y + (row * self.CELL_HEIGHT)

            # Draw time label
            time_x = self.PADDING + 5
            time_y = y + (self.CELL_HEIGHT - 14) // 2
            draw.text((time_x, time_y), time_str, fill=self.TIME_TEXT, font=self.font)

            # Draw cells for each day
            for col, day in enumerate(days):
                x = self.TIME_COL_WIDTH + (col * self.CELL_WIDTH) + self.PADDING

                # Get events in this cell
                events_in_cell = []
                if time_str in schedule and day in schedule[time_str]:
                    events_in_cell = schedule[time_str][day]

                # Determine cell background color based on events
                if events_in_cell:
                    # Get event names (handle 5-element tuple)
                    event_names = [event_name for _, event_name, _, _, _ in events_in_cell]

                    # For combo cells with Party, use the non-Party event's color
                    if len(event_names) > 1 and "Party" in event_names:
                        # Find the non-Party event
                        non_party_event = next((name for name in event_names if name != "Party"), None)
                        cell_bg = self.EVENT_BG_COLORS.get(non_party_event, self.CELL_BG)
                    else:
                        # Use the first event's color
                        cell_bg = self.EVENT_BG_COLORS.get(event_names[0], self.CELL_BG)
                else:
                    cell_bg = self.CELL_BG

                # Draw cell background
                draw.rectangle(
                    [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT],
                    fill=cell_bg,
                    outline=self.GRID_COLOR
                )

                # Draw events in this cell (support up to 2 events)
                if events_in_cell:
                        # Sort events based on dynamic ordering rules
                        sorted_events = self._sort_events_for_display(events_in_cell, time_str)

                        # Draw up to 2 events per cell
                        num_events_to_show = min(2, len(sorted_events))

                        for event_idx in range(num_events_to_show):
                            priority, event_name, slot_num, start_time, duration = sorted_events[event_idx]

                            # Get emoji (handle Guild War specially since it's not in events dict)
                            if event_name == "Guild War":
                                emoji = "🏰"
                            else:
                                emoji = events.get(event_name, {}).get("emoji", "•")

                            # Create display text with emoji and name
                            display_text = f"{emoji} {event_name}"

                            # Calculate text width for centering
                            bbox = draw.textbbox((0, 0), display_text, font=self.font_small)
                            text_width = bbox[2] - bbox[0]
                            text_height = bbox[3] - bbox[1]

                            # Center horizontally
                            text_x = x + (self.CELL_WIDTH - text_width) // 2

                            # Position events vertically based on index
                            if num_events_to_show == 1:
                                # Single event: center vertically
                                text_y = y + (self.CELL_HEIGHT - text_height) // 2
                            else:
                                # Multiple events: stack vertically with line breaks, center each
                                if event_idx == 0:
                                    text_y = y + 10
                                else:
                                    text_y = y + 45  # Second line (with line break)

                            if not hasattr(self, '_emoji_positions'):
                                self._emoji_positions = []
                            self._emoji_positions.append((text_x, text_y, display_text, self.font_small))

    def _draw_legend(self, draw: ImageDraw, width: int, start_y: int, events: Dict):
        """Draw legend showing event labels and names"""
        # Draw legend background
        legend_y = start_y + 10
        draw.rectangle(
            [self.PADDING, legend_y, width - self.PADDING, legend_y + self.LEGEND_HEIGHT - 20],
            fill=self.LEGEND_BG,
            outline=self.GRID_COLOR
        )

        # Draw "Legend:" title
        title_x = self.PADDING + 10
        title_y = legend_y + 8
        draw.text((title_x, title_y), "Legend:", fill=self.HEADER_TEXT, font=self.font_bold)

        # Event list with emojis
        event_list = [
            ("Hero's Realm", "🛡️"),
            ("Sword Trial", "⚔️"),
            ("Party", "🎉"),
            ("Breaking Army", "⚡"),
            ("Showdown", "🏆"),
            ("Guild War", "🏰")
        ]

        # Draw event names in two columns
        col1_x = self.PADDING + 20
        col2_x = width // 2 + 10
        current_x = col1_x
        current_y = legend_y + 32

        for idx, (event_name, emoji) in enumerate(event_list):
            # Get label and color
            label = self.EVENT_LABELS.get(event_name, "?")
            color = self.EVENT_COLORS.get(event_name, self.HEADER_TEXT)

            # Determine number of slots for multi-slot events
            event_info = events.get(event_name, {})
            num_slots = event_info.get("slots", 1)

            # Format text (emoji will be rendered separately with pilmoji)
            if num_slots > 1 and event_info.get("type") == "fixed_days":
                # Show slot range for multi-slot events
                emoji_part = emoji
                text_part = f" {label}1-{label}{num_slots}: {event_name}"
            else:
                emoji_part = emoji
                text_part = f" {label}: {event_name}"

            # Store emoji position for pilmoji rendering
            if not hasattr(self, '_legend_emoji_positions'):
                self._legend_emoji_positions = []
            self._legend_emoji_positions.append((current_x, current_y, emoji_part, self.font_small))

            # Draw the text part (after emoji space)
            text_x = current_x + 25  # Space for emoji
            draw.text((text_x, current_y), text_part, fill=self.HEADER_TEXT, font=self.font_small)

            # Move to next position (3 items per column)
            if idx == 2:
                current_x = col2_x
                current_y = legend_y + 32
            else:
                current_y += 18

    def _draw_footer(self, draw: ImageDraw, width: int, height: int, total_voters: int):
        """Draw footer with timestamp and voter count"""
        from datetime import datetime

        # Calculate footer position
        footer_y = height - self.FOOTER_HEIGHT

        # Get current timestamp
        now = datetime.utcnow()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Create footer text
        footer_text = f"Timezone: {self.timezone} | Total voters: {total_voters} | Last updated: {timestamp}"

        # Draw footer text centered
        bbox = draw.textbbox((0, 0), footer_text, font=self.font_small)
        text_width = bbox[2] - bbox[0]
        text_x = (width - text_width) // 2
        text_y = footer_y + (self.FOOTER_HEIGHT - 14) // 2

        draw.text((text_x, text_y), footer_text, fill=self.TIME_TEXT, font=self.font_small)

    def _is_time_blocked(self, day: str, time_str: str, blocked_times: List[Dict]) -> bool:
        """Check if a time slot is blocked"""
        from datetime import datetime, timedelta

        for blocked in blocked_times:
            if blocked["day"] != day:
                continue

            # Parse times
            slot_time = datetime.strptime(time_str, "%H:%M")
            blocked_start = datetime.strptime(blocked["start"], "%H:%M")
            blocked_end = datetime.strptime(blocked["end"], "%H:%M")

            # Check if slot falls within blocked period (30 min duration)
            slot_end = slot_time + timedelta(minutes=30)

            # Check overlap
            if slot_time.time() < blocked_end.time() and slot_end.time() > blocked_start.time():
                return True

        return False

    def _crop_empty_hours(self, time_slots: List[str], schedule: Dict, days: List[str]) -> List[str]:
        """Crop empty hours from the extremities of the calendar

        Args:
            time_slots: Sorted list of all time slots
            schedule: Schedule data structure mapping time -> day -> events
            days: List of day abbreviations

        Returns:
            Filtered list of time slots with empty extremities removed
        """
        if not time_slots:
            return time_slots

        # Find first time slot with any events
        first_event_idx = None
        for idx, time_str in enumerate(time_slots):
            has_events = False
            for day in days:
                if time_str in schedule and day in schedule[time_str]:
                    if schedule[time_str][day]:  # Check if events list is not empty
                        has_events = True
                        break
            if has_events:
                first_event_idx = idx
                break

        # Find last time slot with any events
        last_event_idx = None
        for idx in range(len(time_slots) - 1, -1, -1):
            time_str = time_slots[idx]
            has_events = False
            for day in days:
                if time_str in schedule and day in schedule[time_str]:
                    if schedule[time_str][day]:  # Check if events list is not empty
                        has_events = True
                        break
            if has_events:
                last_event_idx = idx
                break

        # If no events found, return original list
        if first_event_idx is None or last_event_idx is None:
            return time_slots

        # Return cropped list
        return time_slots[first_event_idx:last_event_idx + 1]
