# Event Polling Cog

A Discord cog for creating event scheduling polls with dropdown menus, automatic conflict detection, and duration-aware scheduling with multi-slot selection.

## Features

- **3 Event Types**: Party (daily, 1 slot), Breaking Army (weekly, 2 slots), and Showdown (weekly, 2 slots)
- **Multi-Slot Selection**: Select multiple day/time combinations for Breaking Army and Showdown events
- **Interactive Buttons**: Grey buttons for day selection, dropdowns for time selection
- **Duration-Aware Conflict Detection**: Prevents users from selecting overlapping event times based on event durations
- **Blocked Time Slots**: Saturday 20:30-22:30 is blocked from selection
- **Calendar View**: Real-time calendar-style display showing current winning times with slot numbers
- **Color-Coded Buttons**: Green for Party, Blue for Breaking Army, Red for Showdown
- **Editable Selections**: Users can freely change or clear their choices
- **Live Updates**: Poll embed updates automatically when users vote

## Events

### Party (Daily Event) 🎉
- **Duration**: 10 minutes
- **Frequency**: Daily
- **Slots**: 1
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **No day selection needed**
- **Button color**: Green

### Breaking Army (Weekly Event) ⚔️
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

## Usage Flow

1. Admin creates a poll using `[p]eventpoll create`
2. Users click on color-coded event buttons to make their selections:
   - For **Party** (🎉 Green): Select a time directly
   - For **Breaking Army** (⚔️ Blue): Select slot (1 or 2) → Select day (Mon-Sun) → Select time
   - For **Showdown** (🏆 Red): Select slot (1 or 2) → Select day (Mon-Sun) → Select time
3. The system checks for duration-based conflicts and blocked times across all slots
4. The poll embed updates automatically showing the current winning times in a calendar view with slot numbers
5. Users can edit or clear their selections anytime by clicking the event button again
6. Admin can view detailed results using `[p]eventpoll results`

## Conflict Detection

The cog uses **duration-aware conflict detection** to prevent overlapping events:

### Duration Rules:
- **Party**: 10 minutes (e.g., 20:00 Party ends at 20:10)
- **Weekly Events**: 1 hour (e.g., 20:00 Breaking Army ends at 21:00)

### Conflict Rules:
- **Party (daily)** conflicts with any other event if their time ranges overlap
  - Example: Party at 20:00-20:10 conflicts with Breaking Army at 20:05-21:05
  - Example: Party at 20:00-20:10 does NOT conflict with Breaking Army at 20:10-21:10
- **Weekly events** only conflict if they're on the same day AND time ranges overlap
  - Example: Breaking Army #1 (Mon 20:00-21:00) does NOT conflict with Breaking Army #2 (Tue 20:00-21:00)
  - Example: Breaking Army #1 (Mon 20:00-21:00) conflicts with Showdown #1 (Mon 20:30-21:30)
- **Blocked time**: Saturday 20:30-22:30 cannot be selected for any event
  - Events that would overlap with this period are prevented

### Error Messages:
Users receive clear, specific error messages when conflicts occur:
- "This time conflicts with your Party selection"
- "This conflicts with your Breaking Army #1 selection on Monday"
- "This time conflicts with a blocked period (Sat 20:30-22:30)"

## Calendar View

The poll embed displays a **live calendar** showing the current winning times:

```
📊 Current Leading Times (votes)
Mon: ⚔️20:00#1 (3v) | 🏆21:00#2 (2v)
Tue: —
Wed: 🎉20:00 (5v) | ⚔️19:00#2 (2v)
Thu: —
Fri: 🏆20:30#1 (4v)
Sat: —
Sun: ⚔️21:00#2 (3v)

🏆 Current Winners
🎉 Party: 20:00 (5 votes)
⚔️ Breaking Army #1: Monday 20:00 (3 votes)
⚔️ Breaking Army #2: Wednesday 19:00 (2 votes)
🏆 Showdown #1: Friday 20:30 (4 votes)
🏆 Showdown #2: Monday 21:00 (2 votes)

Note: #1 and #2 indicate slot numbers for multi-slot events
```

## Permissions

- Creating polls requires `Manage Server` permission or admin role
- All users can vote in polls
- Only poll creators and admins can end polls

## Examples

**Creating a poll:**
```
User: [p]eventpoll create This Week's Events
Bot: *Creates interactive poll with 3 color-coded buttons and calendar view*
     [🎉 Party] [⚔️ Breaking Army] [🏆 Showdown]
```

**User voting example 1 - Single slot event (Party):**
1. Click "🎉 Party" (Green) button
2. Select "20:00" from dropdown
3. ✅ Selection saved! Party at 20:00 (daily)
4. Poll calendar updates automatically

**User voting example 2 - Multi-slot event (Breaking Army):**
1. Click "⚔️ Breaking Army" (Blue) button
2. See: [Slot 1] [Slot 2] [Cancel]
3. Click "Slot 1"
4. See: [Mon] [Tue] [Wed] [Thu] [Fri] [Sat] [Sun] [Cancel]
5. Click "Mon"
6. Select "20:00" from time dropdown
7. ✅ Selection saved! Breaking Army slot 1 on Monday at 20:00
8. Click "⚔️ Breaking Army" again to set slot 2
9. Click "Slot 2" → "Wednesday" → "19:00"
10. ✅ Selection saved! Breaking Army slot 2 on Wednesday at 19:00

**User voting example 3 - Conflict:**
1. User has Party at 20:00 (ends 20:10)
2. Click "⚔️ Breaking Army" (Blue) button
3. Select "Slot 1" → "Monday" → "20:05"
4. ⚠️ Conflict detected! This time conflicts with your Party selection on Monday
5. User selects "20:10" instead
6. ✅ Selection saved! (20:10-21:10 doesn't overlap with 20:00-20:10)

**User voting example 4 - Blocked time:**
1. Click "🏆 Showdown" (Red) button
2. Select "Slot 1" → "Saturday" → "21:00"
3. ⚠️ Conflict detected! This time conflicts with a blocked period (Sat 20:30-22:30)
4. User selects different day or time

## Technical Details

- Uses persistent Discord UI components (Views, Buttons, Select menus)
- Stores poll data in Red-Discord Bot's Config system
- Multi-slot selection: List format for multi-slot events, dict format for single-slot
- Duration-aware time range overlap detection across all event slots
- Real-time poll embed updates when users vote
- Supports multiple active polls per server
- 3-minute timeout on dropdown interactions
- Automatic conflict and blocked time validation before saving selections
- Horizontal button layout: 3 main event buttons, 7 day buttons, 2 slot buttons
- Sequential selection flow: Event → Slot (if multi-slot) → Day (if weekly) → Time
