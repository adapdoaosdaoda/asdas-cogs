# EventChannels - Getting Started

This guide will walk you through the basic setup of EventChannels to get your first event channels working.

## Quick Setup (5 Minutes)

### Step 1: Set the Event Category

Choose or create a category where event channels will be created:

```
[p]eventchannels setcategory Events
```

You can also use a category ID:

```
[p]eventchannels setcategory 123456789012345678
```

### Step 2: Configure Your Timezone

Set your server's timezone for proper role matching:

```
[p]eventchannels settimezone Europe/Amsterdam
```

Common timezones:
- `America/New_York`
- `America/Los_Angeles`
- `Europe/London`
- `Europe/Amsterdam`
- `Asia/Tokyo`
- `Australia/Sydney`

### Step 3: Set Role Format

Configure how the bot matches event roles (usually created by Raid-Helper):

```
[p]eventchannels setroleformat {name} {day_abbrev} {day}. {month_abbrev} {time}
```

**Example role name:** `Raid Night Wed 25. Dec 21:00`

Available placeholders:
- `{name}` - Event name
- `{day_abbrev}` - Day abbreviation (Mon, Tue, Wed, etc.)
- `{day}` - Day number (1-31)
- `{month_abbrev}` - Month abbreviation (Jan, Feb, etc.)
- `{time}` - Time in HH:MM format

### Step 4: Verify Settings

Check that everything is configured correctly:

```
[p]eventchannels viewsettings
```

### Step 5: Create a Test Event

1. Create a Discord scheduled event in your server
2. Make sure it has a matching role (following your role format)
3. Wait for the creation time (default: 15 minutes before event start)
4. Channels should be created automatically!

## Basic Configuration

### Adjust Creation Time

Change when channels are created before the event starts:

```
[p]eventchannels setcreationtime 30
```

This sets creation to 30 minutes before the event.

### Adjust Deletion Time

Change when channels are deleted after the event starts:

```
[p]eventchannels setdeletion 6
```

This sets deletion to 6 hours after the event starts.

### Customize Channel Names

Change the format of created channel names:

```
[p]eventchannels setchannelformat {name}-{type}
```

**Examples:**
- `{name}᲼{type}` → `raid-night᲼text` (default)
- `{name}-{type}` → `raid-night-text`
- `event-{name}` → `event-raid-night`

## Adding Announcements

### Set Announcement Message

Configure the message posted when channels are created:

```
[p]eventchannels setannouncement {role} The event is starting soon!
```

**Available placeholders:**
- `{role}` - Mentions the event role
- `{event}` - Event name
- `{time}` - Relative time (e.g., "in 15 minutes")

### Set Event Start Message

Configure the message posted when the event actually starts:

```
[p]eventchannels setstartmessage {role} The event is starting now!
```

### Set Deletion Warning

Configure the warning message before channels are deleted:

```
[p]eventchannels setdeletionwarning ⚠️ These channels will be deleted in 15 minutes.
```

## Testing Your Setup

### Test Channel Lock

Verify the bot can lock channels before deletion:

```
[p]eventchannels testchannellock
```

### Full Stress Test

Run a comprehensive test of all features:

```
[p]eventchannels stresstest
```

This will create temporary test channels and verify all functionality.

## Common First-Time Issues

### ❌ Channels Not Being Created

**Check these:**
- Is the event category set? (`[p]eventchannels viewsettings`)
- Does the bot have "Manage Channels" permission?
- Is the event scheduled in the future?
- Does the event have a matching role?

### ❌ Role Not Found

**Check these:**
- Does your role format match Raid-Helper's format?
- Is the timezone configured correctly?
- Use `[p]eventchannels viewsettings` to verify the role format

### ❌ Permission Errors

**Check these:**
- Bot needs "Manage Channels" in the category
- Bot needs "Manage Roles" at server level
- Bot needs "View Channels" permission

## What's Next?

Now that you have the basics working, explore advanced features:

- [🔊 Voice Multipliers](Voice-Multipliers) - Create multiple voice channels based on attendance
- [👥 Minimum Roles Enforcement](Minimum-Roles-Enforcement) - Prevent events with low signup
- [🎨 Channel Customization](Channel-Customization) - Advanced name formatting and limits
- [💡 Configuration Examples](Configuration-Examples) - Real-world setup examples

[← Back to Overview](Overview) | [Home](../Home)
