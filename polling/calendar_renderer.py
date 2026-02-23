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
        "Hero's Realm (Catch-up)": (92, 107, 192),  # Inherit from Hero's Realm
        "Hero's Realm (Reset)": (92, 107, 192),     # Inherit from Hero's Realm
        "Sword Trial": (255, 202, 40),      # #FFCA28 - Yellow
        "Sword Trial (Echo)": (255, 202, 40),       # Inherit from Sword Trial
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

    # Layout constants (compact sizes for smaller fonts)
    CELL_WIDTH = 200
    CELL_HEIGHT = 80
    TIME_COL_WIDTH = 140
    HEADER_HEIGHT = 80
    FOOTER_HEIGHT = 60
    LEGEND_HEIGHT = 100
    PADDING = 15

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
                self.font = ImageFont.truetype(font_path, 13)
                self.font_small = ImageFont.truetype(font_path, 11)
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
                self.font_bold = ImageFont.truetype(font_bold_path, 17)
                self.font_large = ImageFont.truetype(font_bold_path, 19)
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

    def _draw_borders(self, draw: ImageDraw, x1: int, y1: int, x2: int, y2: int,
                     color: Tuple[int, int, int],
                     top_width: int = 0, left_width: int = 0,
                     right_width: int = 0, bottom_width: int = 0):
        """Draw borders around a rectangle with individual widths per side

        Args:
            draw: ImageDraw object
            x1, y1: Top-left corner
            x2, y2: Bottom-right corner
            color: RGB color tuple
            top_width: Top border width (0 to skip)
            left_width: Left border width (0 to skip)
            right_width: Right border width (0 to skip)
            bottom_width: Bottom border width (0 to skip)
        """
        # Top border
        if top_width > 0:
            draw.line([(x1, y1), (x2 + 1, y1)], fill=color, width=top_width)

        # Left border
        if left_width > 0:
            draw.line([(x1, y1), (x1, y2 + 1)], fill=color, width=left_width)

        # Right border
        if right_width > 0:
            draw.line([(x2, y1), (x2, y2 + 1)], fill=color, width=right_width)

        # Bottom border
        if bottom_width > 0:
            draw.line([(x1, y2), (x2 + 1, y2)], fill=color, width=bottom_width)

    def _draw_dotted_border(self, draw: ImageDraw, x1: int, y1: int, x2: int, y2: int,
                           color: Tuple[int, int, int], dash_length: int = 5,
                           skip_right: bool = False, skip_bottom: bool = False,
                           skip_top: bool = False, skip_left: bool = False, width: int = 2):
        """Draw a solid border around a rectangle (legacy function for compatibility)

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
            width: Border width in pixels (default 2)
        """
        # Top border (if not skipped)
        if not skip_top:
            draw.line([(x1, y1), (x2 + 1, y1)], fill=color, width=width)

        # Left border (if not skipped)
        if not skip_left:
            draw.line([(x1, y1), (x1, y2 + 1)], fill=color, width=width)

        # Right border (if not skipped)
        if not skip_right:
            draw.line([(x2, y1), (x2, y2 + 1)], fill=color, width=width)

        # Bottom border (if not skipped)
        if not skip_bottom:
            draw.line([(x1, y2), (x2 + 1, y2)], fill=color, width=width)

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

        # Fill in gaps between start and end time to show continuous schedule
        if time_slots:
            start_minutes = sort_time_key(time_slots[0])
            end_minutes = sort_time_key(time_slots[-1])
            
            full_time_slots = []
            for minutes in range(start_minutes, end_minutes + 30, 30):
                # Convert back to HH:MM
                h = (minutes // 60) % 24
                m = minutes % 60
                time_str = f"{h:02d}:{m:02d}"
                full_time_slots.append(time_str)
                
                # Ensure slot exists in schedule (init with empty days if missing)
                if time_str not in schedule:
                    schedule[time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
            
            time_slots = full_time_slots

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
        self._draw_calendar_grid(img, draw, days, time_slots, schedule, blocked_times, events)

        # Draw footer with timestamp and voter count
        self._draw_footer(draw, width, height, total_voters)

        # Render all emojis using pilmoji if available
        if PILMOJI_AVAILABLE:
            # Use emoji_scale_factor to make emojis larger and more prominent
            with Pilmoji(img, emoji_scale_factor=0.95) as pilmoji:
                # Draw calendar cell emojis
                for text_x, text_y, display_text, font in self._emoji_positions:
                    # Guild War emoji gets moved up by an additional 2px (total 4px)
                    if "🏰" in display_text:
                        pilmoji.text((text_x, text_y), display_text, font=font, fill=self.HEADER_TEXT, emoji_position_offset=(0, -4))
                    else:
                        pilmoji.text((text_x, text_y), display_text, font=font, fill=self.HEADER_TEXT, emoji_position_offset=(0, -2))
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

        # Don't generate a fixed time range - instead, ensure all time slots that have events exist
        # The _crop_empty_hours function will remove empty slots at the extremities
        # This allows events to appear at any time after timezone conversion
        for time_str in list(schedule.keys()):
            # Ensure all days exist for each time slot
            if time_str not in schedule:
                schedule[time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
            else:
                # Ensure all days exist
                for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                    if d not in schedule[time_str]:
                        schedule[time_str][d] = []

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
                    # Create time slot if it doesn't exist (ensures Guild War shows even with no votes)
                    if slot_time_str not in schedule:
                        schedule[slot_time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
                    # Add Guild War event (priority 0, will be handled specially)
                    schedule[slot_time_str][short_day].append((0, "Guild War", 0, start_time_str, duration))
                    current_dt += timedelta(minutes=30)

        # Add locked events (Hero's Realm Reset, Sword Trial Echo) - these always show
        from datetime import datetime, timedelta
        for event_name, event_info in events.items():
            if event_info.get("type") == "locked":
                # Skip if already added via winning_times (to avoid duplicates)
                if event_name in winning_times:
                    continue

                fixed_time_str = event_info.get("fixed_time")
                event_days = event_info.get("days", [])
                duration = event_info.get("duration", 30)
                priority = event_info.get("priority", 3)

                if not fixed_time_str or not event_days:
                    continue

                # Parse time
                start_dt = datetime.strptime(fixed_time_str, "%H:%M")
                time_slots_spanned = max(1, duration // 30)

                # Generate all time slots for this locked event
                for i in range(time_slots_spanned):
                    slot_time = start_dt + timedelta(minutes=i * 30)
                    slot_time_str = slot_time.strftime("%H:%M")

                    # Create time slot if it doesn't exist
                    if slot_time_str not in schedule:
                        schedule[slot_time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

                    # Add locked event to all configured days
                    for day_full in event_days:
                        short_day = day_map.get(day_full, day_full[:3])
                        schedule[slot_time_str][short_day].append((priority, event_name, 0, fixed_time_str, duration))

        # Note: Events will be sorted dynamically at draw time based on position rules

        return schedule

    def _sort_events_for_display(self, events_in_cell: List, current_time: str) -> List:
        """Sort events for display based on priority

        Rules:
        - Party always appears on top in combo cells
        - Other events sorted by priority

        Args:
            events_in_cell: List of (priority, event_name, slot_num, start_time, duration)
            current_time: Current time slot being displayed

        Returns:
            Sorted list of events with Party always first
        """
        # Separate Party and other events
        party_events = [e for e in events_in_cell if e[1] == "Party"]
        other_events = [e for e in events_in_cell if e[1] != "Party"]

        if not other_events:
            return party_events
        if not party_events:
            # Sort by priority (first element of tuple)
            return sorted(other_events, key=lambda x: x[0], reverse=True)

        # Party always goes first, then other events sorted by priority
        other_sorted = sorted(other_events, key=lambda x: x[0], reverse=True)
        return party_events + other_sorted

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
                self.GRID_COLOR, skip_right=skip_right, skip_bottom=False, skip_top=False, skip_left=skip_left, width=3
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
        img: Image.Image,
        draw: ImageDraw,
        days: List[str],
        time_slots: List[str],
        schedule: Dict,
        blocked_times: List[Dict],
        events: Dict
    ):
        """Draw the calendar grid with times and events"""
        start_y = self.HEADER_HEIGHT + self.PADDING

        # Build a grid of cell contents for border optimization
        cell_contents = {}  # (row, col) -> sorted event names tuple
        overlays = []  # List of (x, y, height) for Guild War text
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

            # Draw time label (right-aligned, bold)
            bbox = draw.textbbox((0, 0), time_str, font=self.font_bold)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            time_x = self.TIME_COL_WIDTH + self.PADDING - text_width - 5
            time_y = y + 5  # Top aligned with padding
            draw.text((time_x, time_y), time_str, fill=self.TIME_TEXT, font=self.font_bold)

            # Draw cells for each day
            for col, day in enumerate(days):
                x = self.TIME_COL_WIDTH + (col * self.CELL_WIDTH) + self.PADDING

                # Get events in this cell
                events_in_cell = []
                if time_str in schedule and day in schedule[time_str]:
                    events_in_cell = schedule[time_str][day]

                # --- 1. Determine Layout & Draw Backgrounds ---
                
                # Separate Party from others
                party_event = None
                other_events = []
                
                if events_in_cell:
                    for evt in events_in_cell:
                        if evt[1] == "Party":
                            party_event = evt
                        else:
                            other_events.append(evt)

                # Determine area for other events
                has_party = (party_event is not None)
                
                # Sort other events by start time for Left/Right split
                # evt structure: (priority, event_name, slot_num, start_time, duration)
                # Sort by start_time (idx 3) then priority (idx 0)
                def event_sort_key(e):
                    # Parse time to comparable
                    h, m = map(int, e[3].split(':'))
                    # Handle post-midnight times
                    if h < 5: h += 24 
                    return (h * 60 + m, -e[0]) # Earlier time first, then higher priority
                
                other_events.sort(key=event_sort_key)
                
                # Define rects
                rects_to_draw = [] # (rect_tuple, event_name, is_party)
                
                if has_party:
                    # Top Half: Party
                    rects_to_draw.append(
                        ([x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT // 2], "Party", True)
                    )
                    
                    # Bottom Half: Others
                    bottom_rect = [x, y + self.CELL_HEIGHT // 2, x + self.CELL_WIDTH, y + self.CELL_HEIGHT]
                    
                    if not other_events:
                        # Empty bottom
                        draw.rectangle(bottom_rect, fill=self.CELL_BG, outline=None)
                    elif len(other_events) == 1:
                        # Full Bottom
                        rects_to_draw.append((bottom_rect, other_events[0][1], False))
                    else:
                        # Split Bottom Left/Right
                        mid_x = x + self.CELL_WIDTH // 2
                        left_rect = [x, y + self.CELL_HEIGHT // 2, mid_x, y + self.CELL_HEIGHT]
                        right_rect = [mid_x, y + self.CELL_HEIGHT // 2, x + self.CELL_WIDTH, y + self.CELL_HEIGHT]
                        
                        rects_to_draw.append((left_rect, other_events[0][1], False))
                        rects_to_draw.append((right_rect, other_events[1][1], False))
                        
                else:
                    # No Party - Full Cell for Others
                    full_rect = [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT]
                    
                    if not other_events:
                        # Empty Cell
                        draw.rectangle(full_rect, fill=self.CELL_BG, outline=None)
                    elif len(other_events) == 1:
                        # Full Cell
                        rects_to_draw.append((full_rect, other_events[0][1], False))
                    else:
                        # Split Full Cell Left/Right
                        mid_x = x + self.CELL_WIDTH // 2
                        left_rect = [x, y, mid_x, y + self.CELL_HEIGHT]
                        right_rect = [mid_x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT]
                        
                        rects_to_draw.append((left_rect, other_events[0][1], False))
                        rects_to_draw.append((right_rect, other_events[1][1], False))

                # --- 2. Draw Rectangles & Borders ---
                
                # Check adjacent rows for event continuity (for border skipping)
                prev_row_events = cell_contents.get((row - 1, col), ())
                next_row_events = cell_contents.get((row + 1, col), ())
                multi_slot_events = ["Breaking Army", "Showdown", "Guild War"]

                # If cell is empty, draw default border
                if not rects_to_draw:
                    # Determine border widths for empty cell
                    top_w = 3 if row == 0 else 2
                    bottom_w = 3 if row == len(time_slots) - 1 else 2
                    left_w = 3 if col == 0 else 2
                    right_w = 3 if col == len(days) - 1 else 2
                    
                    self._draw_borders(
                        draw, x, y, x + self.CELL_WIDTH - 1, y + self.CELL_HEIGHT - 1,
                        self.GRID_COLOR,
                        top_width=top_w, left_width=left_w,
                        right_width=right_w, bottom_width=bottom_w
                    )

                # Draw each rect with its specific background and borders
                for rect, evt_name, is_party in rects_to_draw:
                    rect_x, rect_y, rect_x2, rect_y2 = rect
                    
                    # 1. Background
                    color = self.EVENT_BG_COLORS.get(evt_name, self.CELL_BG)
                    color_faded = self._fade_color(color)
                    draw.rectangle(rect, fill=color_faded, outline=None)
                    
                    # 2. Borders
                    # Default widths (internal=2, external=3)
                    top_w = 2
                    bottom_w = 2
                    left_w = 2
                    right_w = 2
                    
                    # Adjust for cell edges (External borders)
                    is_cell_top = (rect_y == y)
                    is_cell_bottom = (rect_y2 == y + self.CELL_HEIGHT)
                    is_cell_left = (rect_x == x)
                    is_cell_right = (rect_x2 == x + self.CELL_WIDTH)
                    
                    if is_cell_top and row == 0: top_w = 3
                    if is_cell_bottom and row == len(time_slots) - 1: bottom_w = 3
                    if is_cell_left and col == 0: left_w = 3
                    if is_cell_right and col == len(days) - 1: right_w = 3

                    # Skip Top Border?
                    # Only if this specific event continues from above
                    skip_top = False
                    if is_cell_top and evt_name in multi_slot_events and evt_name in prev_row_events:
                        # Check if it's a clean continuation (simple logic: just check existence)
                        # The user issue was SD losing border when sharing with BA. 
                        # By checking evt_name specifically, BA won't lose border if only SD continues.
                        skip_top = True
                    
                    # Skip Bottom Border?
                    skip_bottom = False
                    if is_cell_bottom and evt_name in multi_slot_events and evt_name in next_row_events:
                        skip_bottom = True

                    # Party specific: Top border always exists unless... well Party doesn't span rows.
                    # Party is short, so it never skips top/bottom borders based on continuity.
                    if evt_name == "Party":
                        skip_top = False
                        skip_bottom = False

                    if skip_top: top_w = 0
                    if skip_bottom: bottom_w = 0
                    
                    self._draw_borders(
                        draw, rect_x, rect_y, rect_x2 - 1, rect_y2 - 1,
                        self.GRID_COLOR,
                        top_width=top_w, left_width=left_w,
                        right_width=right_w, bottom_width=bottom_w
                    )

                # --- 3. Draw Text/Emojis ---
                
                # Prepare events list for text drawing
                # We need to match the layout logic: Party first, then sorted others
                events_to_text = []
                
                if party_event:
                    # Party uses the first rect
                    events_to_text.append((party_event, rects_to_draw[0][0]))
                    
                    # Add others
                    if other_events:
                        if len(other_events) == 1:
                            # One other event -> second rect
                            events_to_text.append((other_events[0], rects_to_draw[1][0]))
                        else:
                            # Two other events -> second and third rects
                            events_to_text.append((other_events[0], rects_to_draw[1][0]))
                            events_to_text.append((other_events[1], rects_to_draw[2][0]))
                else:
                    # No party
                    if other_events:
                        if len(other_events) == 1:
                             events_to_text.append((other_events[0], rects_to_draw[0][0]))
                        else:
                             events_to_text.append((other_events[0], rects_to_draw[0][0]))
                             events_to_text.append((other_events[1], rects_to_draw[1][0]))

                # Draw text for each mapped event
                for (priority, event_name, slot_num, start_time, duration), rect in events_to_text:
                    rect_x, rect_y, rect_x2, rect_y2 = rect
                    rect_width = rect_x2 - rect_x
                    rect_height = rect_y2 - rect_y
                    
                    # Get emoji
                    if event_name == "Guild War":
                        emoji = "🏰"
                    else:
                        emoji = events.get(event_name, {}).get("emoji", "•")

                    # Helper to prepare text lines
                    def prepare_lines(text):
                        lines = []
                        if "(" in text and ")" in text:
                            parts = text.split("(", 1)
                            lines.append(parts[0].strip())
                            lines.append(f"({parts[1]}")
                        else:
                            lines.append(text)
                        return lines

                    event_lines = prepare_lines(event_name)
                    
                    # Try Standard Font
                    font_to_use = self.font_bold
                    display_lines = [f"{emoji} {event_lines[0]}"] + event_lines[1:]
                    
                    # Check width and wrap if needed
                    # Logic: 
                    # 1. Try standard font.
                    # 2. If too wide, try small font.
                    # 3. If still too wide, wrap words.
                    
                    def check_fit(lines, font):
                        for line in lines:
                            w = draw.textbbox((0, 0), line, font=font)[2]
                            if w > rect_width - 4: # 4px padding
                                return False
                        return True

                    if not check_fit(display_lines, self.font_bold):
                        if check_fit(display_lines, self.font_small):
                            font_to_use = self.font_small
                        else:
                            # Need to wrap. Use small font for wrapped text.
                            font_to_use = self.font_small
                            # Simple word wrap for the name part
                            words = event_name.split()
                            wrapped_lines = []
                            current_line = f"{emoji}"
                            
                            for word in words:
                                test_line = f"{current_line} {word}".strip()
                                if draw.textbbox((0, 0), test_line, font=font_to_use)[2] <= rect_width - 4:
                                    current_line = test_line
                                else:
                                    wrapped_lines.append(current_line)
                                    current_line = word
                            wrapped_lines.append(current_line)
                            display_lines = wrapped_lines

                    # Calculate positions
                    line_height = 15
                    if font_to_use == self.font_small:
                        line_height = 12
                        
                    total_text_height = len(display_lines) * line_height

                    # Center text vertically in its rect
                    # Special adjustment for Party to move up 2px
                    y_offset = -2 if event_name == "Party" else 0
                    base_y = rect_y + (rect_height - total_text_height) // 2 + y_offset

                    if not hasattr(self, '_emoji_positions'):
                        self._emoji_positions = []

                    for line_idx, line_text in enumerate(display_lines):
                        bbox = draw.textbbox((0, 0), line_text, font=font_to_use)
                        text_width = bbox[2] - bbox[0]

                        # Center horizontally in rect
                        text_x = rect_x + (rect_width - text_width) // 2
                        text_y = base_y + (line_idx * line_height)
                        
                        # Add boundary checks to avoid drawing outside rect
                        if text_y >= rect_y - 2 and text_y + line_height <= rect_y2 + 5:
                             self._emoji_positions.append((text_x, text_y, line_text, font_to_use))

                    # Collect Overlays
                    if event_name == "Guild War" and start_time == time_str:
                        num_slots = max(1, duration // 30)
                        overlay_height = num_slots * self.CELL_HEIGHT
                        overlay_text = "2 Games / Locked" if priority == 0 else "2 Games"
                        # Use x, y from loop (cell origin)
                        overlays.append((x, y, overlay_height, overlay_text))

                    if event_name == "Hero's Realm (Reset)" and start_time == time_str:
                        num_slots = max(1, duration // 30)
                        overlay_height = num_slots * self.CELL_HEIGHT
                        overlays.append((x, y, overlay_height, "Locked"))

        # Draw overlays for multi-slot events
        for x, y, height, text in overlays:
            # Create text image - width is height because we rotate
            # Use a reasonable width for the text strip (e.g. 30px to fit descenders)
            txt_img_height = 30
            txt_img = Image.new('RGBA', (height, txt_img_height), (0, 0, 0, 0))
            txt_draw = ImageDraw.Draw(txt_img)
            
            # Calculate text size to center it
            bbox = txt_draw.textbbox((0, 0), text, font=self.font_bold)
            txt_w = bbox[2] - bbox[0]
            txt_h = bbox[3] - bbox[1]
            
            # Draw text centered along the strip
            txt_x = (height - txt_w) // 2
            txt_y = (txt_img_height - txt_h) // 2
            # Use 20% opacity (alpha 51) for the text
            txt_draw.text((txt_x, txt_y), text, font=self.font_bold, fill=(*self.HEADER_TEXT, 51))
            
            # Rotate 90 degrees (vertical reading up)
            rotated_txt = txt_img.rotate(90, expand=True)
            
            # Paste onto main image at left edge of block
            # x + padding, y (start of block)
            paste_x = x - 5
            paste_y = y
            
            img.paste(rotated_txt, (paste_x, paste_y), rotated_txt)

    def _draw_legend(self, draw: ImageDraw, width: int, start_y: int, events: Dict):
        """Draw legend showing event labels and names"""
        # Draw legend background
        legend_y = start_y + 5
        legend_x1 = self.PADDING
        legend_x2 = width - self.PADDING
        legend_y2 = legend_y + self.LEGEND_HEIGHT - 10
        draw.rectangle(
            [legend_x1, legend_y, legend_x2, legend_y2],
            fill=self.LEGEND_BG,
            outline=None
        )
        # Draw 3px border around legend
        draw.line([(legend_x1, legend_y), (legend_x2, legend_y)], fill=self.GRID_COLOR, width=3)  # Top
        draw.line([(legend_x1, legend_y), (legend_x1, legend_y2)], fill=self.GRID_COLOR, width=3)  # Left
        draw.line([(legend_x2, legend_y), (legend_x2, legend_y2)], fill=self.GRID_COLOR, width=3)  # Right
        draw.line([(legend_x1, legend_y2), (legend_x2, legend_y2)], fill=self.GRID_COLOR, width=3)  # Bottom

        # Draw "Legend:" title
        title_x = self.PADDING + 5
        title_y = legend_y + 4
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
        col1_x = self.PADDING + 10
        col2_x = width // 2 + 5
        current_x = col1_x
        current_y = legend_y + 16

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
            text_x = current_x + 5  # Space for emoji (reduced for smaller fonts)
            draw.text((text_x, current_y), text_part, fill=self.HEADER_TEXT, font=self.font_small)

            # Move to next position (3 items per column)
            if idx == 2:
                current_x = col2_x
                current_y = legend_y + 16
            else:
                current_y += 9

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

        # Find first time slot with any events (including Guild War)
        first_event_idx = None
        for idx, time_str in enumerate(time_slots):
            has_events = False
            for day in days:
                if time_str in schedule and day in schedule[time_str]:
                    if schedule[time_str][day]:  # Check if events list is not empty (includes Guild War)
                        has_events = True
                        break
            if has_events:
                first_event_idx = idx
                break

        # Find last time slot with any events (including Guild War)
        last_event_idx = None
        for idx in range(len(time_slots) - 1, -1, -1):
            time_str = time_slots[idx]
            has_events = False
            for day in days:
                if time_str in schedule and day in schedule[time_str]:
                    if schedule[time_str][day]:  # Check if events list is not empty (includes Guild War)
                        has_events = True
                        break
            if has_events:
                last_event_idx = idx
                break

        # If no events found, return original list
        if first_event_idx is None or last_event_idx is None:
            return time_slots

        # Return cropped list (Guild War is already included in the schedule)
        return time_slots[first_event_idx:last_event_idx + 1]
