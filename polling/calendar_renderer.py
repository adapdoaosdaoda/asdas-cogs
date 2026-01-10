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
    CELL_BG = (55, 62, 75)  # Cell background
    BLOCKED_BG = (80, 50, 50)  # Blocked time cell background
    LEGEND_BG = (50, 58, 70)  # Legend background

    # Event label mapping (text labels instead of emojis since PIL doesn't support emojis well)
    EVENT_LABELS = {
        "Hero's Realm": "HR",
        "Sword Trial": "ST",
        "Party": "P",
        "Breaking Army": "BA",
        "Showdown": "SD",
        "Guild Wars": "GW"
    }

    # Event colors for text
    EVENT_COLORS = {
        "Hero's Realm": (147, 197, 253),  # Light blue
        "Sword Trial": (196, 181, 253),    # Purple
        "Party": (253, 224, 71),           # Yellow
        "Breaking Army": (252, 165, 165),  # Light red
        "Showdown": (253, 186, 116),       # Orange
        "Guild Wars": (156, 163, 175)      # Gray
    }

    # Layout constants (increased for higher resolution)
    CELL_WIDTH = 120
    CELL_HEIGHT = 50
    TIME_COL_WIDTH = 90
    HEADER_HEIGHT = 50
    PADDING = 15

    # Event name abbreviations for display
    EVENT_ABBREV = {
        "Hero's Realm": "Hero's Realm",
        "Sword Trial": "Sword Trial",
        "Party": "Party",
        "Breaking Army": "Breaking Army",
        "Showdown": "Showdown",
        "Guild Wars": "Guild Wars"
    }

    def __init__(self, timezone: str = "UTC"):
        """Initialize calendar renderer

        Args:
            timezone: Timezone string (not used in image anymore, kept for compatibility)
        """
        self.timezone = timezone

        # Try to load a nice font with larger sizes for better clarity
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            self.font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 17)
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except:
            self.font = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_bold = ImageFont.load_default()
            self.font_large = ImageFont.load_default()

    def render_calendar(
        self,
        winning_times: Dict[str, Dict[str, str]],
        events: Dict,
        blocked_times: List[Dict] = None
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
                {"day": "Saturday", "start": "20:30", "end": "21:30"},
                {"day": "Sunday", "start": "20:30", "end": "21:30"}
            ]

        # Build schedule data structure
        schedule = self._build_schedule(winning_times, events)

        # Calculate image dimensions
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        time_slots = sorted(schedule.keys())

        width = self.TIME_COL_WIDTH + (len(days) * self.CELL_WIDTH) + (2 * self.PADDING)
        height = self.HEADER_HEIGHT + (len(time_slots) * self.CELL_HEIGHT) + (2 * self.PADDING)

        # Create image
        img = Image.new('RGB', (width, height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Initialize emoji positions list
        self._emoji_positions = []

        # Draw column headers (days)
        self._draw_day_headers(draw, days)

        # Draw time labels and calendar grid
        self._draw_calendar_grid(draw, days, time_slots, schedule, blocked_times, events)

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
                for event_name, emoji in [("Hero's Realm", "🛡️"), ("Sword Trial", "⚔️"), ("Party", "🎉"), ("Breaking Army", "⚡"), ("Showdown", "🏆"), ("Guild Wars", "🏰")]:
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

    def _build_schedule(self, winning_times: Dict, events: Dict) -> Dict[str, Dict[str, List]]:
        """Build schedule data structure from winning times

        Returns:
            Dict mapping time -> day -> [(priority, event_name, slot_num)]
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
                short_day = day_map.get(day, day[:3])

                if time_str not in schedule:
                    schedule[time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

                # Determine slot number for this event
                slot_num = day_slot_map.get(day, 0)  # 0 means single slot or not applicable

                schedule[time_str][short_day].append((priority, event_name, slot_num))

        # Generate all time slots from 18:00 to 24:00 (30 min intervals)
        all_times = []
        hour = 18
        minute = 0
        while hour < 24:
            all_times.append(f"{hour:02d}:{minute:02d}")
            minute += 30
            if minute >= 60:
                minute = 0
                hour += 1

        # Ensure all time slots exist
        for time_str in all_times:
            if time_str not in schedule:
                schedule[time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

        # Sort events by priority within each cell
        for time_str in schedule:
            for day in schedule[time_str]:
                schedule[time_str][day].sort(reverse=True, key=lambda x: x[0])

        return schedule

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

        # Track which cells have been drawn (for multi-cell spanning events)
        drawn_cells = set()

        for row, time_str in enumerate(time_slots):
            y = start_y + (row * self.CELL_HEIGHT)

            # Draw time label
            time_x = self.PADDING + 5
            time_y = y + (self.CELL_HEIGHT - 14) // 2
            draw.text((time_x, time_y), time_str, fill=self.TIME_TEXT, font=self.font)

            # Draw cells for each day
            for col, day in enumerate(days):
                x = self.TIME_COL_WIDTH + (col * self.CELL_WIDTH) + self.PADDING

                # Skip if this cell was already drawn as part of a spanning event
                if (row, col) in drawn_cells:
                    continue

                # Check if this cell is blocked
                is_blocked = self._is_time_blocked(
                    day_full_names[day],
                    time_str,
                    blocked_times
                )

                cell_bg = self.BLOCKED_BG if is_blocked else self.CELL_BG

                # Draw cell background
                draw.rectangle(
                    [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT],
                    fill=cell_bg,
                    outline=self.GRID_COLOR
                )

                # Draw Guild Wars in blocked cells
                if is_blocked:
                    display_text = "🏰 Guild Wars"
                    text_x = x + 5
                    text_y = y + (self.CELL_HEIGHT // 2) - 8
                    if not hasattr(self, '_emoji_positions'):
                        self._emoji_positions = []
                    self._emoji_positions.append((text_x, text_y, display_text, self.font_small))

                # Draw events in this cell
                if time_str in schedule and day in schedule[time_str]:
                    events_in_cell = schedule[time_str][day]

                    if events_in_cell:
                        # Get the top priority event
                        priority, event_name, slot_num = events_in_cell[0]
                        emoji = events.get(event_name, {}).get("emoji", "•")
                        event_abbrev = self.EVENT_ABBREV.get(event_name, event_name)
                        duration = events.get(event_name, {}).get("duration", 30)

                        # Calculate how many cells to span (duration / 30 minutes)
                        cells_to_span = max(1, duration // 30)

                        # Check if we have enough cells to span
                        max_span = min(cells_to_span, len(time_slots) - row)

                        # Mark cells as drawn
                        for span_row in range(row, row + max_span):
                            drawn_cells.add((span_row, col))

                        # Calculate spanning cell dimensions
                        span_height = max_span * self.CELL_HEIGHT

                        # Draw background for spanning event (slightly different color)
                        if max_span > 1:
                            # Redraw cell background for spanning event
                            event_color = self.EVENT_COLORS.get(event_name, self.HEADER_TEXT)
                            # Use a darker, semi-transparent version of event color for background
                            bg_color = tuple(max(0, c - 100) for c in event_color)
                            draw.rectangle(
                                [x + 2, y + 2, x + self.CELL_WIDTH - 2, y + span_height - 2],
                                fill=bg_color,
                                outline=event_color,
                                width=2
                            )

                        # Draw event text (emoji + name)
                        display_text = f"{emoji} {event_abbrev}"
                        text_x = x + 5
                        text_y = y + (span_height // 2) - 8

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
            ("Guild Wars", "🏰")
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
