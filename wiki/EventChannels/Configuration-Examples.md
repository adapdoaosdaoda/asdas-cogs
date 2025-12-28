# EventChannels - Configuration Examples

Real-world configuration examples for common use cases.

## Example 1: Basic Raid Setup

**Goal:** Simple 10-man raid channels

```bash
[p]eventchannels setcategory Events
[p]eventchannels settimezone Europe/Amsterdam
[p]eventchannels setchannelformat {name}-{type}
[p]eventchannels setvoicemultiplier raid 9
```

**Event:** "Weekly Raid Night" (10 members)

**Result:**
- `weekly-raid-night-text`
- `weekly-raid-night-voice` (limit: 10)

## Example 2: Multiple Event Types

**Goal:** Different scaling for different content

```bash
[p]eventchannels setvoicemultiplier raid 9      # 10-player raids
[p]eventchannels setvoicemultiplier dungeon 4   # 5-player dungeons
[p]eventchannels setvoicemultiplier pvp 4       # PvP events
```

## Example 3: Minimum Attendance Enforcement

**Goal:** Only create channels if enough people sign up

```bash
[p]eventchannels setvoicemultiplier raid 9
[p]eventchannels setminimumroles raid 8  # Need at least 8 for a 10-man
```

**Event:** "Hero Raid" with retry mechanism
- T-15: 6 members → Retry
- T-10: 7 members → Retry
- T-5: 9 members → ✅ Create channels

## Example 4: Large Community Events

**Goal:** Scale for 40+ player events

```bash
[p]eventchannels setvoicemultiplier alliance 19
[p]eventchannels setminimumroles alliance 20
[p]eventchannels setannouncement {role} {event} starts {time}! We need 20+ signups.
```

**Event:** "Alliance Raid" (45 members)

**Result:**
- `alliance-raid-text`
- `alliance-raid-voice 1` (limit: 20)
- `alliance-raid-voice 2` (limit: 20)
- `alliance-raid-voice 3` (limit: 20)

## Example 5: Character-Limited Channel Names

**Goal:** Clean channel names for events with long titles

```bash
[p]eventchannels setchannelnamelimit ﹕
```

**Event:** `Sunday﹒Hero's Realm﹒POST RESET﹕10 man`

**Result:**
- `sunday﹒hero's-realm﹒post-reset﹕-text` (truncated at ﹕)

## Example 6: Complete Setup with Announcements

```bash
# Basic config
[p]eventchannels setcategory "📅 Event Channels"
[p]eventchannels settimezone America/New_York
[p]eventchannels setcreationtime 30

# Channel format
[p]eventchannels setchannelformat event-{name}-{type}
[p]eventchannels setchannelnamelimit 50

# Voice scaling
[p]eventchannels setvoicemultiplier raid 9
[p]eventchannels setminimumroles raid 10

# Messages
[p]eventchannels setannouncement {role} {event} starts {time}!
[p]eventchannels setstartmessage {role} The event is live!
[p]eventchannels setdeletionwarning ⚠️ Channels closing in 15 minutes

# Divider
[p]eventchannels setdivider true ━━━━━━ ACTIVE EVENTS ━━━━━━
```

[← Back to Overview](Overview) | [Home](../Home)
