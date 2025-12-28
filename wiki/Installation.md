# Installation Guide

This guide will help you install and set up the asdas-cogs collection for your Red-Discord bot.

## Requirements

- **Red-Discord Bot** v3.5.0 or higher
- **Python** 3.8+
- Required bot permissions (see individual cog documentation)

## Installation Steps

### 1. Add the Repository

Add this repository to your Red-Discord bot:

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
```

### 2. Install Cogs

Install the cogs you want to use:

```
[p]cog install asdas-cogs eventchannels
[p]cog install asdas-cogs eventrolereadd
[p]cog install asdas-cogs reminders
```

### 3. Load the Cogs

Load the installed cogs:

```
[p]load eventchannels
[p]load eventrolereadd
[p]load reminders
```

### 4. Verify Installation

Check that the cogs are loaded successfully:

```
[p]cogs
```

You should see the installed cogs in the list.

## Next Steps

- **EventChannels**: See the [Getting Started Guide](EventChannels/Getting-Started)
- **EventRoleReadd**: See the [Overview](EventRoleReadd/Overview)
- **Reminders**: See the [Overview](Reminders/Overview)

## Updating Cogs

To update to the latest version:

```
[p]repo update asdas-cogs
[p]cog update eventchannels eventrolereadd reminders
```

Then reload the cogs:

```
[p]reload eventchannels eventrolereadd reminders
```

## Troubleshooting Installation

### Repository Not Found

If you get an error adding the repository:
- Check that the URL is correct
- Ensure your bot has internet access
- Verify your Red-Discord bot version is compatible

### Permission Errors

If you get permission errors:
- Ensure your bot account has the necessary permissions in your server
- Check that you have admin permissions to run these commands

### Cog Load Failures

If a cog fails to load:
- Check the bot console for error messages
- Ensure all dependencies are installed
- Try updating Red-Discord bot to the latest version

## Getting Help

If you encounter issues during installation:
- Check the [GitHub Issues](https://github.com/adapdoaosdaoda/asdas-cogs/issues)
- Open a new issue with details about your problem
- Include error messages and your bot version

[← Back to Home](Home)
