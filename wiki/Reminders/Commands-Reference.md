# Reminders - Commands Reference

Quick reference for Reminders cog commands.

## Creating Reminders

### remindme

**Usage:** `[p]remindme <time> [message]`

Create a personal reminder in DMs.

**Examples:**
```
[p]remindme 30m Check the oven
[p]remindme 2h Meeting {time}!
[p]remindme 1d Take medication
```

### remind

**Usage:** `[p]remind [destination] [targets]... <time> [message]`

Create a reminder in a channel with optional pings.

**Examples:**
```
[p]remind #general 1h Event starting soon!
[p]remind #events @Role 30m Get ready!
```

## Managing Reminders

### reminder list

**Usage:** `[p]reminder list ["text"|"command"|"say"] ["expire"|"created"|"id"]`

List your existing reminders.

### reminder edit

**Usage:** `[p]reminder edit <reminder_id>`

Edit an existing reminder.

### reminder remove

**Usage:** `[p]reminder remove <reminder_id>...`

Remove one or more reminders.

### reminder clear

**Usage:** `[p]reminder clear [confirmation]`

Clear all your reminders.

## Modify Reminders

### reminder expires

**Usage:** `[p]reminder expires <reminder_id> <time>`

Change when a reminder will trigger.

### reminder text

**Usage:** `[p]reminder text <reminder_id> <text>`

Change reminder message.

### reminder repeat

**Usage:** `[p]reminder repeat <reminder_id> <interval>`

Make a reminder repeat.

## Special Reminder Types

### reminder fifo

**Usage:** `[p]reminder fifo [destination] <time> <command>`

Schedule a command to execute later.

**Example:**
```
[p]reminder fifo 1h ping
[p]reminder fifo #admin 30m cleanup
```

### reminder say

**Usage:** `[p]reminder say [destination] <time> <text>`

Schedule a message to be sent.

**Example:**
```
[p]reminder say #announcements 1d Vote for the server!
```

## Utility Commands

### reminder timezone

**Usage:** `[p]reminder timezone <timezone>`

Set your personal timezone.

**Example:**
```
[p]reminder timezone Europe/Amsterdam
[p]reminder timezone America/New_York
```

### reminder timestamps

**Usage:** `[p]reminder timestamps [repeat_times] [time]`

Get Discord timestamps for a given time.

### reminder timetips

**Usage:** `[p]reminder timetips`

Show time parsing tips and examples.

## Admin Commands

### setreminders

**Usage:** `[p]setreminders <subcommand>`

Configure server-wide reminder settings.

**Subcommands:**
- `maximumuserreminders <number>` - Set reminder limit per user
- `autodeleteminutesreminders <minutes>` - Auto-delete after N minutes
- `fifoallowed <true|false>` - Allow/deny command reminders
- `repeatallowed <true|false>` - Allow/deny repeating reminders
- `metoo <true|false>` - Show "Me too" button
- `snoozeview <true|false>` - Show snooze buttons
- `showsettings` - View current settings
- `clearuserreminders <user>` - Clear a user's reminders

## Time Format Examples

```
30s    - 30 seconds
5m     - 5 minutes
2h     - 2 hours
1d     - 1 day
1w     - 1 week
3mo    - 3 months
1y     - 1 year
```

Can combine: `1d 2h 30m` = 1 day, 2 hours, 30 minutes

## Using the {time} Variable

Add `{time}` to your reminder message for a live countdown:

```
[p]remindme 1h The event starts {time}!
```

When created, shows: "The event starts in 1 hour!"

[← Back to Overview](Overview) | [Home](../Home)
