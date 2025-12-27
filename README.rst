======
README
======

A collection of custom cogs for Red-Discord bot, including **EventChannels** for automated event channel management and **Reminders** with enhanced time variable support.

.. contents:: Table of Contents
   :local:
   :depth: 2

============
Requirements
============

- Red-Discord Bot v3.5.0 or higher
- Python 3.8+
- Required bot permissions (see individual cog sections)

============
Installation
============

Add this repository to your Red-Discord bot::

    [p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs

Install the cogs you want::

    [p]cog install asdas-cogs eventchannels
    [p]cog install asdas-cogs eventrolereadd
    [p]cog install asdas-cogs reminders

Load the cogs::

    [p]load eventchannels
    [p]load eventrolereadd
    [p]load reminders

=============
EventChannels
=============

A cog that automatically creates temporary text and voice channels for Discord scheduled events, with dynamic voice channel scaling, channel name customization, and automatic cleanup.

Overview
========

This cog automatically creates text and voice channels 15 minutes before (configurable), or immediately within that timeframe, a Discord event starts.
It was made to complement `Raid-Helper <https://raid-helper.dev/>`_ (premium), which allows automatic event + matching role creation, but not automatic text channel creation nor automatic voice channel creation when using its web dashboard (automatic voice channels do work with manual text creation, but these are created instantly, not around event start).

The cog also automatically deletes the channels after a configurable time (default: 4 hours) after the event start time, and if it has the permissions, the role that raid-helper creates. Before deletion, it sends a configurable warning message (default: 15 minutes before deletion) and locks the channels to prevent further messages.

Key Features
============

- **Automatic Channel Creation** - Creates text and voice channels when Discord scheduled events are about to start
- **Role-Based Access Control** - Assigns event-specific roles for channel access
- **Dynamic Voice Scaling** - Creates multiple voice channels based on role member count
- **Channel Name Customization** - Supports character limits and custom truncation points
- **Automatic Cleanup** - Removes channels and roles when events end or are cancelled
- **Divider Channel Support** - Organizes event channels with visual separators
- **Permission Management** - Handles channel permissions and role assignments
- **Configurable Timings** - Customize when channels are created and deleted
- **Custom Messages** - Configure announcement, event start, and deletion warning messages

Required Permissions
====================

Server-Level Permissions
------------------------

- **Manage Channels** - Required to create and delete text/voice channels
- **Manage Roles** - Required to delete event roles after cleanup
- **View Channels** - Required to access and manage the category

Category Permissions (if using a specific category)
---------------------------------------------------

- **Manage Channels** - Required to create channels within the category
- **Manage Permissions** - Required to set channel permissions/overwrites

Commands Overview
=================

All EventChannels commands are subcommands of ``[p]eventchannels``. Run ``[p]eventchannels`` or ``[p]help eventchannels`` to see all available commands.

+---------------------------------------+--------------------------------------------------------+
| Command                               | Description                                            |
+=======================================+========================================================+
| ``[p]eventchannels``                  | Display all EventChannels commands with explanations   |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setcategory``      | Set the category for event channels                    |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels settimezone``      | Configure server timezone                              |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setcreationtime``  | Set when channels are created before event start       |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setdeletion``      | Set channel deletion time after event start            |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setroleformat``    | Customize role name pattern                            |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setchannelformat`` | Customize channel name pattern and rename existing     |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setannouncement``  | Configure announcement message in event channels       |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setstartmessage``  | Configure message sent when event starts               |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setdeletionwarning`` | Configure warning message before channel deletion   |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setchannelnamelimit`` | Set maximum character limit for channel names       |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setvoicemultiplier``  | Add/update voice multiplier for dynamic scaling     |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels listvoicemultipliers`` | List all configured voice multipliers              |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels removevoicemultiplier`` | Remove a specific voice multiplier               |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels disablevoicemultiplier`` | Disable all voice multipliers                   |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels setdivider``       | Enable/disable divider channel and rename existing     |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels viewsettings``     | Display current settings                               |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels testchannellock``  | Test channel locking permissions                       |
+---------------------------------------+--------------------------------------------------------+
| ``[p]eventchannels stresstest``       | Comprehensive stress test of all features              |
+---------------------------------------+--------------------------------------------------------+

Detailed Commands
=================

eventchannels
-------------

**Category:** Information
**Permission:** None (available to all users)

Displays all EventChannels commands with explanations in an organized embed. This is a quick reference guide showing all available configuration commands, voice multiplier commands, divider channel commands, testing commands, and view settings commands. Use this command if you need a reminder of what commands are available and what they do.

**Example:** ``[p]eventchannels``

⠀

eventchannels setcategory
-------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets the Discord category where event text and voice channels will be automatically created. The bot will place all event-related channels in this category for better organization.
Also works with a category ID.

**Example:** ``[p]eventchannels setcategory Events``

⠀

eventchannels settimezone
-------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Configures the timezone used for matching event roles. This ensures the bot generates role names with the correct local time for your server. Uses standard timezone identifiers like ``Europe/Amsterdam``, ``America/New_York``, or ``Asia/Tokyo``.

**Example:** ``[p]eventchannels settimezone Europe/Amsterdam``

⠀

eventchannels setcreationtime
-----------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets how many minutes before an event starts that the bot will create the event channels. Default is 15 minutes. This cannot exceed 1440 minutes (24 hours).

**Example:** ``[p]eventchannels setcreationtime 30``

⠀

eventchannels setdeletion
-------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets how many hours after an event starts before the bot automatically deletes the event channels and role. Default is 4 hours. This gives participants time to wrap up after the event ends.

**Example:** ``[p]eventchannels setdeletion 6``

⠀

eventchannels setroleformat
---------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Customizes the pattern used to match event roles. The bot looks for roles matching this format to determine which events to create channels for. Use placeholders like ``{name}``, ``{day_abbrev}``, ``{day}``, ``{month_abbrev}``, and ``{time}`` to build your pattern.

**Available placeholders:**

- ``{name}`` - Event name
- ``{day_abbrev}`` - Day abbreviation (Mon, Tue, etc.)
- ``{day}`` - Day number (1-31)
- ``{month_abbrev}`` - Month abbreviation (Jan, Feb, etc.)
- ``{time}`` - Time in HH:MM format

**Example:** ``[p]eventchannels setroleformat {name} {day_abbrev} {day}. {month_abbrev} {time}``
**Result:** ``Raid Night Wed 25. Dec 21:00``

⠀

eventchannels setchannelformat
------------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Customizes the pattern used for channel names. This allows you to control how the text and voice channels are named when they're automatically created. **This command will also rename all existing event channels** to match the new format.

**Available placeholders:**

- ``{name}`` - Event name (lowercase, spaces replaced)
- ``{type}`` - Channel type ("text" or "voice")

**Examples:**

- ``{name}᲼{type}`` → "raid᲼night᲼text" (default)
- ``{name}-{type}`` → "raid-night-text"
- ``event-{name}-{type}`` → "event-raid-night-text"

**Example:** ``[p]eventchannels setchannelformat {name}-{type}``

⠀

eventchannels setannouncement
-----------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets the announcement message that will be posted in the event text channel when it's created. This message can mention the role and provide information about when the event starts.

**Available placeholders:**

- ``{role}`` - Mentions the event role
- ``{event}`` - Event name
- ``{time}`` - Event start time (relative format: "in 5 minutes", "in 2 hours")

**Examples:**

- ``{role} The event is starting soon!`` (default)
- ``{role} {event} begins {time}!`` → "@Role Raid Night begins in 15 minutes!"
- ``{role} Get ready, event starts {time}!``

**To disable announcements:** ``[p]eventchannels setannouncement none``

**Example:** ``[p]eventchannels setannouncement {role} {event} starts {time}! Get ready!``

⠀

eventchannels setstartmessage
-----------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets the message that will be posted in the event text channel when the event starts. This message is sent at the exact event start time.

**Available placeholders:**

- ``{role}`` - Mentions the event role
- ``{event}`` - Event name

**Examples:**

- ``{role} The event is starting now!`` (default)
- ``{role} {event} has begun!``
- ``{role} Time to join!``

**To disable event start messages:** ``[p]eventchannels setstartmessage none``

**Example:** ``[p]eventchannels setstartmessage {role} {event} is now live!``

⠀

eventchannels setdeletionwarning
--------------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets the warning message that will be posted 15 minutes before the channels are deleted. After this message is sent, the channels are locked (users can no longer send messages or speak in voice).

**Available placeholders:**

- ``{role}`` - Mentions the event role
- ``{event}`` - Event name

**Examples:**

- ``⚠️ These channels will be deleted in 15 minutes.`` (default)
- ``{role} Event channels closing in 15 minutes!``
- ``⚠️ {event} channels will be removed shortly.``

**To disable deletion warnings:** ``[p]eventchannels setdeletionwarning none``

**Example:** ``[p]eventchannels setdeletionwarning {role} Heads up! These channels close in 15 minutes.``

⠀

eventchannels setchannelnamelimit
---------------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Set the maximum character limit for channel names. Accepts either a number (1-100) or a character/string to truncate at.

**Numeric Limit:**

``[p]eventchannels setchannelnamelimit 50``

This limits the event name to 50 characters before adding type identifiers.

**Character-Based Limit:**

``[p]eventchannels setchannelnamelimit ﹕``

This truncates the event name at the first occurrence of "﹕" (inclusive), keeping everything up to and including that character.

**How It Works:**

- The limit applies **only** to the ``{name}`` portion from the event, not the entire channel name
- Type identifiers like "text" and "voice" are added after the limit is applied
- If the specified character isn't found, falls back to the numeric limit (default: 100)

**Examples:**

Event: ``Sunday﹒Hero's Realm﹒POST RESET﹕10 man``

- Limit: ``﹕`` → Channel becomes: ``Sunday﹒Hero's Realm﹒POST RESET﹕᲼text``
- Limit: ``30`` → Channel becomes: ``Sunday﹒Hero's Realm﹒POST RE᲼text``

⠀

eventchannels setvoicemultiplier
--------------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Enable dynamic voice channel creation based on role member count. When an event name contains the specified keyword (case-insensitive), the bot will create multiple voice channels to accommodate all participants.

**Parameters:**

- ``keyword`` - Trigger word in the event name (case-insensitive)
- ``multiplier`` - Max capacity minus 1 per voice channel (1-99)

**Formula:**

- Number of channels = ``floor(role_members / multiplier)``, minimum 1
- User limit per channel = ``multiplier + 1``

**Example:**

``[p]eventchannels setvoicemultiplier hero 9``

**How It Works:**

1. Event name contains "hero" (case-insensitive)
2. Event role has 25 members
3. Calculation: ``25 / 9 = 2.77`` → 2 channels created
4. Each channel has user limit of 10 (9 + 1)
5. Channels named: ``voice 1``, ``voice 2``

**Channel Naming:**

- 1 channel: ``voice`` (no number)
- 2+ channels: ``voice 1``, ``voice 2``, etc.

⠀

eventchannels listvoicemultipliers
----------------------------------

**Category:** Information
**Permission:** Manage Server or Administrator

List all configured voice multipliers showing keywords and their associated multiplier values.

**Example:** ``[p]eventchannels listvoicemultipliers``

⠀

eventchannels removevoicemultiplier
-----------------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Remove a specific voice multiplier by keyword.

**Example:** ``[p]eventchannels removevoicemultiplier hero``

⠀

eventchannels disablevoicemultiplier
------------------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Disable the voice channel multiplier feature entirely, removing all configured keywords.

**Example:** ``[p]eventchannels disablevoicemultiplier``

⠀

eventchannels setdivider
------------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Enables or disables the divider channel feature and optionally sets a custom name for the divider. The divider channel is a special text channel created before all event channels to provide visual separation in the channel list. It persists across multiple events and is only visible to users with active event roles. **If a new name is provided, the existing divider channel will be renamed automatically.**

**Available options:**

- Enable with default name: ``[p]eventchannels setdivider True``
- Enable with custom name: ``[p]eventchannels setdivider True ━━━━━━ MY EVENTS ━━━━━━``
- Disable: ``[p]eventchannels setdivider False``

The default divider name is: ``━━━━━━ EVENT CHANNELS ━━━━━━``

**Examples:**

- ``[p]eventchannels setdivider True`` → Enable divider with default name
- ``[p]eventchannels setdivider True ════ RAID EVENTS ════`` → Enable with custom name (renames existing divider)
- ``[p]eventchannels setdivider False`` → Disable divider channel

⠀

eventchannels viewsettings
--------------------------

**Category:** Information
**Permission:** Manage Server or Administrator

Displays all current configuration settings in an organized embed, including the category, timezone, creation time, deletion time, role format, channel format, announcement messages, voice multipliers, and all other settings. Use this to verify your setup is correct.

**Example:** ``[p]eventchannels viewsettings``

⠀

eventchannels testchannellock
-----------------------------

**Category:** Testing
**Permission:** Manage Server or Administrator

Test channel locking permissions to ensure the bot can properly lock channels before deletion. This helps verify that the bot has the correct permissions.

**Example:** ``[p]eventchannels testchannellock``

⠀

eventchannels stresstest
------------------------

**Category:** Testing
**Permission:** Manage Server or Administrator

Comprehensive stress test of all features including channel creation, role assignment, voice multipliers, divider channels, and cleanup. This is useful for testing your configuration before live events.

**Example:** ``[p]eventchannels stresstest``

⠀

Configuration Examples
======================

Example 1: Basic Setup
----------------------

::

    [p]eventchannels setcategory Events
    [p]eventchannels settimezone Europe/Amsterdam
    [p]eventchannels setchannelformat {name}᲼{type}
    [p]eventchannels setchannelnamelimit 50

**Event:** ``Weekly Raid Night``

**Channels Created:**

- ``weekly᲼raid᲼night᲼text``
- ``weekly᲼raid᲼night᲼voice``

Example 2: Character-Based Limiting
------------------------------------

::

    [p]eventchannels setchannelnamelimit ﹕

**Event:** ``Sunday﹒Hero's Realm﹒POST RESET﹕10 man``

**Channels Created:**

- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼text``
- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼voice``

Example 3: Voice Multiplier (Small Group)
------------------------------------------

::

    [p]eventchannels setvoicemultiplier raid 9

**Event:** ``Weekly Raid Night`` (role has 8 members)

**Calculation:** ``8 / 9 = 0.88`` → 1 channel

**Channels Created:**

- ``weekly᲼raid᲼night᲼text``
- ``weekly᲼raid᲼night᲼voice`` (limit: 10 users)

Example 4: Voice Multiplier (Medium Group)
-------------------------------------------

::

    [p]eventchannels setvoicemultiplier raid 9

**Event:** ``Weekly Raid Night`` (role has 25 members)

**Calculation:** ``25 / 9 = 2.77`` → 2 channels

**Channels Created:**

- ``weekly᲼raid᲼night᲼text``
- ``weekly᲼raid᲼night᲼voice 1`` (limit: 10 users)
- ``weekly᲼raid᲼night᲼voice 2`` (limit: 10 users)

Example 5: Voice Multiplier (Large Group)
------------------------------------------

::

    [p]eventchannels setvoicemultiplier pvp 4

**Event:** ``PvP Tournament`` (role has 23 members)

**Calculation:** ``23 / 4 = 5.75`` → 5 channels

**Channels Created:**

- ``pvp᲼tournament᲼text``
- ``pvp᲼tournament᲼voice 1`` (limit: 5 users)
- ``pvp᲼tournament᲼voice 2`` (limit: 5 users)
- ``pvp᲼tournament᲼voice 3`` (limit: 5 users)
- ``pvp᲼tournament᲼voice 4`` (limit: 5 users)
- ``pvp᲼tournament᲼voice 5`` (limit: 5 users)

Example 6: Combined Features
-----------------------------

::

    [p]eventchannels setchannelnamelimit ﹕
    [p]eventchannels setvoicemultiplier hero 9

**Event:** ``Sunday﹒Hero's Realm﹒POST RESET﹕10 man`` (role has 40 members)

**Calculation:** ``40 / 9 = 4.44`` → 4 channels

**Channels Created:**

- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼text``
- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼voice 1`` (limit: 10 users)
- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼voice 2`` (limit: 10 users)
- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼voice 3`` (limit: 10 users)
- ``sunday﹒hero's᲼realm﹒post᲼reset﹕᲼voice 4`` (limit: 10 users)

How It Works
============

Event Lifecycle
---------------

1. **Event Created** - Bot detects a new Discord scheduled event
2. **Pre-Event Task** - Schedules channel creation for configured minutes before event start (default: 15)
3. **Channel Creation** - Creates text channel, voice channel(s), and updates role permissions
4. **Announcement** - Posts announcement message in text channel (if configured)
5. **Event Start** - Posts event start message (if configured)
6. **Event Active** - Channels are active and accessible to role members
7. **Deletion Warning** - 15 minutes before cleanup, posts warning and locks channels
8. **Cleanup** - Deletes channels and optionally roles after configured hours (default: 4)

Voice Multiplier Logic
-----------------------

When an event name contains the configured keyword:

1. Counts members in the event role
2. Calculates: ``max(1, floor(members / multiplier))``
3. Creates that many voice channels
4. Sets user limit to ``multiplier + 1`` on each channel
5. Numbers channels if count > 1

Character Limit Logic
----------------------

When processing event names:

1. If character-based limit is set, searches for first occurrence
2. Truncates at that character (inclusive) if found
3. Falls back to numeric limit if character not found
4. Applies limit before adding type identifiers

Troubleshooting
===============

Channels Not Being Created
---------------------------

- Verify bot has permissions to create channels and roles
- Check that event category is set: ``[p]eventchannels viewsettings``
- Ensure event is scheduled (not in the past)
- Check bot has permission to view scheduled events
- Verify the role format matches the roles created by Raid-Helper

Voice Multiplier Not Working
-----------------------------

- Event name must contain the configured keyword (case-insensitive)
- Check configuration: ``[p]eventchannels listvoicemultipliers``
- Verify event role has members assigned
- Multiplier must be between 1-99

Channel Name Too Long
----------------------

- Discord limits channel names to 100 characters
- Use ``[p]eventchannels setchannelnamelimit`` to reduce length
- Consider using shorter channel format
- Use character-based limiting for consistent truncation

Permissions Issues
------------------

- Bot needs these permissions in the event category:
  - Manage Channels
  - Manage Roles
  - View Channels
  - Send Messages
  - Connect to Voice

=========
Reminders
=========

A clone of the `Reminders cog <https://github.com/AAA3A-AAA3A/AAA3A-cogs/tree/main/reminders>`_ from `AAA3A-cogs <https://github.com/AAA3A-AAA3A/AAA3A-cogs>`_ with an enhanced ``{time}`` variable feature to allow for inserting Discord relative timestamps into reminder messages.

Overview
========

Don't forget anything anymore! This cog provides comprehensive reminder functionality including reminders in DMs, channels, FIFO commands scheduler, say scheduler, and more. Features 'Me Too', snooze functionality, and interactive buttons.

Key Features
============

- **Flexible Reminders** - Create reminders in DMs or specific channels
- **Time Variables** - Use ``{time}`` variable to insert Discord relative timestamps
- **FIFO Commands** - Schedule commands to run at specific times
- **Say Scheduler** - Schedule messages to be sent at specific times
- **Me Too Feature** - Allow others to get the same reminder
- **Snooze Functionality** - Postpone reminders with interactive buttons
- **Repeat Support** - Create recurring reminders
- **Migration Tools** - Migrate from RemindMe by PhasecoreX or FIFO by Fox
- **Timezone Support** - Configure personal timezone for accurate time parsing

Text Variables
==============

You can use the following variables in your reminder messages:

- ``{time}`` - Displays a Discord relative timestamp showing when the reminder will expire (e.g., "in 5 minutes", "in 2 hours")

**Example:** ``[p]remindme 1h Don't forget the meeting {time}!``

When the reminder is created, this will show "Don't forget the meeting in 1 hour!" with a Discord timestamp that counts down.

Available Commands
==================

Main Commands
-------------

- ``[p]remind [destination] [targets]... <time> [message_or_text]`` - Create a reminder with optional reminder text or message, in a channel with an user/role ping
- ``[p]remindme <time> [message_or_text]`` - Create a reminder with optional reminder text or message
- ``[p]reminder`` - List, edit and delete existing reminders, or create FIFO/commands or Say reminders

Reminder Management
-------------------

- ``[p]reminder list [card=False] ["text"|"command"|"say"] ["expire"|"created"|"id"=expire]`` - List your existing reminders
- ``[p]reminder edit <reminder>`` - Edit an existing Reminder from its ID
- ``[p]reminder remove [reminders]...`` - Remove existing Reminder(s) from their IDs
- ``[p]reminder clear [confirmation=False]`` - Clear all your existing reminders
- ``[p]reminder expires <reminder> <time>`` - Edit the expires time of an existing Reminder from its ID
- ``[p]reminder text <reminder> <text>`` - Edit the text of an existing Reminder from its ID
- ``[p]reminder repeat <reminder> <repeat>`` - Edit the repeat of an existing Reminder from its ID
- ``[p]reminder auto_delete <reminder> <minutes>`` - Edit the auto-delete time of an existing Reminder from its ID

Special Reminder Types
----------------------

- ``[p]reminder fifo [destination] <time> <command>`` - Create a FIFO/command reminder (command will be executed with you as invoker)
- ``[p]reminder say [destination] <time> <text>`` - Create a reminder that will say/send text

Utility Commands
----------------

- ``[p]reminder timezone <timezone>`` - Set your timezone for the time converter
- ``[p]reminder timestamps [repeat_times=100] [time=now]`` - Get a list of Discord timestamps for a given time
- ``[p]reminder timetips`` - Show time parsing tips

Configuration Commands (Admin)
-------------------------------

- ``[p]setreminders`` - Configure Reminders
- ``[p]setreminders autodeleteminutesreminders <auto_delete_minutes>`` - Auto-delete reminder messages after N minutes (0 to disable)
- ``[p]setreminders maximumuserreminders <maximum_user_reminders>`` - Change the reminders limit for each user (except bot owners)
- ``[p]setreminders fifoallowed <fifo_allowed>`` - Allow or deny commands reminders for users (except bot owners)
- ``[p]setreminders repeatallowed <repeat_allowed>`` - Enable or disabled repeat option for users (except bot owners)
- ``[p]setreminders minimumrepeat <minimum_repeat>`` - Change the minimum minutes number for a repeat time
- ``[p]setreminders secondsallowed <seconds_allowed>`` - Check reminders every 30 seconds instead of every 1 minute
- ``[p]setreminders metoo <me_too>`` - Show a 'Me too' button in reminders
- ``[p]setreminders creationview <creation_view>`` - Send Creation view/buttons when reminders creation
- ``[p]setreminders snoozeview <snooze_view>`` - Send Snooze view/buttons when reminders sending
- ``[p]setreminders clearuserreminders <user> [confirmation=False]`` - Clear all existing reminders for a user
- ``[p]setreminders migratefromremindme`` - Migrate Reminders from RemindMe by PhasecoreX
- ``[p]setreminders migratefromfifo`` - Migrate Reminders from FIFO by Fox
- ``[p]setreminders showsettings [with_dev=False]`` - Show all settings for the cog with defaults and values
- ``[p]setreminders modalconfig [confirmation=False]`` - Set all settings for the cog with a Discord Modal
- ``[p]setreminders resetsetting <setting>`` - Reset a setting
- ``[p]setreminders getdebugloopstatus`` - Get an embed to check loop status

Usage Examples
==============

Basic Reminders
---------------

::

    [p]remindme 30m Check the oven
    [p]remindme 2h Meeting with team
    [p]remind #general 1d Server maintenance tomorrow!

Using Time Variables
--------------------

::

    [p]remindme 1h Don't forget the meeting {time}!
    [p]remind #events 30m The event starts {time}!

This will create a reminder that shows "Don't forget the meeting in 1 hour!" with a live countdown timestamp.

FIFO Commands
-------------

::

    [p]reminder fifo 1h ping
    [p]reminder fifo #general 30m announce Server restart

Say Scheduler
-------------

::

    [p]reminder say #announcements 2h Scheduled maintenance will begin soon
    [p]reminder say 1d Remember to vote for the server!

Repeating Reminders
-------------------

::

    [p]remindme 1d Take medication
    [p]reminder repeat <reminder_id> 1d

Further Support
===============

- Check out the `AAA3A-cogs documentation <https://aaa3a-cogs.readthedocs.io/en/latest/>`_
- Join the `cog support server <https://discord.gg/GET4DVk>`_ for help
- Open an issue on the `AAA3A-cogs repository <https://github.com/AAA3A-AAA3A/AAA3A-cogs>`_

=======
Support
=======

For issues, feature requests, or questions about these cogs:

- Open an issue on the `GitHub repository <https://github.com/adapdoaosdaoda/asdas-cogs/issues>`_
- For Reminders-specific questions, refer to the `AAA3A-cogs repository <https://github.com/AAA3A-AAA3A/AAA3A-cogs>`_

=======
Credits
=======

- **EventChannels** - Developed for Red-Discord Bot framework
- **Reminders** - Original cog by `AAA3A <https://github.com/AAA3A-AAA3A/AAA3A-cogs>`_, modified to include ``{time}`` variable support
- Thanks to Kreusada for the Python code to automatically generate documentation

=======
License
=======

See individual cog directories for license information.

- EventChannels: See repository for license details
- Reminders: Licensed under the same terms as AAA3A-cogs (see ``Reminders/LICENSE``)
