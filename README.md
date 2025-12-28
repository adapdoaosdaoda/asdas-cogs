# asdas-cogs

A collection of custom cogs for Red-Discord bot, featuring automated event management, role handling, and enhanced reminders.

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

## 🚀 Quick Start

### Installation

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
[p]cog install asdas-cogs eventchannels
[p]load eventchannels
```

**See the [Installation Guide](wiki/Installation.md) for detailed instructions.**

## 📚 Documentation

**Complete documentation is available in the [Wiki](wiki/Home.md):**

- **[Installation Guide](wiki/Installation.md)** - Get started
- **[EventChannels Wiki](wiki/EventChannels/Overview.md)** - Complete guide with examples
- **[EventRoleReadd Wiki](wiki/EventRoleReadd/Overview.md)** - Setup and commands
- **[Reminders Wiki](wiki/Reminders/Overview.md)** - Features and usage

## ⚡ Quick Examples

### EventChannels: Auto-create channels for 10-man raids

```
[p]eventchannels setcategory Events
[p]eventchannels settimezone Europe/Amsterdam
[p]eventchannels setvoicemultiplier raid 9
[p]eventchannels setminimumroles raid 8
```

**[See more examples →](wiki/EventChannels/Configuration-Examples.md)**

### EventRoleReadd: Monitor raid-helper logs

```
[p]rolereadd setchannel #raid-helper-logs
[p]rolereadd addkeyword signed up
```

**[See setup guide →](wiki/EventRoleReadd/Commands-Reference.md)**

### Reminders: Create reminder with countdown

```
[p]remindme 1h Don't forget the meeting {time}!
```

**[See more features →](wiki/Reminders/Overview.md)**

## 🔗 Links

- **[GitHub Repository](https://github.com/adapdoaosdaoda/asdas-cogs)**
- **[Report Issues](https://github.com/adapdoaosdaoda/asdas-cogs/issues)**
- **[Red-Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot)**

## 💬 Support

For help, questions, or feature requests:
- **Read the [Wiki](wiki/Home.md)**
- **Check [Troubleshooting](wiki/EventChannels/Troubleshooting.md)**
- **[Open an issue](https://github.com/adapdoaosdaoda/asdas-cogs/issues)**

For Reminders-specific questions, see the [AAA3A-cogs repository](https://github.com/AAA3A-AAA3A/AAA3A-cogs).

## 📝 Credits

- **EventChannels** - Custom development for Red-Discord Bot
- **EventRoleReadd** - Custom development for Red-Discord Bot
- **Reminders** - Based on [AAA3A's Reminders cog](https://github.com/AAA3A-AAA3A/AAA3A-cogs), enhanced with `{time}` variable support

## 📄 License

See individual cog directories for license information.
