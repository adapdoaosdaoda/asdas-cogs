#!/usr/bin/env python3
"""Quick test for EventPolling logic"""

from datetime import datetime


def generate_time_options(start_hour: int = 18, end_hour: int = 24, interval: int = 30):
    """Generate time options in HH:MM format"""
    times = []
    current_hour = start_hour
    current_minute = 0

    while current_hour < end_hour or (current_hour == end_hour and current_minute == 0):
        times.append(f"{current_hour:02d}:{current_minute:02d}")

        current_minute += interval
        if current_minute >= 60:
            current_minute = 0
            current_hour += 1

    return times


def check_time_conflict(user_selections, event_name, new_day, new_time, events):
    """Check if a new selection conflicts with existing selections"""
    for existing_event, selection in user_selections.items():
        if existing_event == event_name:
            continue

        existing_time = selection["time"]
        existing_day = selection.get("day")

        # Convert times to comparable format
        new_time_obj = datetime.strptime(new_time, "%H:%M").time()
        existing_time_obj = datetime.strptime(existing_time, "%H:%M").time()

        # Party is daily, so it conflicts with any event on any day at the same time
        if events[event_name]["type"] == "daily":
            if new_time == existing_time:
                return True, f"This time conflicts with your {existing_event} selection"

        elif events[existing_event]["type"] == "daily":
            if new_time == existing_time:
                if new_day:
                    return True, f"This time conflicts with your Party selection on {new_day}"
                else:
                    return True, f"This time conflicts with your Party selection"

        else:
            # Both are weekly events
            if new_day and existing_day and new_day == existing_day and new_time == existing_time:
                return True, f"This conflicts with your {existing_event} selection on {existing_day}"

    return False, None


# Test time generation
print("Testing time generation (18:00-24:00, 30min intervals):")
times = generate_time_options(18, 24, 30)
print(f"Generated {len(times)} time slots:")
print(", ".join(times))
print()

# Test conflict detection
events = {
    "Party": {"type": "daily"},
    "Breaking Army #1": {"type": "once"},
    "Breaking Army #2": {"type": "once"},
    "Showdown #1": {"type": "once"},
    "Showdown #2": {"type": "once"}
}

print("Testing conflict detection:")
print()

# Test 1: Party conflicts with weekly event at same time
user_selections = {
    "Party": {"time": "20:00"}
}
has_conflict, msg = check_time_conflict(
    user_selections, "Breaking Army #1", "Monday", "20:00", events
)
print(f"Test 1 - Party at 20:00, trying Breaking Army #1 Monday at 20:00:")
print(f"  Conflict: {has_conflict}, Message: {msg}")
print()

# Test 2: No conflict - different times
user_selections = {
    "Party": {"time": "20:00"}
}
has_conflict, msg = check_time_conflict(
    user_selections, "Breaking Army #1", "Monday", "21:00", events
)
print(f"Test 2 - Party at 20:00, trying Breaking Army #1 Monday at 21:00:")
print(f"  Conflict: {has_conflict}, Message: {msg}")
print()

# Test 3: Weekly events on different days, same time - no conflict
user_selections = {
    "Breaking Army #1": {"day": "Monday", "time": "20:00"}
}
has_conflict, msg = check_time_conflict(
    user_selections, "Showdown #1", "Tuesday", "20:00", events
)
print(f"Test 3 - Breaking Army #1 Monday 20:00, trying Showdown #1 Tuesday 20:00:")
print(f"  Conflict: {has_conflict}, Message: {msg}")
print()

# Test 4: Weekly events on same day, same time - conflict
user_selections = {
    "Breaking Army #1": {"day": "Monday", "time": "20:00"}
}
has_conflict, msg = check_time_conflict(
    user_selections, "Showdown #1", "Monday", "20:00", events
)
print(f"Test 4 - Breaking Army #1 Monday 20:00, trying Showdown #1 Monday 20:00:")
print(f"  Conflict: {has_conflict}, Message: {msg}")
print()

# Test 5: Multiple selections, complex scenario
user_selections = {
    "Party": {"time": "19:00"},
    "Breaking Army #1": {"day": "Wednesday", "time": "21:00"}
}
has_conflict, msg = check_time_conflict(
    user_selections, "Showdown #1", "Wednesday", "19:00", events
)
print(f"Test 5 - Party 19:00 + Breaking Army #1 Wed 21:00, trying Showdown #1 Wed 19:00:")
print(f"  Conflict: {has_conflict}, Message: {msg}")
print()

print("All tests completed!")
