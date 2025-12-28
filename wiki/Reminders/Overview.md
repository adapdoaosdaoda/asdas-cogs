# Reminders - Overview

Enhanced reminders cog with time variables, FIFO scheduling, and comprehensive reminder management.

## About This Cog

This is a modified version of the [Reminders cog](https://github.com/AAA3A-AAA3A/AAA3A-cogs/tree/main/reminders) by AAA3A, enhanced with `{time}` variable support for Discord relative timestamps.

## Key Features

- ⏰ **Flexible Reminders** - Create reminders in DMs or channels
- 🔁 **Repeat Support** - Recurring reminders
- 📅 **Time Variables** - Use `{time}` for Discord relative timestamps
- 🤖 **FIFO Commands** - Schedule commands to run later
- 💬 **Say Scheduler** - Schedule messages to be sent
- 👥 **Me Too Feature** - Let others join your reminder
- ⏸️ **Snooze Functionality** - Postpone reminders easily
- 🌍 **Timezone Support** - Personal timezone configuration

## Time Variable Enhancement

The key enhancement in this version is the `{time}` variable:

```
[p]remindme 1h Don't forget the meeting {time}!
```

**Result:** "Don't forget the meeting in 1 hour!" with a live Discord timestamp that counts down.

## Quick Start

### Create a Simple Reminder

```
[p]remindme 30m Check the oven
```

### Create a Reminder with Time Variable

```
[p]remindme 2h Meeting starts {time}!
```

### Create a Channel Reminder

```
[p]remind #general 1d Server maintenance tomorrow!
```

### Schedule a Command (FIFO)

```
[p]reminder fifo 1h ping
```

### Schedule a Message

```
[p]reminder say #announcements 30m Event starting soon!
```

## Reminder Management

- List reminders: `[p]reminder list`
- Edit reminder: `[p]reminder edit <id>`
- Remove reminder: `[p]reminder remove <id>`
- Clear all: `[p]reminder clear`

## Configuration

### Set Your Timezone

```
[p]reminder timezone Europe/Amsterdam
```

### Admin Settings

Server administrators can configure:
- Maximum reminders per user
- Auto-delete timer for reminder messages
- Enable/disable FIFO commands
- Enable/disable repeating reminders
- Me Too button visibility
- Snooze button visibility

See `[p]setreminders` for all admin options.

## For More Information

For comprehensive documentation, see:
- [AAA3A-cogs Documentation](https://aaa3a-cogs.readthedocs.io/en/latest/)
- [AAA3A-cogs Support Server](https://discord.gg/GET4DVk)
- [Commands Reference](Commands-Reference)

[← Back to Home](../Home)
