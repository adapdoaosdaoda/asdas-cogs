#!/usr/bin/env python3
"""Tests for Party Guild War adjustment in polling cog."""

import os
import sys
from unittest.mock import MagicMock

# Ensure parent directory is in sys.path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Mock redbot and discord modules for standalone execution
mock_redbot = MagicMock()
mock_core = MagicMock()
mock_commands = MagicMock()
class Cog:
    @classmethod
    def listener(cls, *args, **kwargs): return lambda f: f
mock_commands.Cog = Cog
mock_core.commands = mock_commands
mock_core.Config = MagicMock()
mock_redbot.core = mock_core
sys.modules['redbot'] = mock_redbot
sys.modules['redbot.core'] = mock_core
sys.modules['redbot.core.commands'] = mock_commands
sys.modules['redbot.core.bot'] = MagicMock()
sys.modules['redbot.core.utils'] = MagicMock()
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.ext.tasks'] = MagicMock()
sys.modules['discord.ui'] = MagicMock()

import unittest
from polling.polling import EventPolling
from polling.calendar_renderer import CalendarRenderer


class TestPartyGuildWarAdjustment(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.cog = EventPolling(self.bot)

    def test_party_overlaps_guild_war(self):
        # Guild War is at 19:30, duration 90 min (ends 21:00)
        # Party duration is 10 min
        self.assertTrue(self.cog._party_overlaps_guild_war("20:00"))
        self.assertTrue(self.cog._party_overlaps_guild_war("19:30"))
        self.assertTrue(self.cog._party_overlaps_guild_war("20:30"))

        # No overlap
        self.assertFalse(self.cog._party_overlaps_guild_war("19:00"))
        self.assertFalse(self.cog._party_overlaps_guild_war("21:00"))
        self.assertFalse(self.cog._party_overlaps_guild_war("18:30"))
        self.assertFalse(self.cog._party_overlaps_guild_war("22:00"))
        self.assertFalse(self.cog._party_overlaps_guild_war("01:00"))

    def test_prepare_calendar_data_overlapping(self):
        # When Party voted time is 20:00
        winning_times = {
            "Party": {
                0: (("Daily", "20:00"), 15, [(("Daily", "20:00"), 15)])
            }
        }
        cal_data = self.cog._prepare_calendar_data(winning_times, convert_to_local=False)
        self.assertIn("Party", cal_data)
        party_days = cal_data["Party"]

        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            self.assertEqual(party_days[day], "20:00", f"Expected 20:00 on {day}")

        for day in ["Saturday", "Sunday"]:
            self.assertEqual(party_days[day], "19:00", f"Expected 19:00 on {day}")

    def test_prepare_calendar_data_non_overlapping(self):
        # When Party voted time is 19:00 (does not overlap with GW 19:30-21:00)
        winning_times = {
            "Party": {
                0: (("Daily", "19:00"), 15, [(("Daily", "19:00"), 15)])
            }
        }
        cal_data = self.cog._prepare_calendar_data(winning_times, convert_to_local=False)
        party_days = cal_data["Party"]

        for day in self.cog.days_of_week:
            self.assertEqual(party_days[day], "19:00", f"Expected 19:00 on {day}")

    def test_calendar_renderer_daily_expansion(self):
        # Test renderer _build_schedule when given Daily format directly
        renderer = CalendarRenderer(timezone="Server Time")
        cal_data = {
            "Party": {"Daily": "20:00"},
            "Guild War": {"Saturday": "19:30", "Sunday": "19:30"}
        }
        schedule = renderer._build_schedule(cal_data, self.cog.events)

        # On Saturday: Party should be at 19:00, Guild War at 19:30, 20:00, 20:30
        sat_1900_events = [e[1] for e in schedule.get("19:00", {}).get("Sat", [])]
        self.assertIn("Party", sat_1900_events)

        sat_2000_events = [e[1] for e in schedule.get("20:00", {}).get("Sat", [])]
        self.assertNotIn("Party", sat_2000_events)
        self.assertIn("Guild War", sat_2000_events)

        # On Monday: Party should be at 20:00
        mon_2000_events = [e[1] for e in schedule.get("20:00", {}).get("Mon", [])]
        self.assertIn("Party", mon_2000_events)

    def test_snapshot_summary(self):
        snapshot = {
            "Party": {
                0: (("Daily", "20:00"), 15, [(("Daily", "20:00"), 15)])
            }
        }
        summary = self.cog._get_snapshot_summary(snapshot, use_discord_timestamps=False)
        self.assertIn("20:00", summary)
        self.assertIn("19:00", summary)
        self.assertIn("Mon-Fri", summary)
        self.assertIn("Sat-Sun", summary)

    def test_format_all_results_inline(self):
        winning_times = {
            "Party": {
                0: (("Daily", "20:00"), 15, [(("Daily", "20:00"), 15)])
            }
        }
        selections = {"123": {"Party": {"time": "20:00"}}}
        inline_text = self.cog.format_all_results_inline(winning_times, selections)
        self.assertIn("Party", inline_text)
        self.assertIn("Sat/Sun: 19:00", inline_text)


if __name__ == "__main__":
    unittest.main()
