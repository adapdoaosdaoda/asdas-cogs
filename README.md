# asdas-cogs

A collection of custom cogs for Red-Discord bot, featuring automated event management, role handling, and enhanced reminders.

## 🚀 Quick Start

### Installation

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
```
```
[p]cog install asdas-cogs birthday
[p]cog install asdas-cogs borkedsince
[p]cog install asdas-cogs eventchannels
[p]cog install asdas-cogs eventrolereadd
[p]cog install asdas-cogs forumthreadmessage
[p]cog install asdas-cogs reminders
[p]cog install asdas-cogs tradecommission
```
```
[p]load birthday
[p]load borkedsince
[p]load eventchannels
[p]load eventrolereadd
[p]load forumthreadmessage
[p]load reminders
[p]load tradecommission
```

## 📦 Available Cogs

### Birthday
[Vexed01's](https://github.com/Vexed01/Vex-Cogs) birthday cog with some added junk.

**Added Features:**
- Added the ability to upload and include an image to the birthday announcement messages
- Increased the role requirerment from 1 to 2
- Added the ability to limit the set subcommand to a single channel
- Automatic emote reaction to the announcement

### BorkedSince
Track and display days since your bot last crashed in the bot's About Me section.

**Key Features:**
- Automatic crash detection (distinguishes between crashes and intentional restarts)
- Generates formatted "Last borked: X days ago" text for bot's About Me
- Crash history tracking with longest streak highscores
- Bio length validation for 10.000+ day counts
- Uses period (.) as thousand separator (e.g., "10.000 days")
- Manual reset command for after bug fixes
- All-time statistics and recent crash reports

**Note:** Discord bots cannot programmatically update their About Me section. The cog will show you what your bio should be, but you'll need to manually update it in the Discord Developer Portal.

### EventChannels
Automatically creates and manages temporary channels for Discord scheduled events, created with [Raid-Helper](https://raid-helper.dev/) in mind.

**Key Features:**
- Automatic channel creation before events
- Dynamic voice channel scaling based on attendance
- Minimum role enforcement with retry mechanism
- Customizable channel names and formats
- Automatic cleanup after events

### EventRoleReadd
Extension to EventChannels that automatically re-adds event roles based on log channel messages.

**Key Features:**
- Keyword-based role management
- Intended to be used with [Raid-helper](https://raid-helper.dev/)
- Instant role restoration

### ForumThreadMessage
Automatically send, edit, and optionally delete messages in new forum threads.

**Key Features:**
- Monitors configured forum channels for new threads
- Automatically sends a message when a thread is created
- Edits the message after 2 seconds
- Optionally deletes the message after another 2 seconds
- Fully configurable message content
- Silent message sending (no notifications)

### Reminders
[AAA3A's](https://github.com/AAA3A-AAA3A/AAA3A-cogs) reminders with added time variable.

**Added Features:**
- Discord relative timestamp support (`{time}` variable)

### TradeCommission
A Discord cog for Where Winds Meet that sends weekly Trade Commission information with interactive options.

**Key Features:**
- Weekly scheduled messages with timezone support
- Dropdown based information selection (up to 3 options)
- Unlimited configurable trade options
- Customizable emotes and messages
- Image support for Trade Commission updates
- Role-based access control
- **Scheduled notifications:**
  - Sunday pre-shop restock notification (customizable time and message)
  - Wednesday sell recommendation notification (customizable time and message)
  - Independent timezone support for all notifications
  - Optional role pinging for notifications


## 📚 Documentation

**Complete documentation is available in the [Wiki](https://github.com/adapdoaosdaoda/asdas-cogs/wiki):**

- **[Installation Guide](https://github.com/adapdoaosdaoda/asdas-cogs/wiki#-installation)** - Get started
- **[EventChannels Wiki](https://github.com/adapdoaosdaoda/asdas-cogs/wiki/EventChannels)** - Complete guide with examples
- **[EventRoleReadd Wiki](https://github.com/adapdoaosdaoda/asdas-cogs/wiki/EventRoleReadd)** - Setup and commands
- **[Reminders Wiki](https://github.com/adapdoaosdaoda/asdas-cogs/wiki/Reminders)** - Features and usage
- **[TradeCommission Wiki](https://github.com/adapdoaosdaoda/asdas-cogs/wiki/TradeCommission)** - Setup and commands


## 🔗 Links

- **[GitHub Repository](https://github.com/adapdoaosdaoda/asdas-cogs)**
- **[Report Issues](https://github.com/adapdoaosdaoda/asdas-cogs/issues)**
- **[Red-Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot)**
- **[AAA3A-cogs repository](https://github.com/AAA3A-AAA3A/AAA3A-cogs)**

## 💬 Support

For help, questions, or feature requests:
- **Read the [Wiki](https://github.com/adapdoaosdaoda/asdas-cogs/wiki)**
- **Check [Troubleshooting](https://github.com/adapdoaosdaoda/asdas-cogs/wiki/EventChannels-Troubleshooting)**
- **[Open an issue](https://github.com/adapdoaosdaoda/asdas-cogs/issues)**

For Reminders-specific questions, see the [AAA3A-cogs repository](https://github.com/AAA3A-AAA3A/AAA3A-cogs).

## 📝 Credits

- **Claude** - Everything 🎉🎊
- **Birthday** - Cloned from [Vexed01's Birthday cog](https://github.com/Vexed01/Vex-Cogs), added image upload to announcements, multi-role inclusion, and something else i forgot
- **BorkedSince** - Custom development for Red-Discord Bot
- **EventChannels** - Custom development for Red-Discord Bot
- **EventRoleReadd** - Custom development for Red-Discord Bot
- **ForumThreadMessage** - Custom development for Red-Discord Bot
- **Reminders** - Cloned from [AAA3A's Reminders cog](https://github.com/AAA3A-AAA3A/AAA3A-cogs), enhanced with `{time}` variable support
- **TradeCommission** - Custom development for Red-Discord Bot

## 📄 License
- **Birthday** - Identical to original from [Vex-cogs](https://github.com/Vexed01/Vex-Cogs), [GNU General Public License v3.0](https://github.com/Vexed01/Vex-Cogs/blob/master/LICENSE)
- **Reminders** - Identical to original from [AAA3A-cogs](https://github.com/AAA3A-AAA3A/AAA3A-cogs), [MIT License](https://github.com/AAA3A-AAA3A/AAA3A-cogs/blob/main/LICENSE)

Unless otherwise stated, do whatever you want.
