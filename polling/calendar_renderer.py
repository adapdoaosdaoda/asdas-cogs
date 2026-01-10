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

    # Layout constants
    CELL_WIDTH = 90
    CELL_HEIGHT = 40
    TIME_COL_WIDTH = 70
    HEADER_HEIGHT = 40
    LEGEND_HEIGHT = 110
    PADDING = 10

    def __init__(self, timezone: str = "UTC"):
        """Initialize calendar renderer

        Args:
            timezone: Timezone string (not used in image anymore, kept for compatibility)
        """
        self.timezone = timezone

        # Try to load a nice font, fallback to default
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
            self.font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
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
                {"day": "Saturday", "start": "20:30", "end": "22:30"},
                {"day": "Sunday", "start": "20:30", "end": "22:30"}
            ]

        # Build schedule data structure
        schedule = self._build_schedule(winning_times, events)

        # Calculate image dimensions
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        time_slots = sorted(schedule.keys())

        width = self.TIME_COL_WIDTH + (len(days) * self.CELL_WIDTH) + (2 * self.PADDING)
        height = self.HEADER_HEIGHT + (len(time_slots) * self.CELL_HEIGHT) + self.LEGEND_HEIGHT + (2 * self.PADDING)

        # Create image
        img = Image.new('RGB', (width, height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Draw column headers (days)
        self._draw_day_headers(draw, days)

        # Draw time labels and calendar grid
        self._draw_calendar_grid(draw, days, time_slots, schedule, blocked_times, events)

        # Draw legend at bottom
        grid_bottom = self.HEADER_HEIGHT + (len(time_slots) * self.CELL_HEIGHT) + self.PADDING
        self._draw_legend(draw, width, grid_bottom, events)

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
                        # Build text labels for events
                        labels = []
                        for priority, event_name, slot_num in events_in_cell[:3]:  # Max 3 events per cell
                            label = self.EVENT_LABELS.get(event_name, "?")
                            if slot_num > 0:  # Multi-slot event
                                label = f"{label}{slot_num}"
                            labels.append((label, event_name))

                        # Draw labels with colored text
                        if len(labels) == 1:
                            # Single event - centered
                            label, event_name = labels[0]
                            color = self.EVENT_COLORS.get(event_name, self.HEADER_TEXT)
                            bbox = draw.textbbox((0, 0), label, font=self.font_bold)
                            text_width = bbox[2] - bbox[0]
                            text_height = bbox[3] - bbox[1]
                            text_x = x + (self.CELL_WIDTH - text_width) // 2
                            text_y = y + (self.CELL_HEIGHT - text_height) // 2
                            draw.text((text_x, text_y), label, fill=color, font=self.font_bold)
                        else:
                            # Multiple events - stack vertically
                            total_height = len(labels) * 15
                            start_text_y = y + (self.CELL_HEIGHT - total_height) // 2
                            for idx, (label, event_name) in enumerate(labels):
                                color = self.EVENT_COLORS.get(event_name, self.HEADER_TEXT)
                                bbox = draw.textbbox((0, 0), label, font=self.font_small)
                                text_width = bbox[2] - bbox[0]
                                text_x = x + (self.CELL_WIDTH - text_width) // 2
                                text_y = start_text_y + (idx * 15)
                                draw.text((text_x, text_y), label, fill=color, font=self.font_small)

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

            # Format text
            if num_slots > 1 and event_info.get("type") == "fixed_days":
                # Show slot range for multi-slot events
                text = f"{emoji} {label}1-{label}{num_slots}: {event_name}"
            else:
                text = f"{emoji} {label}: {event_name}"

            # Draw the text
            draw.text((current_x, current_y), text, fill=self.HEADER_TEXT, font=self.font_small)

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
