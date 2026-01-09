# Event Polling Cog

A Discord cog for creating event scheduling polls with dropdown menus, automatic conflict detection, and duration-aware scheduling.

## Features

- **5 Event Types**: Party (daily, 10 min), Breaking Army #1/#2 (weekly, 1 hour), and Showdown #1/#2 (weekly, 1 hour)
- **Interactive Dropdowns**: Easy-to-use select menus for day and time selection
- **Duration-Aware Conflict Detection**: Prevents users from selecting overlapping event times based on event durations
- **Blocked Time Slots**: Saturday 20:30-22:30 is blocked from selection
- **Calendar View**: Real-time calendar-style display showing current winning times
- **Color-Coded Buttons**: Green for Party, Blue for Breaking Army, Red for Showdown
- **Editable Selections**: Users can freely change or clear their choices
- **Live Updates**: Poll embed updates automatically when users vote

## Events

### Party (Daily Event) 🎉
- **Duration**: 10 minutes
- **Frequency**: Daily
- **Time selection**: 18:00 - 24:00 (30-minute intervals)
- **No day selection needed**
- **Button color**: Green

### Breaking Army #1 & #2 (Weekly Events) ⚔️
- **Duration**: 1 hour
- **Frequency**: Once per week
- **First select a day** (Monday-Sunday)
- **Then select a time** (18:00 - 24:00, 30-minute intervals)
- **Button color**: Blue

### Showdown #1 & #2 (Weekly Events) 🏆
- **Duration**: 1 hour
- **Frequency**: Once per week
- **First select a day** (Monday-Sunday)
- **Then select a time** (18:00 - 24:00, 30-minute intervals)
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
   - For **Breaking Army** (⚔️ Blue): Select a day, then a time
   - For **Showdown** (🏆 Red): Select a day, then a time
3. The system checks for duration-based conflicts and blocked times
4. The poll embed updates automatically showing the current winning times in a calendar view
5. Users can edit or clear their selections anytime
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
Mon: ⚔️20:00 (3v) | 🏆21:00 (2v)
Tue: —
Wed: 🎉20:00 (5v) | ⚔️19:00 (2v)
Thu: —
Fri: 🏆20:30 (4v)
Sat: —
Sun: ⚔️21:00 (3v)

🏆 Current Winners
🎉 Party: 20:00 (5 votes)
⚔️ Breaking Army #1: 20:00 (3 votes)
⚔️ Breaking Army #2: 19:00 (2 votes)
🏆 Showdown #1: 21:00 (2 votes)
🏆 Showdown #2: 20:30 (4 votes)
```

## Permissions

- Creating polls requires `Manage Server` permission or admin role
- All users can vote in polls
- Only poll creators and admins can end polls

## Examples

**Creating a poll:**
```
User: [p]eventpoll create This Week's Events
Bot: *Creates interactive poll with 5 color-coded buttons and calendar view*
```

**User voting example 1 - Success:**
1. Click "🎉 Party" (Green) button
2. Select "20:00" from dropdown
3. ✅ Selection saved! Party at 20:00 (daily)
4. Poll calendar updates automatically

**User voting example 2 - Conflict:**
1. User has Party at 20:00 (ends 20:10)
2. Click "⚔️ Breaking Army #1" (Blue) button
3. Select "Monday", then "20:05"
4. ⚠️ Conflict detected! This time conflicts with your Party selection on Monday
5. User selects "20:10" instead
6. ✅ Selection saved! (20:10-21:10 doesn't overlap with 20:00-20:10)

**User voting example 3 - Blocked time:**
1. Click "🏆 Showdown #1" (Red) button
2. Select "Saturday", then "21:00"
3. ⚠️ Conflict detected! This time conflicts with a blocked period (Sat 20:30-22:30)
4. User selects different day or time

## Technical Details

- Uses persistent Discord UI components (Views, Buttons, Select menus)
- Stores poll data in Red-Discord Bot's Config system
- Duration-aware time range overlap detection
- Real-time poll embed updates when users vote
- Supports multiple active polls per server
- 3-minute timeout on dropdown interactions
- Automatic conflict and blocked time validation before saving selections
- Horizontal button layout (all 5 buttons in one row)
