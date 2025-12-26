======
README
======

This cog automatically creates text and voice channels 15 minutes before (configurable), or immediately within that timeframe, a Discord event starts.
It was made to complement `Raid-Helper <https://raid-helper.dev/>`_ (premium), which allows automatic event + matching role creation, but not automatic text channel creation nor automatic voice channel creation when using its web dashboard (automatic voice channels do work with manual text creation, but these are created instantly, not around event start).

The cog also automatically deletes the channels after a configurable time (default: 4 hours) after the event start time, and if it has the permissions, the role that raid-helper creates. Before deletion, it sends a configurable warning message (default: 15 minutes before deletion) and locks the channels to prevent further messages.

Reminders is simply a `cloned reminders <https://github.com/AAA3A-AAA3A/AAA3A-cogs/tree/main/reminders>`_ cog from `AAA3A-cogs <https://github.com/AAA3A-AAA3A/AAA3A-cogs>`_ but including a {time} variable to allow for inserting a discord relative time into the reminders.

Installation
============

::

    [p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
    [p]cog install asdas-cogs EventChannels

----

Cog Permissions
===============

The cog requires the following permissions:

Server-Level Permissions
------------------------

- **Manage Channels** - Required to create and delete text/voice channels
- **Manage Roles** - Required to delete event roles after cleanup
- **View Channels** - Required to access and manage the category

Category Permissions (if using a specific category)
---------------------------------------------------

- **Manage Channels** - Required to create channels within the category
- **Manage Permissions** - Required to set channel permissions/overwrites

----

Commands Overview
=================

+------------------------------+--------------------------------------------------------+
| Command                      | Description                                            |
+==============================+========================================================+
| ``[p]eventchannels``         | Display all EventChannels commands with explanations   |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventcategory``      | Set the category for event channels                    |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventtimezone``      | Configure server timezone                              |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventcreationtime``  | Set when channels are created before event start       |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventdeletion``      | Set channel deletion time after event start            |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventroleformat``    | Customize role name pattern                            |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventchannelformat`` | Customize channel name pattern and rename existing     |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventannouncement``  | Configure announcement message in event channels       |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventstartmessage``  | Configure message sent when event starts               |
+------------------------------+--------------------------------------------------------+
| ``[p]setdeletionwarning``    | Configure warning message before channel deletion      |
+------------------------------+--------------------------------------------------------+
| ``[p]seteventdivider``       | Enable/disable divider channel and rename existing     |
+------------------------------+--------------------------------------------------------+
| ``[p]vieweventsettings``     | Display current settings                               |
+------------------------------+--------------------------------------------------------+

Commands
==============

eventchannels
-------------

**Category:** Information
**Permission:** None (available to all users)

Displays all EventChannels commands with explanations in an organized embed. This is a quick reference guide showing all available configuration commands, divider channel commands, and view settings commands. Use this command if you need a reminder of what commands are available and what they do.

**Example:** ``[p]eventchannels``

⠀

seteventcategory
----------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets the Discord category where event text and voice channels will be automatically created. The bot will place all event-related channels in this category for better organization.
Also works with a category ID.

**Example:** ``[p]seteventcategory Events``

⠀

seteventtimezone
----------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Configures the timezone used for matching event roles. This ensures the bot generates role names with the correct local time for your server. Uses standard timezone identifiers like ``Europe/Amsterdam``, ``America/New_York``, or ``Asia/Tokyo``.

**Example:** ``[p]seteventtimezone Europe/Amsterdam``

⠀

seteventcreationtime
--------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets how many minutes before an event starts that the bot will create the event channels. Default is 15 minutes. This cannot exceed 1440 minutes (24 hours).

**Example:** ``[p]seteventcreationtime 30``

⠀

seteventdeletion
----------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Sets how many hours after an event starts before the bot automatically deletes the event channels and role. Default is 4 hours. This gives participants time to wrap up after the event ends.

**Example:** ``[p]seteventdeletion 6``

⠀

seteventroleformat
------------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Customizes the pattern used to match event roles. The bot looks for roles matching this format to determine which events to create channels for. Use placeholders like ``{name}``, ``{day_abbrev}``, ``{day}``, ``{month_abbrev}``, and ``{time}`` to build your pattern.

**Available placeholders:**

- ``{name}`` - Event name
- ``{day_abbrev}`` - Day abbreviation (Mon, Tue, etc.)
- ``{day}`` - Day number (1-31)
- ``{month_abbrev}`` - Month abbreviation (Jan, Feb, etc.)
- ``{time}`` - Time in HH:MM format

**Example:** ``[p]seteventroleformat {name} {day_abbrev} {day}. {month_abbrev} {time}``
**Result:** ``Raid Night Wed 25. Dec 21:00``

⠀

seteventchannelformat
---------------------

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

**Example:** ``[p]seteventchannelformat {name}-{type}``

⠀

seteventannouncement
--------------------

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

**To disable announcements:** ``[p]seteventannouncement none``

**Example:** ``[p]seteventannouncement {role} {event} starts {time}! Get ready!``

⠀

seteventstartmessage
--------------------

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

**To disable event start messages:** ``[p]seteventstartmessage none``

**Example:** ``[p]seteventstartmessage {role} {event} is now live!``

⠀

setdeletionwarning
------------------

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

**To disable deletion warnings:** ``[p]setdeletionwarning none``

**Example:** ``[p]setdeletionwarning {role} Heads up! These channels close in 15 minutes.``

⠀

seteventdivider
---------------

**Category:** Configuration
**Permission:** Manage Server or Administrator

Enables or disables the divider channel feature and optionally sets a custom name for the divider. The divider channel is a special text channel created before all event channels to provide visual separation in the channel list. It persists across multiple events and is only visible to users with active event roles. **If a new name is provided, the existing divider channel will be renamed automatically.**

**Available options:**

- Enable with default name: ``[p]seteventdivider True``
- Enable with custom name: ``[p]seteventdivider True ━━━━━━ MY EVENTS ━━━━━━``
- Disable: ``[p]seteventdivider False``

The default divider name is: ``━━━━━━ EVENT CHANNELS ━━━━━━``

**Examples:**

- ``[p]seteventdivider True`` → Enable divider with default name
- ``[p]seteventdivider True ════ RAID EVENTS ════`` → Enable with custom name (renames existing divider)
- ``[p]seteventdivider False`` → Disable divider channel

⠀

vieweventsettings
-----------------

**Category:** Information
**Permission:** Manage Server or Administrator

Displays all current configuration settings in an organized embed, including the category, timezone, creation time, deletion time, role format, channel format, and announcement message. Use this to verify your setup is correct.

**Example:** ``[p]vieweventsettings``

⠀
