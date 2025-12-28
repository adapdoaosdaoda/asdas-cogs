# asdas-cogs

A collection of custom cogs for Red-Discord bot, featuring automated event management, role handling, and enhanced reminders.

## 🚀 Quick Start

### Installation

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
[p]cog install asdas-cogs eventchannels
[p]cog install asdas-cogs eventrolereadd
[p]cog install asdas-cogs reminders
[p]load eventchannels
[p]load eventrolereadd
[p]load reminders
```

**See the [Installation Guide](wiki/Installation.md) for detailed instructions.**

## 📦 Available Cogs

### [EventChannels](wiki/EventChannels/Overview.md)
Automatically creates and manages temporary channels for Discord scheduled events.

**Key Features:**
- Automatic channel creation before events
- Dynamic voice channel scaling based on attendance
- Minimum role enforcement with retry mechanism
- Customizable channel names and formats
- Automatic cleanup after events

### [EventRoleReadd](wiki/EventRoleReadd/Overview.md)
Automatically re-adds event roles based on log channel messages.

**Key Features:**
- Keyword-based role management
- Raid-helper integration
- Instant role restoration

### [Reminders](wiki/Reminders/Overview.md)
Enhanced reminders with time variables and FIFO scheduling.

**Key Features:**
- Discord relative timestamp support (`{time}` variable)
- FIFO command scheduling
- Recurring reminders
- Snooze and "Me Too" functionality


## 📚 Documentation

**Complete documentation is available in the [Wiki](wiki/Home.md):**

- **[Installation Guide](wiki/Installation.md)** - Get started
- **[EventChannels Wiki](wiki/EventChannels/Overview.md)** - Complete guide with examples
- **[EventRoleReadd Wiki](wiki/EventRoleReadd/Overview.md)** - Setup and commands
- **[Reminders Wiki](wiki/Reminders/Overview.md)** - Features and usage


## 🔗 Links

- **[GitHub Repository](https://github.com/adapdoaosdaoda/asdas-cogs)**
- **[Report Issues](https://github.com/adapdoaosdaoda/asdas-cogs/issues)**
- **[Red-Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot)**
- **[AAA3A-cogs repository](https://github.com/AAA3A-AAA3A/AAA3A-cogs)**

## 💬 Support

For help, questions, or feature requests:
- **Read the [Wiki](wiki/Home.md)**
- **Check [Troubleshooting](wiki/EventChannels/Troubleshooting.md)**
- **[Open an issue](https://github.com/adapdoaosdaoda/asdas-cogs/issues)**

For Reminders-specific questions, see the [AAA3A-cogs repository](https://github.com/AAA3A-AAA3A/AAA3A-cogs).

## 📝 Credits

- **EventChannels** - Custom development for Red-Discord Bot
- **EventRoleReadd** - Custom development for Red-Discord Bot
- **Reminders** - Cloned from [AAA3A's Reminders cog](https://github.com/AAA3A-AAA3A/AAA3A-cogs), enhanced with `{time}` variable support
- **Claude** - AI assistance in development and documentation

## 📄 License

Unless otherwise stated, do whatever you want with this code.

- **Reminders** - Cloned from [AAA3A-cogs](https://github.com/AAA3A-AAA3A/AAA3A-cogs), [MIT License](https://github.com/AAA3A-AAA3A/AAA3A-cogs/blob/main/LICENSE)
