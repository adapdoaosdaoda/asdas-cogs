# Trade Commission Cog

A Discord cog for Where Winds Meet that sends weekly Trade Commission information with interactive reaction-based options.

## Features

- **Weekly Scheduled Messages**: Automatically send Trade Commission updates on a configured day/time
- **Reaction-Based Information**: Add up to 3 pieces of information by clicking reaction emotes
- **Unlimited Options**: Configure as many trade options as you need, select any 3 to display
- **Separate Scheduling**: Post the message early, add information later in the day
- **Timezone Support**: Configure your preferred timezone for accurate scheduling
- **Global Options**: Configure option content once, use across all servers
- **Customizable Emotes**: Each option uses a custom emoji for reactions (unicode or custom Discord emojis)
- **Image Support**: Display an image when Trade Commission information is added
- **Fully Customizable Messages**: Personalize title, descriptions, and ping roles per server
- **Clean Design**: No footer or timestamps for a streamlined appearance

## Installation

1. Load the cog:
   ```
   [p]load tradecommission
   ```

## Setup

### 1. Configure Options (Global)

Set up trade options that can be used across all servers. **You can add unlimited options**, and when using `addinfo`, you can select any 3 to display. These options are global and shared across all servers using this cog:

```
[p]tc setoption 🔥 "Silk Road" This week's trade route is the Silk Road with 20% bonus on silk items.
[p]tc setoption 💎 "Tea Trade" Premium tea trading available with double rewards.
[p]tc setoption ⚔️ "Spice Markets" Special spice market event active this week.
[p]tc setoption 🌊 "Maritime Trade" Oceanic trading routes open this week.
```

**Managing Options:**
- Add/update an option: `[p]tc setoption <emoji> <title> <description>`
- Remove an option: `[p]tc removeoption <title>`
- List all options: `[p]tc listoptions`

**Custom Emojis:**
You can use custom Discord server emojis! Just type them normally:
```
[p]tc setoption :tradeicon: "Silk Road" This week's trade route...
```

**Note:**
- The emoji you choose will be used as the reaction emote in the addinfo command
- If an option with the same title exists, it will be updated instead of creating a duplicate
- Custom emojis must be from your server or a server the bot is in
- Both unicode emojis (🔥) and custom emojis (:custom:) are supported

### 2. Set Image (Optional - Global)

Set an image to display when Trade Commission information is added (bot owner only):

```
[p]tc setimage https://example.com/trade-commission-banner.png
```

The image will only appear when options are selected via `[p]tc addinfo`.

### 3. Schedule Weekly Messages (Per-Server)

Configure when the weekly message should be sent for your server:

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

### 4. Configure Allowed Roles (Optional - Per-Server)

By default, only users with "Manage Server" permission can use addinfo reactions. You can add specific roles that should also have access:

```
[p]tc addrole @Trade Manager
[p]tc addrole @Community Helper
```

Users with these roles will be able to click reactions on the addinfo message to select Trade Commission options.

**View allowed roles:**
```
[p]tc listroles
```

**Remove a role:**
```
[p]tc removerole @Trade Manager
```

### 5. Customize Messages (Optional - Per-Server)

Personalize the Trade Commission messages for your server:

**Set the title/header:**
```
[p]tc settitle 📊 Weekly Trade Routes - Where Winds Meet
```

**Set the initial description (shown before options are added):**
```
[p]tc setinitial This week's trade routes will be announced soon! Check back later for updates.
```

**Set the post description (shown after options are added):**
```
[p]tc setpost This week's Trade Commission routes:
```

**Set a role to ping when posting:**
```
[p]tc setpingrole @Traders
```
The role will be mentioned when the weekly message is posted.

**Remove ping role:**
```
[p]tc setpingrole
```

## Usage

### Automatic Weekly Flow

Once configured, the cog will automatically:
1. Post the weekly message at the scheduled time
2. Wait for you to add information using the `addinfo` command

### Adding Information (Reaction-Based)

After the weekly message is posted (either automatically or manually), use:

```
[p]tc addinfo
```

This creates an interactive message with reaction emotes. **All configured options are shown, and you can click any reactions to select up to 3 options** to add their information to the Trade Commission message.

**How it works:**
1. Bot posts a message with **all** configured option emojis as reactions
2. Click a reaction to add that option to the weekly message
3. Click again to remove it (or remove your reaction)
4. Maximum 3 options can be selected at once (even if you have more options configured)
5. The Trade Commission message updates in real-time
6. Only authorized users can modify selections (users with "Manage Server" permission or configured allowed roles)

**Note:** You can have unlimited options configured, but only 3 can be selected at a time for the weekly message.

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
| `[p]tc addinfo` | Add information via reaction emotes | Admin |
| `[p]tc setoption <emoji> <title> <description>` | Add/update an option (global) | Admin/Owner |
| `[p]tc removeoption <title>` | Remove an option (global) | Admin/Owner |
| `[p]tc listoptions` | List all configured options (global) | Anyone |
| `[p]tc setimage <url>` | Set image to display with information (global) | Owner |
| `[p]tc addrole <role>` | Add role that can use addinfo reactions | Admin |
| `[p]tc removerole <role>` | Remove role from addinfo allowed list | Admin |
| `[p]tc listroles` | List roles allowed to use addinfo | Admin |
| `[p]tc settitle <title>` | Set message title/header | Admin |
| `[p]tc setinitial <description>` | Set initial description (before addinfo) | Admin |
| `[p]tc setpost <description>` | Set post description (after addinfo) | Admin |
| `[p]tc setpingrole [role]` | Set role to ping when posting | Admin |
| `[p]tc info` | View current configuration | Admin |
| `[p]tc enable` | Enable weekly messages | Admin |
| `[p]tc disable` | Disable weekly messages | Admin |
| `[p]tc testnow` | [Owner only] Test send immediately | Owner |

## Example Workflow

**Initial Setup (One-time):**
```
[p]tc setoption 🔥 "Silk Road" This week's trade route is the Silk Road.
[p]tc setoption 💎 "Tea Trade" Premium tea trading available.
[p]tc setoption ⚔️ "Spice Markets" Special spice market event active.
[p]tc setoption 🌊 "Maritime Route" Oceanic trading routes open.
[p]tc setoption 🏔️ "Mountain Pass" New mountain trading paths discovered.
```

**Weekly Cycle:**

1. **Monday 9:00 AM**: Bot automatically posts the weekly Trade Commission message
   - Message shows "Information will be added soon"

2. **Monday 3:00 PM**: Admin runs `[p]tc addinfo`
   - Bot posts a control message with **all 5** reaction emojis (🔥💎⚔️🌊🏔️)

3. **Admin selects this week's routes**: Clicks on 🔥, 🌊, and 🏔️ emotes
   - Trade Commission message updates immediately with the 3 selected routes
   - Configured image appears on the message
   - Players can now see this week's active trade routes

4. **Next Monday**: Process repeats automatically
   - Admin can choose any different 3 options from the available 5

## Configuration Types

### Global Configuration
These settings are shared across **all servers** using the cog:
- **Unlimited trade options** (emoji, title, description) - managed via:
  - `[p]tc setoption` - Add or update an option
  - `[p]tc removeoption` - Remove an option
  - `[p]tc listoptions` - View all options
- Image URL - set via `[p]tc setimage`

### Per-Server Configuration
These settings are unique to each server:
- Schedule (day, time, timezone, channel) - set via `[p]tc schedule`
- Allowed roles for addinfo reactions - set via `[p]tc addrole`
- Message customization (title, descriptions, ping role) - set via `[p]tc settitle`, `[p]tc setinitial`, `[p]tc setpost`, `[p]tc setpingrole`
- Current message tracking
- Active option selections (up to 3 from the global option pool)

This design allows you to configure unlimited Trade Commission options once and use them across multiple Where Winds Meet community servers. Each server can select any 3 options each week, while maintaining its own posting schedule, role permissions, and customized messaging.

## Permissions

### Bot Permissions
The bot needs:
- `Send Messages` in the configured channel
- `Embed Links` to send rich embeds
- `Read Message History` to update messages
- `Add Reactions` to add reaction emojis
- `Manage Messages` to remove invalid reactions

### User Permissions
**For commands** (`[p]tc schedule`, `[p]tc setoption`, etc.):
- `Manage Server` permission required (or admin role)

**For addinfo reactions** (clicking reactions to select options):
- `Manage Server` permission OR
- One of the roles configured via `[p]tc addrole`

This allows you to give specific roles (like "Trade Manager" or "Community Helper") the ability to update Trade Commission information without needing full server management permissions.

## Troubleshooting

**Reactions not working?**
- Make sure the bot has `Add Reactions` permission
- Ensure you have `Manage Server` permission
- Verify you're reacting to the correct message from `[p]tc addinfo`

**Options not updating?**
- Global options (`[p]tc setoption`) affect all servers
- Use `[p]tc info` to verify your configuration
- Try running `[p]tc addinfo` again to create a fresh control message

## Support

For issues or questions about this cog, please contact the server administrators.
