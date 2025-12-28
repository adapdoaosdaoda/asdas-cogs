# EventChannels - Commands Reference

Complete reference of all Event Channels commands. All commands require **Manage Server** permission unless noted.

## Command Structure

All commands are subcommands of `[p]eventchannels`:

```
[p]eventchannels <subcommand> [arguments]
```

---

## Configuration Commands

### setcategory

**Usage:** `[p]eventchannels setcategory <category>`

Set the Discord category where event channels will be created.

**Example:**
```
[p]eventchannels setcategory Events
[p]eventchannels setcategory 123456789012345678
```

### settimezone

**Usage:** `[p]eventchannels settimezone <timezone>`

Configure the timezone for matching event roles.

**Example:**
```
[p]eventchannels settimezone Europe/Amsterdam
[p]eventchannels settimezone America/New_York
```

### setcreationtime

**Usage:** `[p]eventchannels setcreationtime <minutes>`

Set when channels are created before event start (max: 1440 minutes/24 hours).

**Example:**
```
[p]eventchannels setcreationtime 30
```

### setdeletion

**Usage:** `[p]eventchannels setdeletion <hours>`

Set when channels are deleted after event start.

**Example:**
```
[p]eventchannels setdeletion 6
```

### setroleformat

**Usage:** `[p]eventchannels setroleformat <format>`

Customize the pattern for matching event roles.

**Placeholders:** `{name}`, `{day_abbrev}`, `{day}`, `{month_abbrev}`, `{time}`

**Example:**
```
[p]eventchannels setroleformat {name} {day_abbrev} {day}. {month_abbrev} {time}
```

### setchannelformat

**Usage:** `[p]eventchannels setchannelformat <format>`

Customize channel name pattern. **Also renames existing event channels.**

**Placeholders:** `{name}`, `{type}`

**Example:**
```
[p]eventchannels setchannelformat {name}-{type}
[p]eventchannels setchannelformat event-{name}-{type}
```

### setannouncement

**Usage:** `[p]eventchannels setannouncement <message|none>`

Set announcement message posted in event channels.

**Placeholders:** `{role}`, `{event}`, `{time}`

**Example:**
```
[p]eventchannels setannouncement {role} {event} starts {time}!
[p]eventchannels setannouncement none
```

### setstartmessage

**Usage:** `[p]eventchannels setstartmessage <message|none>`

Set message posted when event starts.

**Placeholders:** `{role}`, `{event}`

**Example:**
```
[p]eventchannels setstartmessage {role} The event is starting now!
```

### setdeletionwarning

**Usage:** `[p]eventchannels setdeletionwarning <message|none>`

Set warning message before channel deletion (15 min before cleanup).

**Example:**
```
[p]eventchannels setdeletionwarning ⚠️ Channels closing in 15 minutes!
```

### setchannelnamelimit

**Usage:** `[p]eventchannels setchannelnamelimit <limit>`

Set maximum character limit for channel names (number or character).

**Example:**
```
[p]eventchannels setchannelnamelimit 50
[p]eventchannels setchannelnamelimit ﹕
```

---

## Voice Multiplier Commands

### setvoicemultiplier

**Usage:** `[p]eventchannels setvoicemultiplier <keyword> <multiplier>`

Create multiple voice channels based on role member count.

**Parameters:**
- `keyword` - Trigger word in event name (case-insensitive)
- `multiplier` - Channel capacity minus 1 (1-99)

**Example:**
```
[p]eventchannels setvoicemultiplier hero 9
[p]eventchannels setvoicemultiplier pvp 4
```

See [Voice Multipliers](Voice-Multipliers) for detailed guide.

### listvoicemultipliers

**Usage:** `[p]eventchannels listvoicemultipliers`

List all configured voice multipliers.

### removevoicemultiplier

**Usage:** `[p]eventchannels removevoicemultiplier <keyword>`

Remove a specific voice multiplier.

**Example:**
```
[p]eventchannels removevoicemultiplier hero
```

### disablevoicemultiplier

**Usage:** `[p]eventchannels disablevoicemultiplier`

Disable all voice multipliers.

---

## Minimum Roles Commands

### setminimumroles

**Usage:** `[p]eventchannels setminimumroles <keyword> <minimum>`

Set minimum role members required for channel creation.

**Parameters:**
- `keyword` - Keyword to enforce minimum on (case-insensitive)
- `minimum` - Minimum members required (1-999)

**Example:**
```
[p]eventchannels setminimumroles hero 10
[p]eventchannels setminimumroles raid 5
```

See [Minimum Roles Enforcement](Minimum-Roles-Enforcement) for detailed guide.

### listminimumroles

**Usage:** `[p]eventchannels listminimumroles`

List all configured minimum role requirements.

### removeminimumroles

**Usage:** `[p]eventchannels removeminimumroles <keyword>`

Remove minimum role requirement for a keyword.

**Example:**
```
[p]eventchannels removeminimumroles hero
```

---

## Divider Channel Commands

### setdivider

**Usage:** `[p]eventchannels setdivider <true|false> [name]`

Enable/disable divider channel and optionally set custom name. **Renames existing divider if name provided.**

**Example:**
```
[p]eventchannels setdivider true
[p]eventchannels setdivider true ━━━━━━ MY EVENTS ━━━━━━
[p]eventchannels setdivider false
```

---

## Information Commands

### viewsettings

**Usage:** `[p]eventchannels viewsettings`

Display all current configuration settings.

### eventchannels

**Usage:** `[p]eventchannels`

**Permission:** None (available to all users)

Display all EventChannels commands with explanations.

---

## Testing Commands

### testchannellock

**Usage:** `[p]eventchannels testchannellock`

Test channel locking permissions.

### stresstest

**Usage:** `[p]eventchannels stresstest`

Comprehensive stress test of all features.

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `setcategory` | Set event channel category |
| `settimezone` | Configure server timezone |
| `setroleformat` | Set role name pattern |
| `setchannelformat` | Set channel name pattern |
| `setvoicemultiplier` | Enable dynamic voice scaling |
| `setminimumroles` | Enforce minimum attendance |
| `setdivider` | Enable/disable divider channel |
| `viewsettings` | View current configuration |

[← Back to Overview](Overview) | [Home](../Home)
