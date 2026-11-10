#!/usr/bin/env python3
"""Tests for Hero's Realm weekly reset in winter time (CET) and summer time (CEST)."""

import os
import sys
from unittest.mock import MagicMock, patch

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


class TestHerosRealmReset(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.cog = EventPolling(self.bot)
        guild_mock = MagicMock()
        async def async_polls(): return {}
        guild_mock.polls = async_polls
        self.cog.config.guild_from_id.return_value = guild_mock

    def test_winter_time_configuration(self):
        """In winter time (CET), reset should be configured for Sunday 22:00 and Monday 20:15"""
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        hr_info = self.cog.events["Hero's Realm (Reset)"]
        self.assertEqual(hr_info["type"], "locked")
        self.assertEqual(hr_info["days"], ["Sunday", "Monday"])
        self.assertEqual(hr_info["fixed_times"], {"Sunday": "22:00", "Monday": "20:15"})
        self.assertEqual(hr_info["durations"], {"Sunday": 30, "Monday": 15})
        self.assertEqual(hr_info["slots"], 2)

    def test_summer_time_configuration(self):
        """In summer time (CEST), reset should be configured for Monday 20:15 CEST (19:15 server time)"""
        self.cog._is_winter_time = lambda: False
        self.cog._update_locked_events()

        hr_info = self.cog.events["Hero's Realm (Reset)"]
        self.assertEqual(hr_info["type"], "locked")
        self.assertEqual(hr_info["days"], ["Monday"])
        self.assertEqual(hr_info["fixed_times"], {"Monday": "19:15"})
        self.assertEqual(hr_info["durations"], {"Monday": 15})
        self.assertEqual(hr_info["slots"], 1)

    def test_prepare_calendar_data_winter(self):
        """_prepare_calendar_data in winter should include Sunday 22:00 and Monday 20:15"""
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        cal_data = self.cog._prepare_calendar_data({}, convert_to_local=False)
        self.assertIn("Hero's Realm (Reset)", cal_data)
        hr_data = cal_data["Hero's Realm (Reset)"]
        self.assertEqual(hr_data.get("Sunday"), "22:00")
        self.assertEqual(hr_data.get("Monday"), "20:15")

    def test_prepare_calendar_data_summer_local_conversion(self):
        """_prepare_calendar_data in summer should convert 19:15 server time to 20:15 CEST local time"""
        self.cog._is_winter_time = lambda: False
        self.cog._update_locked_events()

        # Mock _convert_to_local_time to simulate summer DST (+1 hour)
        with patch.object(self.cog, "_convert_to_local_time", side_effect=lambda t: "20:15" if t == "19:15" else t):
            cal_data = self.cog._prepare_calendar_data({}, convert_to_local=True)
            self.assertIn("Hero's Realm (Reset)", cal_data)
            hr_data = cal_data["Hero's Realm (Reset)"]
            self.assertEqual(hr_data.get("Monday"), "20:15")
            self.assertNotIn("Sunday", hr_data)

    def test_calculate_winning_times_weighted_winter(self):
        """_calculate_winning_times_weighted should generate slots for both Sunday and Monday in winter"""
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        winning_times = self.cog._calculate_winning_times_weighted({})
        self.assertIn("Hero's Realm (Reset)", winning_times)
        slots = winning_times["Hero's Realm (Reset)"]
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0][0], ("Sunday", "22:00"))
        self.assertEqual(slots[1][0], ("Monday", "20:15"))

    def test_calculate_winning_times_weighted_summer(self):
        """_calculate_winning_times_weighted should generate slot for Monday only in summer"""
        self.cog._is_winter_time = lambda: False
        self.cog._update_locked_events()

        winning_times = self.cog._calculate_winning_times_weighted({})
        self.assertIn("Hero's Realm (Reset)", winning_times)
        slots = winning_times["Hero's Realm (Reset)"]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0][0], ("Monday", "19:15"))

    def test_calendar_renderer_schedule_winter(self):
        """CalendarRenderer should schedule Sunday 22:00 (30 min) and Monday 20:15 (15 min)"""
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        renderer = CalendarRenderer(timezone="Europe/Berlin")
        cal_data = self.cog._prepare_calendar_data({}, convert_to_local=False)
        schedule = renderer._build_schedule(cal_data, self.cog.events)

        # Sunday 22:00 slot
        sun_2200_events = schedule.get("22:00", {}).get("Sun", [])
        hr_sun = [e for e in sun_2200_events if e[1] == "Hero's Realm (Reset)"]
        self.assertTrue(len(hr_sun) > 0, "Hero's Realm (Reset) should be scheduled on Sunday 22:00")
        priority, name, slot_num, start_time, duration = hr_sun[0]
        self.assertEqual(start_time, "22:00")
        self.assertEqual(duration, 30)

        # Monday 20:00 slot (normalized cell for 20:15 start)
        mon_2000_events = schedule.get("20:00", {}).get("Mon", [])
        hr_mon = [e for e in mon_2000_events if e[1] == "Hero's Realm (Reset)"]
        self.assertTrue(len(hr_mon) > 0, "Hero's Realm (Reset) should be scheduled on Monday 20:15")
        priority, name, slot_num, start_time, duration = hr_mon[0]
        self.assertEqual(start_time, "20:15")
        self.assertEqual(duration, 15)

    def test_calendar_renderer_fallback_winter(self):
        """CalendarRenderer fallback (empty winning_times) should also correctly place both days"""
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        renderer = CalendarRenderer(timezone="Europe/Berlin")
        schedule = renderer._build_schedule({}, self.cog.events)

        sun_2200_events = schedule.get("22:00", {}).get("Sun", [])
        hr_sun = [e for e in sun_2200_events if e[1] == "Hero's Realm (Reset)"]
        self.assertTrue(len(hr_sun) > 0)
        self.assertEqual(hr_sun[0][3], "22:00")
        self.assertEqual(hr_sun[0][4], 30)

        mon_2000_events = schedule.get("20:00", {}).get("Mon", [])
        hr_mon = [e for e in mon_2000_events if e[1] == "Hero's Realm (Reset)"]
        self.assertTrue(len(hr_mon) > 0)
        self.assertEqual(hr_mon[0][3], "20:15")
        self.assertEqual(hr_mon[0][4], 15)

    def test_catchup_tiebreaker_avoids_locked_reset_days(self):
        """Hero's Realm (Catch-up) tiebreak avoids locked Reset days (Sunday and Monday in winter)"""
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        # Simulate votes for Catch-up where Monday and Tuesday are tied with 5 points each
        selections = {
            "user1": {
                "Hero's Realm (Catch-up)": {"day": "Monday", "time": "20:00"}
            },
            "user2": {
                "Hero's Realm (Catch-up)": {"day": "Tuesday", "time": "20:00"}
            }
        }
        winning = self.cog._calculate_winning_times_weighted(selections)
        winner_key = winning["Hero's Realm (Catch-up)"][0][0]
        # Tuesday should win over Monday on tiebreaker because Monday is a locked Reset day
        self.assertEqual(winner_key[0], "Tuesday")

    def test_poll_embed_locked_display_winter(self):
        """Poll embed format for locked events in winter displays 'Sun 22:00 & Mon 20:15'"""
        import asyncio
        self.cog._is_winter_time = lambda: True
        self.cog._update_locked_events()

        with patch("discord.Embed") as mock_embed_cls:
            mock_embed = MagicMock()
            mock_embed_cls.return_value = mock_embed
            asyncio.run(self.cog._create_poll_embed("Weekly Poll", 12345, "123456789"))

            # Find call adding the "🔒 Locked" field
            locked_calls = [c for c in mock_embed.add_field.call_args_list if c.kwargs.get("name") == "🔒 Locked"]
            self.assertTrue(len(locked_calls) > 0)
            locked_value = locked_calls[0].kwargs.get("value", "")
            self.assertIn("Sun 22:00 & Mon 20:15", locked_value)


if __name__ == "__main__":
    unittest.main()
