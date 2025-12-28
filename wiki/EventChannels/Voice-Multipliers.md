# EventChannels - Voice Multipliers

Automatically create multiple voice channels based on event attendance. This feature scales voice channels dynamically to accommodate all participants.

## Quick Start

```
[p]eventchannels setvoicemultiplier <keyword> <multiplier>
```

**Example:**
```
[p]eventchannels setvoicemultiplier raid 9
```

Now any event with "raid" in the name will create multiple voice channels based on role member count.

## How It Works

### Formula

```
Number of channels = max(1, floor(members / multiplier))
User limit per channel = multiplier + 1
```

### Example Calculation

**Setup:** `multiplier = 9` (creates channels with 10-user limit)
**Event:** "Weekly Raid Night" with 25 members

**Calculation:**
- `25 / 9 = 2.77`
- `floor(2.77) = 2 channels`
- Each channel: limit of `9 + 1 = 10 users`

**Channels Created:**
- `weekly-raid-night-text`
- `weekly-raid-night-voice 1` (limit: 10)
- `weekly-raid-night-voice 2` (limit: 10)

## Configuration Examples

### Small Groups (5 players)

```
[p]eventchannels setvoicemultiplier dungeon 4
```

- 5 members → 1 channel (limit: 5)
- 10 members → 2 channels (limit: 5 each)
- 20 members → 5 channels (limit: 5 each)

### Medium Groups (10 players)

```
[p]eventchannels setvoicemultiplier raid 9
```

- 10 members → 1 channel (limit: 10)
- 25 members → 2 channels (limit: 10 each)
- 50 members → 5 channels (limit: 10 each)

### Large Groups (20 players)

```
[p]eventchannels setvoicemultiplier alliance 19
```

- 20 members → 1 channel (limit: 20)
- 40 members → 2 channels (limit: 20 each)
- 100 members → 5 channels (limit: 20 each)

## Keywords

### Case-Insensitive Matching

Keywords match regardless of case:
- Keyword: `raid`
- Matches: "Raid", "RAID", "Weekly Raid", "raid night"

### First Match Wins

If multiple keywords match, the first one in your list is used:

```
[p]eventchannels setvoicemultiplier raid 9
[p]eventchannels setvoicemultiplier pvp 4
```

Event: "Raid PvP Tournament" → Uses "raid" multiplier (9)

### Managing Keywords

**List all multipliers:**
```
[p]eventchannels listvoicemultipliers
```

**Remove a multiplier:**
```
[p]eventchannels removevoicemultiplier raid
```

**Disable all multipliers:**
```
[p]eventchannels disablevoicemultiplier
```

## Channel Naming

### Single Channel

When only 1 channel is created:
```
weekly-raid-night-voice
```

### Multiple Channels

When 2+ channels are created:
```
weekly-raid-night-voice 1
weekly-raid-night-voice 2
weekly-raid-night-voice 3
```

## Choosing the Right Multiplier

### By Activity Type

| Activity | Players | Multiplier | Limit |
|----------|---------|------------|-------|
| Dungeon | 5 | 4 | 5 |
| Raid (10) | 10 | 9 | 10 |
| Raid (25) | 25 | 9 or 24 | 10 or 25 |
| PvP (3v3) | 6 | 2 or 5 | 3 or 6 |
| PvP (5v5) | 10 | 4 or 9 | 5 or 10 |
| Events | 20+ | 19 | 20 |

### Calculation Table

| Multiplier | Limit | Members → Channels |
|------------|-------|-------------------|
| 4 | 5 | 5→1, 10→2, 20→5 |
| 9 | 10 | 10→1, 25→2, 50→5 |
| 19 | 20 | 20→1, 40→2, 100→5 |
| 24 | 25 | 25→1, 50→2, 100→4 |

## Best Practices

### 1. Match Your Content

Set multipliers based on your typical group sizes:
- 5-man content: multiplier 4
- 10-man content: multiplier 9
- 25-man content: multiplier 24

### 2. Leave Room for Flexibility

Set limit slightly higher than exact group size:
- 5-man dungeon: use multiplier 5 (6 limit) for flexibility
- 10-man raid: use multiplier 9 (10 limit) for exact size

### 3. Use Keywords Wisely

Choose keywords that won't accidentally match other events:
- ✅ Good: `raid`, `dungeon`, `pvp`
- ❌ Risky: `the`, `event`, `weekly`

## Troubleshooting

### Not Creating Multiple Channels

**Check:**
- Does event name contain the keyword?
- Is multiplier configured? (`[p]eventchannels listvoicemultipliers`)
- Does the role have members?
- Are there enough members to trigger multiple channels?

### Wrong Number of Channels

**Check:**
- Verify member count: `channels = floor(members / multiplier)`
- Check role membership before event creation time
- Confirm correct multiplier value

### No User Limit Set

This is normal for events without multipliers. Only events matching a keyword get user limits.

[← Back to Overview](Overview) | [Commands Reference](Commands-Reference) | [Home](../Home)
