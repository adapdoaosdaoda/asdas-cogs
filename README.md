# asdas-cogs

A collection of custom cogs for Red-Discord bot, featuring automated event management, role handling, and enhanced reminders.

## 🚀 Quick Start

### Installation

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
```
```
[p]cog install asdas-cogs eventchannels
[p]cog install asdas-cogs eventrolereadd
[p]cog install asdas-cogs reminders
[p]cog install asdas-cogs tradecommission
```
```
[p]load eventchannels
[p]load eventrolereadd
[p]load reminders
[p]load tradecommission
```

## 📦 Available Cogs

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
- **EventChannels** - Custom development for Red-Discord Bot
- **EventRoleReadd** - Custom development for Red-Discord Bot
- **Reminders** - Cloned from [AAA3A's Reminders cog](https://github.com/AAA3A-AAA3A/AAA3A-cogs), enhanced with `{time}` variable support
- **TradeCommission** - Custom development for Red-Discord Bot

## 📄 License
- **Reminders** - Cloned from [AAA3A-cogs](https://github.com/AAA3A-AAA3A/AAA3A-cogs), [MIT License](https://github.com/AAA3A-AAA3A/AAA3A-cogs/blob/main/LICENSE)

Unless otherwise stated, do whatever you want.
