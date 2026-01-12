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

    # Color scheme - Catppuccin Frappé
    BG_COLOR = (48, 52, 70)  # Base - #303446
    GRID_COLOR = (35, 38, 52)  # Custom border - #232634
    HEADER_BG = (65, 69, 89)  # Surface0 - #414559
    HEADER_TEXT = (198, 208, 245)  # Text - #c6d0f5
    TIME_TEXT = (181, 191, 226)  # Subtext1 - #b5bfe2
    CELL_BG = (41, 44, 60)  # Mantle - #292c3c
    BLOCKED_BG = (81, 87, 109)  # Surface1 - #51576d
    LEGEND_BG = (65, 69, 89)  # Surface0 - #414559

    # Event-specific cell background colors
    EVENT_BG_COLORS = {
        "Hero's Realm": (92, 107, 192),     # #5C6BC0 - Indigo
        "Sword Trial": (255, 202, 40),      # #FFCA28 - Yellow
        "Party": (233, 30, 99),             # #e91e63 - Pink
        "Breaking Army": (52, 152, 219),    # #3498db - Blue
        "Showdown": (230, 126, 34),         # #e67e22 - Orange
        "Guild War": (216, 27, 96)          # #D81B60 - Pink-red
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

    # Layout constants (significantly increased to accommodate large fonts)
    CELL_WIDTH = 400
    CELL_HEIGHT = 160
    TIME_COL_WIDTH = 280
    HEADER_HEIGHT = 160
    FOOTER_HEIGHT = 120
    LEGEND_HEIGHT = 200
    PADDING = 30

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

        # Try to load fonts with multiple fallback paths (Windows & Linux)
        font_paths = [
            # Windows paths
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\DejaVuSans.ttf",
            # Linux paths
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu-sans/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ]

        font_bold_paths = [
            # Windows paths
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf",
            # Linux paths
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu-sans/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        ]

        # Try loading fonts without layout_engine parameter (may cause compatibility issues)
        loaded = False
        for font_path in font_paths:
            try:
                self.font = ImageFont.truetype(font_path, 120)
                self.font_small = ImageFont.truetype(font_path, 110)
                print(f"Successfully loaded regular font from: {font_path}")
                loaded = True
                break
            except Exception as e:
                print(f"Failed to load font from {font_path}: {e}")
                continue

        if not loaded:
            print("ERROR: Could not load regular font from any path, using default")
            self.font = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

        loaded_bold = False
        for font_bold_path in font_bold_paths:
            try:
                self.font_bold = ImageFont.truetype(font_bold_path, 140)
                self.font_large = ImageFont.truetype(font_bold_path, 150)
                print(f"Successfully loaded bold font from: {font_bold_path}")
                loaded_bold = True
                break
            except Exception as e:
                print(f"Failed to load bold font from {font_bold_path}: {e}")
                continue

        if not loaded_bold:
            print("ERROR: Could not load bold font from any path, using default")
            self.font_bold = ImageFont.load_default()
            self.font_large = ImageFont.load_default()

    def _fade_color(self, color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Fade a color by blending with background for better text readability

        Args:
            color: RGB color tuple

        Returns:
            Faded RGB color tuple (formula: original * 0.55 + background * 0.45)
        """
        r, g, b = color
        bg_r, bg_g, bg_b = self.BG_COLOR

        # Blend color with background (55% original, 45% background)
        faded_r = int(r * 0.55 + bg_r * 0.45)
        faded_g = int(g * 0.55 + bg_g * 0.45)
        faded_b = int(b * 0.55 + bg_b * 0.45)

        return (faded_r, faded_g, faded_b)

    def _draw_dotted_border(self, draw: ImageDraw, x1: int, y1: int, x2: int, y2: int,
                           color: Tuple[int, int, int], dash_length: int = 5,
                           skip_right: bool = False, skip_bottom: bool = False,
                           skip_top: bool = False, skip_left: bool = False):
        """Draw a solid, thick border around a rectangle

        Args:
            draw: ImageDraw object
            x1, y1: Top-left corner
            x2, y2: Bottom-right corner
            color: RGB color tuple
            dash_length: Unused (kept for compatibility)
            skip_right: Skip drawing the right border
            skip_bottom: Skip drawing the bottom border
            skip_top: Skip drawing the top border
            skip_left: Skip drawing the left border
        """
        # Top border (if not skipped)
        if not skip_top:
            draw.line([(x1, y1), (x2 + 1, y1)], fill=color, width=4)

        # Left border (if not skipped)
        if not skip_left:
            draw.line([(x1, y1), (x1, y2 + 1)], fill=color, width=4)

        # Right border (if not skipped)
        if not skip_right:
            draw.line([(x2, y1), (x2, y2 + 1)], fill=color, width=4)

        # Bottom border (if not skipped)
        if not skip_bottom:
            draw.line([(x1, y2), (x2 + 1, y2)], fill=color, width=4)

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
        draw.fontmode = "L"  # Use antialiased text (8-bit grayscale) instead of 1-bit monochrome

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
            # Use emoji_scale_factor to make emojis match the large font sizes
            with Pilmoji(img, emoji_scale_factor=1.2) as pilmoji:
                # Draw calendar cell emojis
                for text_x, text_y, display_text, font in self._emoji_positions:
                    pilmoji.text((text_x, text_y), display_text, font=font, fill=self.HEADER_TEXT, emoji_position_offset=(0, 0))
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
            # Extract base event name and slot number for multi-slot weekly events
            # (e.g., "Breaking Army 1" -> "Breaking Army", slot_num = 1)
            base_event_name = event_name
            slot_num = 0
            if event_name.endswith(" 1") or event_name.endswith(" 2"):
                parts = event_name.rsplit(" ", 1)
                if parts[1].isdigit():
                    base_event_name = parts[0]
                    slot_num = int(parts[1])

            # Get event info using base name
            event_info = events.get(base_event_name, events.get(event_name))
            if not event_info:
                continue
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
                            # Store base event name (without slot number) for rendering
                            schedule[slot_time_str][short_day].append((priority, base_event_name, slot_num, time_str, duration))

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
                outline=None
            )

            # Draw border (always draw left, only last column draws right to avoid double borders)
            skip_right = (i < len(days) - 1)
            skip_left = False  # Always draw left border
            self._draw_dotted_border(
                draw, x, y, x + self.CELL_WIDTH - 1, y + self.HEADER_HEIGHT - 1,
                self.GRID_COLOR, skip_right=skip_right, skip_bottom=False, skip_top=False, skip_left=skip_left
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

        # Build a grid of cell contents for border optimization
        cell_contents = {}  # (row, col) -> sorted event names tuple
        for row, time_str in enumerate(time_slots):
            for col, day in enumerate(days):
                events_in_cell = []
                if time_str in schedule and day in schedule[time_str]:
                    events_in_cell = schedule[time_str][day]

                if events_in_cell:
                    sorted_events = self._sort_events_for_display(events_in_cell, time_str)
                    event_names = tuple(event_name for _, event_name, _, _, _ in sorted_events)
                    cell_contents[(row, col)] = event_names
                else:
                    cell_contents[(row, col)] = ()

        for row, time_str in enumerate(time_slots):
            y = start_y + (row * self.CELL_HEIGHT)

            # Draw time label (right-aligned)
            bbox = draw.textbbox((0, 0), time_str, font=self.font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            time_x = self.TIME_COL_WIDTH + self.PADDING - text_width - 10
            time_y = y + (self.CELL_HEIGHT - text_height) // 2
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
                    # Sort events first to determine display order
                    sorted_events = self._sort_events_for_display(events_in_cell, time_str)
                    event_names = [event_name for _, event_name, _, _, _ in sorted_events]

                    # For cells with 2 events, draw dual-color split background
                    if len(event_names) >= 2:
                        # Top half: first event's color (faded)
                        top_color = self.EVENT_BG_COLORS.get(event_names[0], self.CELL_BG)
                        top_color_faded = self._fade_color(top_color)
                        draw.rectangle(
                            [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT // 2],
                            fill=top_color_faded,
                            outline=None
                        )

                        # Bottom half: second event's color (faded)
                        bottom_color = self.EVENT_BG_COLORS.get(event_names[1], self.CELL_BG)
                        bottom_color_faded = self._fade_color(bottom_color)
                        draw.rectangle(
                            [x, y + self.CELL_HEIGHT // 2, x + self.CELL_WIDTH, y + self.CELL_HEIGHT],
                            fill=bottom_color_faded,
                            outline=None
                        )

                        # Draw solid horizontal line between the two events
                        mid_y = y + self.CELL_HEIGHT // 2
                        draw.line([(x, mid_y), (x + self.CELL_WIDTH, mid_y)], fill=self.GRID_COLOR, width=4)
                    else:
                        # Single event: use single color (faded)
                        cell_bg = self.EVENT_BG_COLORS.get(event_names[0], self.CELL_BG)
                        cell_bg_faded = self._fade_color(cell_bg)
                        draw.rectangle(
                            [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT],
                            fill=cell_bg_faded,
                            outline=None
                        )
                else:
                    # Empty cell
                    draw.rectangle(
                        [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT],
                        fill=self.CELL_BG,
                        outline=None
                    )

                # Determine if we should skip borders
                current_content = cell_contents.get((row, col), ())
                next_row_content = cell_contents.get((row + 1, col), None)
                prev_row_content = cell_contents.get((row - 1, col), None)

                # Horizontal borders: Only first column draws left, all columns draw right (avoids double borders)
                skip_left = (col > 0)  # Skip left for all except first column
                skip_right = False  # Always draw right border

                # Multi-slot events that span multiple time slots
                multi_slot_events = ["Breaking Army", "Showdown", "Guild War"]

                # Vertical borders: Only first row draws top, all rows draw bottom (avoids double borders)
                # Exception: skip borders when same multi-slot event continues above/below

                # Skip bottom border if next row shares any multi-slot event
                has_common_multislot_below = False
                if next_row_content and current_content:
                    has_common_multislot_below = any(
                        event in next_row_content
                        for event in current_content
                        if event in multi_slot_events
                    )
                skip_bottom = has_common_multislot_below

                # Skip top border if previous row shares any multi-slot event OR if not first row
                has_common_multislot_above = False
                if prev_row_content and current_content:
                    has_common_multislot_above = any(
                        event in prev_row_content
                        for event in current_content
                        if event in multi_slot_events
                    )
                skip_top = (row > 0) or has_common_multislot_above  # Skip top for all except first row

                # Draw border
                self._draw_dotted_border(
                    draw, x, y, x + self.CELL_WIDTH - 1, y + self.CELL_HEIGHT - 1,
                    self.GRID_COLOR, skip_right=skip_right, skip_bottom=skip_bottom, skip_top=skip_top, skip_left=skip_left
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
                            bbox = draw.textbbox((0, 0), display_text, font=self.font_bold)
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
                                    text_y = y + 20  # Scaled from 10 to 20 for larger cells
                                else:
                                    text_y = y + 90  # Scaled from 45 to 90 for larger cells (second line)

                            if not hasattr(self, '_emoji_positions'):
                                self._emoji_positions = []
                            self._emoji_positions.append((text_x, text_y, display_text, self.font_bold))

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
