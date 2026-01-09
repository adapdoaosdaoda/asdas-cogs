# Event Polling Cog

A Discord cog for creating event scheduling polls with dropdown menus and automatic conflict detection.

## Features

- **5 Event Types**: Party (daily), Breaking Army #1/#2, and Showdown #1/#2 (weekly)
- **Interactive Dropdowns**: Easy-to-use select menus for day and time selection
- **Conflict Detection**: Prevents users from selecting overlapping event times
- **Editable Selections**: Users can freely change or clear their choices
- **Results Display**: View aggregated results showing who voted for each time slot

## Events

### Party (Daily Event)
- Occurs every day
- Time selection: 18:00 - 24:00 (30-minute intervals)
- No day selection needed

### Breaking Army #1 & #2 (Weekly Events)
- Occur once per week
- First select a day (Monday-Sunday)
- Then select a time (18:00 - 24:00, 30-minute intervals)

### Showdown #1 & #2 (Weekly Events)
- Occur once per week
- First select a day (Monday-Sunday)
- Then select a time (18:00 - 24:00, 30-minute intervals)

## Commands

### `[p]eventpoll create [title]`
Create a new event scheduling poll.

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
2. Users click on event buttons to make their selections:
   - For **Party**: Select a time directly
   - For other events: Select a day, then a time
3. The system checks for conflicts and prevents overlapping times
4. Users can edit or clear their selections anytime
5. Admin can view results using `[p]eventpoll results`

## Conflict Detection

The cog automatically prevents conflicting selections:

- **Party (daily)** conflicts with any other event at the same time
- **Weekly events** only conflict if they're on the same day at the same time
- Users receive a clear error message if they try to select a conflicting time

## Permissions

- Creating polls requires `Manage Server` permission or admin role
- All users can vote in polls
- Only poll creators and admins can end polls

## Examples

**Creating a poll:**
```
User: [p]eventpoll create This Week's Events
Bot: *Creates interactive poll with 5 event buttons*
```

**User voting:**
1. Click "🎉 Party" button
2. Select "20:00" from dropdown
3. ✅ Selection saved!

**Viewing results:**
```
User: [p]eventpoll results 987654321
Bot: *Shows embed with all votes organized by event and time*
```

## Technical Details

- Uses persistent Discord UI components (Views, Buttons, Select menus)
- Stores poll data in Red-Discord Bot's Config system
- Supports multiple active polls per server
- 3-minute timeout on dropdown interactions
- Automatic conflict validation before saving selections
