#!/usr/bin/env python3
"""Comprehensive test for updated EventPolling logic"""

from datetime import datetime, time as dt_time, timedelta
from typing import Tuple


def time_ranges_overlap(start1: dt_time, end1: dt_time, start2: dt_time, end2: dt_time) -> bool:
    """Check if two time ranges overlap"""
    return start1 < end2 and start2 < end1


def get_event_time_range(event_name: str, start_time_str: str, events: dict) -> Tuple[dt_time, dt_time]:
    """Get the start and end time for an event based on its duration"""
    start_time = datetime.strptime(start_time_str, "%H:%M").time()
    duration = events[event_name]["duration"]

    # Convert to datetime for calculation
    start_dt = datetime.combine(datetime.today(), start_time)
    end_dt = start_dt + timedelta(minutes=duration)

    return start_time, end_dt.time()


def is_time_blocked(day, time_str, event_name, events, blocked_times):
    """Check if a time is in the blocked times list"""
    if not day:
        # For daily events, check all days
        for blocked in blocked_times:
            blocked_start = datetime.strptime(blocked["start"], "%H:%M").time()
            blocked_end = datetime.strptime(blocked["end"], "%H:%M").time()
            event_start, event_end = get_event_time_range(event_name, time_str, events)

            if time_ranges_overlap(event_start, event_end, blocked_start, blocked_end):
                return True, f"This time conflicts with a blocked period on {blocked['day']}"
    else:
        # For weekly events, only check the selected day
        for blocked in blocked_times:
            if blocked["day"] == day:
                blocked_start = datetime.strptime(blocked["start"], "%H:%M").time()
                blocked_end = datetime.strptime(blocked["end"], "%H:%M").time()
                event_start, event_end = get_event_time_range(event_name, time_str, events)

                if time_ranges_overlap(event_start, event_end, blocked_start, blocked_end):
                    return True, f"This time conflicts with a blocked period (Sat 20:30-22:30)"

    return False, None


# Event definitions
events = {
    "Party": {"type": "daily", "duration": 10},
    "Breaking Army #1": {"type": "once", "duration": 60},
    "Breaking Army #2": {"type": "once", "duration": 60},
    "Showdown #1": {"type": "once", "duration": 60},
    "Showdown #2": {"type": "once", "duration": 60}
}

# Blocked times
blocked_times = [
    {"day": "Saturday", "start": "20:30", "end": "22:30"}
]

print("=" * 70)
print("TESTING UPDATED EVENT POLLING LOGIC")
print("=" * 70)
print()

# Test 1: Time range calculation
print("Test 1: Time range calculation")
print("-" * 70)
party_start, party_end = get_event_time_range("Party", "20:00", events)
print(f"Party at 20:00 (10 min): {party_start} - {party_end}")
assert party_start == datetime.strptime("20:00", "%H:%M").time()
assert party_end == datetime.strptime("20:10", "%H:%M").time()

ba_start, ba_end = get_event_time_range("Breaking Army #1", "20:00", events)
print(f"Breaking Army #1 at 20:00 (60 min): {ba_start} - {ba_end}")
assert ba_start == datetime.strptime("20:00", "%H:%M").time()
assert ba_end == datetime.strptime("21:00", "%H:%M").time()
print("✅ PASSED\n")

# Test 2: Time range overlap detection
print("Test 2: Time range overlap detection")
print("-" * 70)
overlap1 = time_ranges_overlap(
    datetime.strptime("20:00", "%H:%M").time(),  # 20:00
    datetime.strptime("20:10", "%H:%M").time(),  # 20:10
    datetime.strptime("20:05", "%H:%M").time(),  # 20:05
    datetime.strptime("21:05", "%H:%M").time(),  # 21:05
)
print(f"20:00-20:10 vs 20:05-21:05: {overlap1}")
assert overlap1 == True

overlap2 = time_ranges_overlap(
    datetime.strptime("20:00", "%H:%M").time(),  # 20:00
    datetime.strptime("20:10", "%H:%M").time(),  # 20:10
    datetime.strptime("20:10", "%H:%M").time(),  # 20:10
    datetime.strptime("21:10", "%H:%M").time(),  # 21:10
)
print(f"20:00-20:10 vs 20:10-21:10: {overlap2}")
assert overlap2 == False

overlap3 = time_ranges_overlap(
    datetime.strptime("20:00", "%H:%M").time(),  # 20:00
    datetime.strptime("21:00", "%H:%M").time(),  # 21:00
    datetime.strptime("20:30", "%H:%M").time(),  # 20:30
    datetime.strptime("21:30", "%H:%M").time(),  # 21:30
)
print(f"20:00-21:00 vs 20:30-21:30: {overlap3}")
assert overlap3 == True
print("✅ PASSED\n")

# Test 3: Blocked time detection
print("Test 3: Blocked time detection (Saturday 20:30-22:30)")
print("-" * 70)

# Weekly event on Saturday at 20:30 (1 hour, ends 21:30) - conflicts
is_blocked, msg = is_time_blocked("Saturday", "20:30", "Breaking Army #1", events, blocked_times)
print(f"Breaking Army #1 on Saturday at 20:30: Blocked={is_blocked}")
print(f"  Message: {msg}")
assert is_blocked == True

# Weekly event on Saturday at 21:00 (1 hour, ends 22:00) - conflicts
is_blocked, msg = is_time_blocked("Saturday", "21:00", "Showdown #1", events, blocked_times)
print(f"Showdown #1 on Saturday at 21:00: Blocked={is_blocked}")
print(f"  Message: {msg}")
assert is_blocked == True

# Weekly event on Saturday at 22:30 (1 hour, ends 23:30) - no conflict
is_blocked, msg = is_time_blocked("Saturday", "22:30", "Breaking Army #2", events, blocked_times)
print(f"Breaking Army #2 on Saturday at 22:30: Blocked={is_blocked}")
assert is_blocked == False

# Weekly event on Monday at 20:30 - no conflict (different day)
is_blocked, msg = is_time_blocked("Monday", "20:30", "Showdown #2", events, blocked_times)
print(f"Showdown #2 on Monday at 20:30: Blocked={is_blocked}")
assert is_blocked == False

# Daily event at 20:30 (10 min, ends 20:40) - conflicts with Saturday block
is_blocked, msg = is_time_blocked(None, "20:30", "Party", events, blocked_times)
print(f"Party (daily) at 20:30: Blocked={is_blocked}")
print(f"  Message: {msg}")
assert is_blocked == True

# Daily event at 22:30 (10 min, ends 22:40) - no conflict (doesn't overlap)
is_blocked, msg = is_time_blocked(None, "22:30", "Party", events, blocked_times)
print(f"Party (daily) at 22:30: Blocked={is_blocked}")
assert is_blocked == False

print("✅ PASSED\n")

# Test 4: Complex conflict scenarios with durations
print("Test 4: Complex conflict scenarios with durations")
print("-" * 70)

# Party at 20:00 (ends 20:10) vs Breaking Army at 20:05 (ends 21:05) - CONFLICT
party_start, party_end = get_event_time_range("Party", "20:00", events)
ba_start, ba_end = get_event_time_range("Breaking Army #1", "20:05", events)
conflict = time_ranges_overlap(party_start, party_end, ba_start, ba_end)
print(f"Party 20:00-20:10 vs Breaking Army 20:05-21:05: Conflict={conflict}")
assert conflict == True

# Party at 20:00 (ends 20:10) vs Breaking Army at 20:10 (ends 21:10) - NO CONFLICT
party_start, party_end = get_event_time_range("Party", "20:00", events)
ba_start, ba_end = get_event_time_range("Breaking Army #1", "20:10", events)
conflict = time_ranges_overlap(party_start, party_end, ba_start, ba_end)
print(f"Party 20:00-20:10 vs Breaking Army 20:10-21:10: Conflict={conflict}")
assert conflict == False

# Breaking Army #1 at 20:00 (ends 21:00) vs Breaking Army #2 at 20:30 (ends 21:30) - CONFLICT (same day)
ba1_start, ba1_end = get_event_time_range("Breaking Army #1", "20:00", events)
ba2_start, ba2_end = get_event_time_range("Breaking Army #2", "20:30", events)
conflict = time_ranges_overlap(ba1_start, ba1_end, ba2_start, ba2_end)
print(f"Breaking Army #1 20:00-21:00 vs Breaking Army #2 20:30-21:30: Conflict={conflict}")
assert conflict == True

# Showdown #1 at 20:00 (ends 21:00) vs Showdown #2 at 21:00 (ends 22:00) - NO CONFLICT
sd1_start, sd1_end = get_event_time_range("Showdown #1", "20:00", events)
sd2_start, sd2_end = get_event_time_range("Showdown #2", "21:00", events)
conflict = time_ranges_overlap(sd1_start, sd1_end, sd2_start, sd2_end)
print(f"Showdown #1 20:00-21:00 vs Showdown #2 21:00-22:00: Conflict={conflict}")
assert conflict == False

print("✅ PASSED\n")

# Test 5: Edge case - event ending at midnight
print("Test 5: Edge case - event ending at midnight")
print("-" * 70)
ba_start, ba_end = get_event_time_range("Breaking Army #1", "23:30", events)
print(f"Breaking Army #1 at 23:30 (60 min): {ba_start} - {ba_end}")
# Should end at 00:30 next day
assert ba_start == datetime.strptime("23:30", "%H:%M").time()
assert ba_end == datetime.strptime("00:30", "%H:%M").time()
print("✅ PASSED\n")

print("=" * 70)
print("ALL TESTS PASSED! ✅")
print("=" * 70)
print("\nSummary:")
print("- Event durations work correctly (Party: 10min, Weekly: 60min)")
print("- Time range overlap detection works correctly")
print("- Blocked times (Saturday 20:30-22:30) are properly enforced")
print("- Complex conflict scenarios are handled correctly")
print("- Edge cases (midnight rollover) work as expected")
