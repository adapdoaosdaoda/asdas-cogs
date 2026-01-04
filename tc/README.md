# TC (Turnip Calculator)

A Discord cog for Animal Crossing turnip market notifications with customizable scheduled reminders.

## Features

- **Sunday Pre-Shop Restock Notification**: Reminds players to prepare for Daisy Mae's turnip sales
- **Wednesday Sell Recommendation**: Mid-week reminder to check turnip prices
- **Timezone Support**: Configure notifications for any timezone (defaults to Europe/Amsterdam)
- **Customizable Messages**: Fully customize notification messages
- **Role Pinging**: Optional role mentions for notifications
- **Test Command**: Test notifications before scheduling

## Setup

1. Load the cog:
   ```
   [p]load tc
   ```

2. Set the notification channel:
   ```
   [p]tc channel #turnips
   ```

3. Set your timezone (optional, defaults to Europe/Amsterdam):
   ```
   [p]tc timezone Europe/Amsterdam
   ```

4. Enable notifications:
   ```
   [p]tc enable
   ```

## Default Schedule

- **Sunday**: 19:00 (7:00 PM) - Pre-shop restock reminder
- **Wednesday**: 19:00 (7:00 PM) - Sell recommendation reminder

Both notifications are enabled by default but can be individually disabled.

## Commands

### General Commands

- `[p]tc channel <channel>` - Set the channel for notifications
- `[p]tc timezone <timezone>` - Set timezone (e.g., Europe/Amsterdam, America/New_York)
- `[p]tc enable` - Enable turnip notifications
- `[p]tc disable` - Disable turnip notifications
- `[p]tc settings` - Show current settings
- `[p]tc test <sunday|wednesday>` - Test a notification

### Sunday Notification Commands

- `[p]tc sunday enable` - Enable Sunday notifications
- `[p]tc sunday disable` - Disable Sunday notifications
- `[p]tc sunday time <hour> [minute]` - Set notification time (24-hour format)
- `[p]tc sunday message <message>` - Set custom message
- `[p]tc sunday pingrole [role]` - Set role to ping (leave empty to remove)

### Wednesday Notification Commands

- `[p]tc wednesday enable` - Enable Wednesday notifications
- `[p]tc wednesday disable` - Disable Wednesday notifications
- `[p]tc wednesday time <hour> [minute]` - Set notification time (24-hour format)
- `[p]tc wednesday message <message>` - Set custom message
- `[p]tc wednesday pingrole [role]` - Set role to ping (leave empty to remove)

## Examples

### Basic Setup
```
[p]tc channel #turnips
[p]tc timezone Europe/Amsterdam
[p]tc enable
```

### Customize Sunday Notification
```
[p]tc sunday time 19 0
[p]tc sunday message 🔔 Daisy Mae arrives tomorrow! Prepare your bells!
[p]tc sunday pingrole @Turnip Traders
```

### Customize Wednesday Notification
```
[p]tc wednesday time 19 0
[p]tc wednesday message 📈 It's Wednesday! Check if you have good turnip prices!
[p]tc wednesday pingrole @Turnip Traders
```

### Test Notifications
```
[p]tc test sunday
[p]tc test wednesday
```

## How It Works

The cog runs a background task that checks every hour whether it's time to send a notification. When the current day and time match a configured schedule, the notification is sent to the designated channel.

## Permissions

All commands require the "Manage Server" permission or administrator role.

## Default Messages

**Sunday:**
```
🔔 **Turnip Pre-Shop Restock Reminder!**

Daisy Mae will be selling turnips tomorrow morning! Get ready to buy your turnips! 🌱
```

**Wednesday:**
```
📈 **Mid-Week Turnip Check!**

It's Wednesday! Check your turnip prices - this is a good time to sell if you have a good price! 💰
```

## Timezone List

For a list of valid timezones, see: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
