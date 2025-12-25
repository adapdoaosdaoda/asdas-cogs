# readme

This cog auto makes text and voice channels 15 minutes before, or immediately within the 15 minutes, an discord event starts.  
It was made to compliment [Raid-Helper](https://raid-helper.dev/) (premium), which allows automatic event + matching role creation, but not automatic text channel creation nor automatic voice channel creation when using its web dashboard (automatic voice channels do work with manual text creation, but these are created instantly, not around event start).

The cog also automatically deletes the channels 4 hours (changeable) after the event start time, and if it has the perms, the role that raid-helper creates.

## Instalation 

`[p]repo add asdasd-cogs https://github.com/adapdoaosdaoda/asdasd-cogs`  
`[p]cog install asdasd-cogs RaidHelperEventThing`

---

## Bot Permissions

The bot requires the following permissions

### Server-Level Permissions
- **Manage Channels** - Required to create and delete text/voice channels
- **Manage Roles** - Required to delete event roles after cleanup
- **View Channels** - Required to access and manage the category

### Category Permissions (if using a specific category)
- **Manage Channels** - Required to create channels within the category
- **Manage Permissions** - Required to set channel permissions/overwrites

---

## Commands Overview

| Command | Description |
|---------|-------------|
| `[p]seteventcategory` | Set the category for event channels |
| `[p]seteventtimezone` | Configure server timezone |
| `[p]seteventdeletion` | Set channel deletion time |
| `[p]seteventroleformat` | Customize role name pattern |
| `[p]vieweventsettings` | Display current settings |
| `[p]listeventchannels` | List active event channels |
| `[p]testeventrole` | Test role name generation |
| `[p]cleanupevent` | Manually cleanup event channels |

## Setup Commands

### `seteventcategory <category>`
**Category:** Configuration  
**Permission:** Manage Server or Administrator

Sets the Discord category where event text and voice channels will be automatically created. The bot will place all event-related channels in this category for better organization.

**Example:** `[p]seteventcategory Events`

---

### `seteventtimezone <timezone>`
**Category:** Configuration  
**Permission:** Manage Server or Administrator

Configures the timezone used for matching event roles. This ensures the bot generates role names with the correct local time for your server. Uses standard timezone identifiers like `Europe/Amsterdam`, `America/New_York`, or `Asia/Tokyo`.

**Example:** `[p]seteventtimezone Europe/Amsterdam`

---

### `seteventdeletion <hours>`
**Category:** Configuration  
**Permission:** Manage Server or Administrator

Sets how many hours after an event starts before the bot automatically deletes the event channels and role. Default is 4 hours. This gives participants time to wrap up after the event ends.

**Example:** `[p]seteventdeletion 6`

---

### `seteventroleformat <format>`
**Category:** Configuration  
**Permission:** Manage Server or Administrator

Customizes the pattern used to match event roles. The bot looks for roles matching this format to determine which events to create channels for. Use placeholders like `{name}`, `{day_abbrev}`, `{day}`, `{month_abbrev}`, and `{time}` to build your pattern.

**Example:** `[p]seteventroleformat {name} {day_abbrev} {day}. {month_abbrev} {time}`  
**Result:** `Raid Night Wed 25. Dec 21:00`

---

### `vieweventsettings`
**Category:** Information  
**Permission:** Manage Server or Administrator

Displays all current configuration settings in an organized embed, including the category, timezone, deletion time, and role format. Use this to verify your setup is correct.

**Example:** `[p]vieweventsettings`

---

### `listeventchannels`
**Category:** Information  
**Permission:** Manage Server or Administrator

Shows all currently active event channels being managed by the bot. Displays the event ID, text channel, voice channel, and associated role for each active event. Helpful for monitoring and troubleshooting.

**Example:** `[p]listeventchannels`

---

### `testeventrole <event_id>`
**Category:** Information  
**Permission:** Manage Server or Administrator

Tests what role name the bot would generate for a specific Discord scheduled event. Shows the event details, expected role name, and whether the role currently exists. Essential for debugging role matching issues before an event starts.

**Example:** `[p]testeventrole 1234567890123456789`

---

### `cleanupevent <event_id>`
**Category:** Management  
**Permission:** Manage Server or Administrator

Manually triggers cleanup for a specific event, immediately deleting its text channel, voice channel, and associated role. Useful if you need to clean up early or if automatic cleanup failed. Cancels any pending automatic cleanup tasks.

**Example:** `[p]cleanupevent 1234567890`
