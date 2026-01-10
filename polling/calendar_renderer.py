"""Calendar image rendering using PIL"""

from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Tuple
import io


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

    # Layout constants
    CELL_WIDTH = 90
    CELL_HEIGHT = 40
    TIME_COL_WIDTH = 70
    HEADER_HEIGHT = 50
    PADDING = 10

    def __init__(self, timezone: str = "UTC"):
        """Initialize calendar renderer

        Args:
            timezone: Timezone string to display in header
        """
        self.timezone = timezone

        # Try to load a nice font, fallback to default
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except:
            self.font = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
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
                {"day": "Saturday", "start": "20:30", "end": "22:30"},
                {"day": "Sunday", "start": "20:30", "end": "22:30"}
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

        # Draw timezone header
        self._draw_timezone_header(draw, width)

        # Draw column headers (days)
        self._draw_day_headers(draw, days)

        # Draw time labels and calendar grid
        self._draw_calendar_grid(draw, days, time_slots, schedule, blocked_times)

        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        return buffer

    def _build_schedule(self, winning_times: Dict, events: Dict) -> Dict[str, Dict[str, List]]:
        """Build schedule data structure from winning times

        Returns:
            Dict mapping time -> day -> [(priority, emoji)]
        """
        schedule = {}
        day_map = {
            "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed",
            "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"
        }

        for event_name, day_times in winning_times.items():
            event_info = events[event_name]
            priority = event_info.get("priority", 0)
            emoji = event_info.get("emoji", "•")

            for day, time_str in day_times.items():
                short_day = day_map.get(day, day[:3])

                if time_str not in schedule:
                    schedule[time_str] = {d: [] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

                schedule[time_str][short_day].append((priority, emoji))

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
        y = self.HEADER_HEIGHT + self.PADDING

        for i, day in enumerate(days):
            x = self.TIME_COL_WIDTH + (i * self.CELL_WIDTH) + self.PADDING

            # Draw header background
            draw.rectangle(
                [x, y, x + self.CELL_WIDTH, y + self.CELL_HEIGHT],
                fill=self.HEADER_BG,
                outline=self.GRID_COLOR
            )

            # Draw day text (centered)
            bbox = draw.textbbox((0, 0), day, font=self.font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x + (self.CELL_WIDTH - text_width) // 2
            text_y = y + (self.CELL_HEIGHT - text_height) // 2
            draw.text((text_x, text_y), day, fill=self.HEADER_TEXT, font=self.font)

    def _draw_calendar_grid(
        self,
        draw: ImageDraw,
        days: List[str],
        time_slots: List[str],
        schedule: Dict,
        blocked_times: List[Dict]
    ):
        """Draw the calendar grid with times and events"""
        start_y = self.HEADER_HEIGHT + self.CELL_HEIGHT + self.PADDING

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

                # Draw events in this cell
                if time_str in schedule and day in schedule[time_str]:
                    events_in_cell = schedule[time_str][day]

                    if events_in_cell:
                        # Draw emojis/symbols
                        emoji_text = " ".join(emoji for _, emoji in events_in_cell[:4])  # Max 4 events

                        # Center the emoji text
                        bbox = draw.textbbox((0, 0), emoji_text, font=self.font)
                        text_width = bbox[2] - bbox[0]
                        text_height = bbox[3] - bbox[1]
                        text_x = x + (self.CELL_WIDTH - text_width) // 2
                        text_y = y + (self.CELL_HEIGHT - text_height) // 2

                        draw.text((text_x, text_y), emoji_text, font=self.font, embedded_color=True)

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
