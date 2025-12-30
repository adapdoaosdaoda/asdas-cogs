# Trade Commission Cog

A Discord cog for Where Winds Meet that sends weekly Trade Commission information with interactive options.

## Features

- **Weekly Scheduled Messages**: Automatically send Trade Commission updates on a configured day/time
- **Interactive Information**: Add up to 3 pieces of information via clickable buttons
- **Separate Scheduling**: Post the message early, add information later in the day
- **Timezone Support**: Configure your preferred timezone for accurate scheduling
- **Customizable Options**: Configure titles and descriptions for each option

## Installation

1. Load the cog:
   ```
   [p]load tradecommission
   ```

## Setup

### 1. Configure Options

First, set up the information for each of the 3 available options:

```
[p]tc setoption 1 "Silk Road" This week's trade route is the Silk Road with 20% bonus on silk items.
[p]tc setoption 2 "Tea Trade" Premium tea trading available with double rewards.
[p]tc setoption 3 "Spice Markets" Special spice market event active this week.
```

### 2. Schedule Weekly Messages

Configure when the weekly message should be sent:

```
[p]tc schedule #trade-info Monday 9 0 America/New_York
```

This will send a message to `#trade-info` every Monday at 9:00 AM Eastern Time.

**Arguments:**
- `channel`: The channel to post to
- `day`: Day of week (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday)
- `hour`: Hour in 24-hour format (0-23)
- `minute`: Minute (0-59)
- `timezone`: Timezone (e.g., UTC, America/New_York, Europe/London)

## Usage

### Automatic Weekly Flow

Once configured, the cog will automatically:
1. Post the weekly message at the scheduled time
2. Wait for you to add information using the `addinfo` command

### Adding Information

After the weekly message is posted (either automatically or manually), use:

```
[p]tc addinfo
```

This creates an interactive panel with buttons for each option. Click up to 3 buttons to add their information to the Trade Commission message.

**Features:**
- Click a button to add that option's information
- Click again to remove it
- Maximum 3 options can be selected
- The Trade Commission message updates in real-time
- Buttons change color when selected (green = active, blue = inactive)

### Manual Posting

To manually post a Trade Commission message:

```
[p]tc post
```

Or specify a different channel:

```
[p]tc post #announcements
```

### View Configuration

Check your current settings:

```
[p]tc info
```

### Enable/Disable

Temporarily disable automatic messages:

```
[p]tc disable
```

Re-enable:

```
[p]tc enable
```

## Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `[p]tc schedule <channel> <day> <hour> [minute] [timezone]` | Schedule weekly messages | Admin |
| `[p]tc post [channel]` | Manually post a message now | Admin |
| `[p]tc addinfo` | Add information via interactive buttons | Admin |
| `[p]tc setoption <num> <title> <description>` | Configure an option | Admin |
| `[p]tc info` | View current configuration | Admin |
| `[p]tc enable` | Enable weekly messages | Admin |
| `[p]tc disable` | Disable weekly messages | Admin |
| `[p]tc testnow` | [Owner only] Test send immediately | Owner |

## Example Workflow

1. **Monday 9:00 AM**: Bot automatically posts the weekly Trade Commission message
   - Message shows "Information will be added soon"

2. **Monday 3:00 PM**: Admin runs `[p]tc addinfo`
   - Interactive panel appears with 3 buttons

3. **Admin clicks buttons**: Selects options 1 and 3
   - Trade Commission message updates immediately with selected information
   - Players can now see the week's trade routes

4. **Next Monday**: Process repeats automatically

## Permissions

The bot needs:
- `Send Messages` in the configured channel
- `Embed Links` to send rich embeds
- `Read Message History` to update messages

Users need:
- `Manage Server` permission to use Trade Commission commands

## Support

For issues or questions about this cog, please contact the server administrators.
