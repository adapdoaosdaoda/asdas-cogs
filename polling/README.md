# Event Polling Cog

A Discord cog for creating event scheduling polls with dropdown menus, automatic conflict detection, visual calendar images, and duration-aware scheduling with multi-slot selection.

## Installation

This cog requires **Pillow** and **pilmoji** for calendar image generation with emoji support:

```bash
pip install Pillow
pip install git+https://github.com/jay3332/pilmoji
```

**Note:** If pilmoji is not installed, the calendar will fall back to text labels (HR, ST, P, BA, SD, GW) instead of emojis.

## Features

- **5 Event Types**: Party (daily, 1 slot), Breaking Army (weekly, 2 slots), Showdown (weekly, 2 slots), Hero's Realm (fixed days, 4 slots), Sword Trial (fixed days, 4 slots)
- **Multi-Slot Selection**: Select multiple day/time combinations for Breaking Army, Showdown, Hero's Realm, and Sword Trial
- **Fixed-Day Events**: Hero's Realm and Sword Trial allow 4 separate slots (one for each day: Wed/Fri/Sat/Sun)
- **Visual Calendar Images**: Professional PNG calendar images with emoji rendering
- **Interactive Buttons**: Color-coded buttons for events (General, Sword Trial, Breaking Army, Showdown), Results button for viewing current winners
- **Duration-Aware Conflict Detection**: Prevents users from selecting overlapping event times based on event durations
- **Locked Time Slots**: Saturday & Sunday 20:30-22:00 are locked from selection
- **Calendar View**: Beautiful visual calendar images showing schedule with colored labels and emojis
- **Color-Coded Buttons**: Row 1: General (Grey), Sword Trial (Green), Breaking Army (Blue), Showdown (Red); Row 2: Results (Grey)
- **Editable Selections**: Users can freely change or clear their choices
- **Live Updates**: Calendar images update automatically when users vote

## Events

### Hero's Realm (Fixed-Day Event) 🛡️
- **Duration**: 30 minutes
- **Frequency**: Wed, Fri, Sat, Sun only
- **Slots**: 1
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **No day selection needed** (automatically appears on Wed/Fri/Sat/Sun)
- **Button color**: Grey

### Sword Trial (Fixed-Day Event) ⚔️
- **Duration**: 30 minutes
- **Frequency**: Wed, Fri, Sat, Sun only
- **Slots**: 1
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **No day selection needed** (automatically appears on Wed/Fri/Sat/Sun)
- **Button color**: Grey

### Party (Daily Event) 🎉
- **Duration**: 10 minutes
- **Frequency**: Daily
- **Slots**: 1
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **No day selection needed**
- **Button color**: Green

### Breaking Army (Weekly Event) ⚡
- **Duration**: 1 hour per slot
- **Frequency**: 2 weekly slots
- **Selection flow**: Choose slot → Choose day → Choose time
- **Day selection**: 7 grey buttons (Mon-Sun)
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **Button color**: Blue

### Showdown (Weekly Event) 🏆
- **Duration**: 1 hour per slot
- **Frequency**: 2 weekly slots
- **Selection flow**: Choose slot → Choose day → Choose time
- **Day selection**: 7 grey buttons (Mon-Sun)
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **Button color**: Red

### Guild Wars (Blocked Event) 🏰
- **Duration**: Sat & Sun 20:30-22:00
- **Not selectable** - This is a blocked time period
- **Appears in calendar** as 🏰 during blocked hours

## Configuration

### Timezone Display
You can customize the timezone display shown in calendar headers by editing `polling.py`:

```python
# In the __init__ method, around line 98:
self.timezone_display = "Server Time"  # Change this to your timezone
```

**Examples:**
- `"UTC"` - Coordinated Universal Time
- `"UTC+1"` - Central European Time
- `"UTC-5"` - Eastern Standard Time
- `"EST"` - Eastern Standard Time
- `"PST"` - Pacific Standard Time
- `"Server Time"` - Generic server time (default)

The timezone appears at the top of all calendar displays:
```
All times in UTC+1
```

## Commands

### `[p]eventpoll create [title]`
Create a new event scheduling poll with live calendar view.

**Example:**
```
[p]eventpoll create Weekly Events Schedule
```

### `[p]eventpoll results <message_id>`
Display the results of a poll showing who voted for each time.

**Example:**
```
[p]eventpoll results 123456789
```

### `[p]eventpoll end <message_id>`
End a poll and remove it from the database. Only the poll creator or server admins can use this.

**Example:**
```
[p]eventpoll end 123456789
```

### `[p]eventpoll clear <message_id> <user>`
Clear a specific user's votes from a poll.

**Example:**
```
[p]eventpoll clear 123456789 @user
```

### `[p]eventpoll calendar <message_id>`
Post an auto-updating calendar view for a poll. Creates a separate calendar embed that automatically updates when users vote, includes a link to the original poll, and provides a legend of event types.

**Example:**
```
[p]eventpoll calendar 123456789
```

## Usage Flow

1. Admin creates a poll using `[p]eventpoll create`
2. Users click on color-coded event buttons to make their selections:
   - For **Hero's Realm** (🛡️ Grey): Select a time directly (appears on Wed/Fri/Sat/Sun)
   - For **Sword Trial** (⚔️ Grey): Select a time directly (appears on Wed/Fri/Sat/Sun)
   - For **Party** (🎉 Green): Select a time directly
   - For **Breaking Army** (⚡ Blue): Select slot (1 or 2) → Select day (Mon-Sun) → Select time
   - For **Showdown** (🏆 Red): Select slot (1 or 2) → Select day (Mon-Sun) → Select time
3. The system checks for duration-based conflicts and locked times (Guild Wars 🏰) across all slots
4. The poll embed updates automatically showing the current winning times in a calendar view with slot numbers
5. Users can edit or clear their selections anytime by clicking the event button again
6. Admin can view detailed results using `[p]eventpoll results`

## Conflict Detection

The cog uses **duration-aware conflict detection** to prevent overlapping events:

### Duration Rules:
- **Party**: 10 minutes (e.g., 20:00 Party ends at 20:10)
- **Weekly Events** (Breaking Army, Showdown): 1 hour (e.g., 20:00 Breaking Army ends at 21:00)
- **Fixed-Day Events** (Hero's Realm, Sword Trial): 30 minutes (e.g., 20:00 Hero's Realm ends at 20:30)

### Conflict Rules:
- **Party (daily)** conflicts with any other event if their time ranges overlap
  - Example: Party at 20:00-20:10 conflicts with Breaking Army at 20:05-21:05
  - Example: Party at 20:00-20:10 does NOT conflict with Breaking Army at 20:10-21:10
- **Weekly events** only conflict if they're on the same day AND time ranges overlap
  - Example: Breaking Army #1 (Mon 20:00-21:00) does NOT conflict with Breaking Army #2 (Tue 20:00-21:00)
  - Example: Breaking Army #1 (Mon 20:00-21:00) conflicts with Showdown #1 (Mon 20:30-21:30)
- **Fixed-day events** conflict with other events on their specific days (Wed/Fri/Sat/Sun)
  - Example: Hero's Realm at 20:00-20:30 conflicts with Sword Trial at 20:15-20:45 (on any of Wed/Fri/Sat/Sun)
  - Example: Hero's Realm at 20:00-20:30 conflicts with Breaking Army slot 1 at 20:00-21:00 on Wednesday
  - Example: Hero's Realm at 20:00-20:30 does NOT conflict with Breaking Army slot 1 at 20:00-21:00 on Monday
- **Blocked time**: Saturday & Sunday 20:30-22:00 cannot be selected for any event
  - Events that would overlap with this period are prevented
  - 22:00 is available for selection

### Error Messages:
Users receive clear, specific error messages when conflicts occur:
- "This time conflicts with your Party selection"
- "This conflicts with your Breaking Army #1 selection on Monday"
- "This time conflicts with a blocked period (Sat & Sun 20:30-22:00)"

## Calendar View

The poll embed displays a **visual Unicode calendar table** showing the weekly schedule. You can also post a dedicated auto-updating calendar embed using `[p]eventpoll calendar <message_id>`.

```
📊 Weekly Calendar View
All times in Server Time

Time  │ Mon │ Tue │ Wed │ Thu │ Fri │ Sat │ Sun
──────────────────────────────────────────────────
18:00 │ 🎉  │ 🎉  │ 🎉  │ 🎉  │ 🎉  │ 🎉  │ 🎉
19:30 │     │     │ 🛡️  │     │ 🛡️  │ 🛡️  │ 🛡️
20:00 │ ⚡1 │     │     │     │     │     │
20:30 │     │     │     │     │ 🏆1 │ 🏰  │ 🏰
21:00 │ 🏆2 │     │ ⚡2 │     │     │ 🏰  │ 🏰

🏆 Current Winners
🛡️ Hero's Realm: 19:30 (4 votes)
🎉 Party: 18:00 (5 votes)
⚡ Breaking Army #1: Monday 20:00 (3 votes)
⚡ Breaking Army #2: Wednesday 21:00 (2 votes)
🏆 Showdown #1: Friday 20:30 (4 votes)
🏆 Showdown #2: Monday 21:00 (2 votes)
```

**Calendar Features:**
- **Grid Layout**: Easy to see which events are scheduled when at a glance
- **Monospace Font**: Uses code block for proper alignment
- **Timezone Display**: Shows "All times in Server Time" at the top
- **Full Schedule View**: Displays all time slots (18:00-24:00) with braille blank pattern for empty cells
- **Slot Numbers**: Multi-slot events show as ⚡1, ⚡2, 🏆1, 🏆2
- **Auto-updating**: Use `[p]eventpoll calendar` to post a dedicated calendar that updates automatically
- **Daily Events**: Party (🎉) appears across all days
- **Fixed-Day Events**: Hero's Realm (🛡️) and Sword Trial (⚔️) appear on Wed/Fri/Sat/Sun
- **Weekly Events**: Appear only on their scheduled day
- **Locked Times**: Guild Wars (🏰) appears on Sat & Sun 20:30-22:00

## Permissions

- Creating polls requires `Manage Server` permission or admin role
- All users can vote in polls
- Only poll creators and admins can end polls

## Examples

Creating a poll:
```
User: [p]eventpoll create This Week's Events
Bot: *Creates interactive poll with color-coded buttons and calendar view*
     [🎯 General] [⚔️ Sword Trial] [⚡ Breaking Army] [🏆 Showdown]
```

**User voting example 1 - General (Party, Hero's Realm):**
1. Click "🎯 General" (Grey) button
2. A combined modal opens allowing you to vote for Party and Hero's Realm (Catch-up)
3. ✅ Selection saved!
4. Poll calendar updates automatically

**User voting example 2 - Multi-slot event (Breaking Army):**
1. Click "⚡ Breaking Army" (Blue) button
2. See: [Slot 1] [Slot 2] [Cancel]
3. Click "Slot 1"
4. See: [Mon] [Tue] [Wed] [Thu] [Fri] [Sat] [Sun] [Cancel]
5. Click "Mon"
6. Select "20:00" from time dropdown
7. ✅ Selection saved! Breaking Army slot 1 on Monday at 20:00
8. Click "⚡ Breaking Army" again to set slot 2
9. Click "Slot 2" → "Wednesday" → "19:00"
10. ✅ Selection saved! Breaking Army slot 2 on Wednesday at 19:00

**User voting example 3 - Conflict:**
1. User has Party at 20:00 (ends 20:10)
2. Click "⚡ Breaking Army" (Blue) button
3. Select "Slot 1" → "Monday" → "20:05"
4. ⚠️ Conflict detected! This time conflicts with your Party selection on Monday
5. User selects "20:10" instead
6. ✅ Selection saved! (20:10-21:10 doesn't overlap with 20:00-20:10)

**User voting example 4 - Fixed-day event (Hero's Realm):**
1. Click "🛡️ Hero's Realm" (Grey) button
2. See message: "Select a time for Hero's Realm on Wed, Fri, Sat, Sun (18:00-24:00)"
3. Select "19:30" from time dropdown
4. ✅ Selection saved! Hero's Realm at 19:30 (Wed, Fri, Sat, Sun)
5. Calendar updates to show 🛡️ on all four days at 19:30

**User voting example 5 - Blocked time (Guild Wars):**
1. Click "🏆 Showdown" (Red) button
2. Select "Slot 1" → "Sunday" → "21:00"
3. ⚠️ Conflict detected! This time conflicts with a blocked period (Sat & Sun 20:30-22:00)
4. User sees 🏰 Guild Wars is blocking that time
5. User selects "22:00" instead (22:00 is available)
6. ✅ Selection saved!

## Technical Details

- Uses persistent Discord UI components (Views, Buttons, Select menus)
- Stores poll data in Red-Discord Bot's Config system
- Multi-slot selection: List format for multi-slot events, dict format for single-slot
- Duration-aware time range overlap detection across all event slots
- Real-time poll embed updates when users vote
- Supports multiple active polls per server
- 3-minute timeout on dropdown interactions
- Automatic conflict and blocked time validation before saving selections
- Horizontal button layout: 5 main event buttons, 7 day buttons, 2 slot buttons
- Sequential selection flow:
  - Daily events: Event → Time
  - Fixed-day events: Event → Time (appears on Wed/Fri/Sat/Sun automatically)
  - Weekly events: Event → Slot (if multi-slot) → Day → Time
