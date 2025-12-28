# EventChannels - Minimum Roles Enforcement

Prevent channel creation when event signup is too low. This feature ensures that channels are only created for events that meet a minimum attendance threshold.

## Overview

The minimum roles enforcement feature allows you to:

- **Set minimum member requirements** per keyword
- **Prevent channel creation** if attendance is too low
- **Automatic retry system** that rechecks attendance before giving up
- **Save resources** by not creating channels for low-attendance events

## How It Works

### Basic Flow

```
┌──────────────────────────────────────────────────────────────┐
│ T-15 min: Check minimum                                       │
│   ├─ 8 members, minimum 10  → ❌ Not met, schedule retry     │
│   └─ Retry scheduled for T-10 min                            │
├──────────────────────────────────────────────────────────────┤
│ T-10 min: Retry check                                        │
│   ├─ 9 members, minimum 10  → ❌ Still not met, retry again  │
│   └─ Retry scheduled for T-5 min                             │
├──────────────────────────────────────────────────────────────┤
│ T-5 min: Retry check                                         │
│   ├─ 12 members, minimum 10 → ✅ MINIMUM MET!                │
│   └─ Proceed with channel creation                           │
└──────────────────────────────────────────────────────────────┘
```

### Retry Intervals

By default, the bot retries at:
- **T-10 minutes** (1st retry)
- **T-5 minutes** (2nd retry)
- **T-2 minutes** (3rd retry, final attempt)

If the minimum isn't met after all retries, **no channels are created**.

## Configuration

### Setting Minimum Roles

```
[p]eventchannels setminimumroles <keyword> <minimum>
```

**Parameters:**
- `keyword` - Must match a configured voice multiplier keyword
- `minimum` - Number of role members required (1-999)

**Example:**
```
[p]eventchannels setminimumroles hero 10
```

This requires events with "hero" in the name to have at least 10 role members.

### Viewing Minimum Requirements

```
[p]eventchannels listminimumroles
```

Shows all configured minimum role requirements.

### Removing Minimum Requirements

```
[p]eventchannels removeminimumroles <keyword>
```

**Example:**
```
[p]eventchannels removeminimumroles hero
```

## Usage Examples

### Example 1: Raid Events

**Setup:**
```
[p]eventchannels setvoicemultiplier raid 9
[p]eventchannels setminimumroles raid 10
```

**Scenario:**
- Event: "Weekly Raid Night"
- Minimum required: 10 members

**Timeline:**
| Time | Members | Result |
|------|---------|--------|
| T-15 min | 7 | ❌ Not met, retry at T-10 |
| T-10 min | 9 | ❌ Not met, retry at T-5 |
| T-5 min | 11 | ✅ Met! Creating channels |

**Channels Created:**
- `weekly-raid-night-text`
- `weekly-raid-night-voice 1` (limit: 10 users)
- `weekly-raid-night-voice 2` (limit: 10 users)

### Example 2: PvP Events

**Setup:**
```
[p]eventchannels setvoicemultiplier pvp 4
[p]eventchannels setminimumroles pvp 8
```

**Scenario:**
- Event: "PvP Tournament"
- Minimum required: 8 members

**Timeline:**
| Time | Members | Result |
|------|---------|--------|
| T-15 min | 12 | ✅ Met! Creating channels immediately |

**Channels Created:**
- `pvp-tournament-text`
- `pvp-tournament-voice 1` (limit: 5 users)
- `pvp-tournament-voice 2` (limit: 5 users)
- `pvp-tournament-voice 3` (limit: 5 users)

### Example 3: Failed Minimum

**Setup:**
```
[p]eventchannels setvoicemultiplier dungeon 4
[p]eventchannels setminimumroles dungeon 5
```

**Scenario:**
- Event: "Dungeon Run"
- Minimum required: 5 members

**Timeline:**
| Time | Members | Result |
|------|---------|--------|
| T-15 min | 3 | ❌ Not met, retry at T-10 |
| T-10 min | 3 | ❌ Not met, retry at T-5 |
| T-5 min | 4 | ❌ Not met, retry at T-2 |
| T-2 min | 4 | ❌ Not met, all retries exhausted |

**Result:** No channels created for this event.

## Retry Mechanism Details

### How Retries Work

1. **Initial Check** - At configured creation time (default: T-15 min)
2. **Schedule Retry** - If minimum not met, schedule next retry
3. **Retry Check** - At retry time, check role count again
4. **Success or Continue** - Either create channels or schedule next retry
5. **Final Attempt** - Last retry at T-2 min before giving up

### Preventing Duplicate Channels

The bot automatically prevents duplicate channel creation:
- Each retry checks if channels already exist
- Once channels are created, all pending retries are cancelled
- Event updates/deletions cancel all retry tasks

### Retry Cancellation

Retry tasks are automatically cancelled when:
- Event is deleted
- Event is cancelled
- Event start time changes
- Minimum requirement is met and channels are created

## Integration with Voice Multipliers

Minimum roles work seamlessly with voice multipliers:

1. **Keyword must match** - Both must use the same keyword
2. **Minimum check first** - Minimum is checked before calculating voice channels
3. **Voice scaling second** - If minimum met, voice multiplier determines channel count

**Example:**
```
[p]eventchannels setvoicemultiplier hero 9
[p]eventchannels setminimumroles hero 15
```

- Event "Hero Raid" with 20 members:
  - ✅ Passes minimum check (20 ≥ 15)
  - Creates `20 / 9 = 2` voice channels
  - Each channel has limit of 10 users

- Event "Hero Raid" with 10 members:
  - ❌ Fails minimum check (10 < 15)
  - No channels created (even though multiplier would create 1)

## Logging

The bot logs all minimum role checks to help you debug:

```
Event 'Hero Raid': minimum not met (8/10 members).
Scheduling retry attempt 1 at T-10 minutes (in 5 minutes)

Event 'Hero Raid': minimum not met (9/10 members).
Scheduling retry attempt 2 at T-5 minutes (in 5 minutes)

Event 'Hero Raid': minimum requirement met on retry attempt 2
(12/10 members). Proceeding with channel creation.
```

## Best Practices

### Setting Appropriate Minimums

- **Don't set too high** - You might miss valid events
- **Consider your community** - Set based on typical attendance
- **Test first** - Use viewsettings and monitor logs

### Recommended Minimums

| Event Type | Multiplier | Recommended Minimum |
|------------|------------|---------------------|
| 10-man Raid | 9 | 8-10 |
| 25-man Raid | 9 | 15-20 |
| PvP (5v5) | 4 | 8-10 |
| Dungeon (5-man) | 4 | 4-5 |
| Large Events | 19 | 25-30 |

### Warning Messages

Consider setting a warning announcement:
```
[p]eventchannels setannouncement {role} Note: Channels will only be created if we have at least 10 signups!
```

## Troubleshooting

### Channels Never Created

**Check:**
- Is the minimum too high for your event?
- Are members joining the role?
- Check logs for minimum check results
- Use `[p]eventchannels listminimumroles` to verify settings

### Channels Created When They Shouldn't

**Check:**
- Is the minimum set correctly?
- Does the keyword match the event name?
- Check `[p]eventchannels viewsettings` for configuration

### Retry Not Working

**Check:**
- Retries happen at T-10, T-5, T-2 minutes
- Event must not be cancelled/deleted
- Check bot logs for retry scheduling

## FAQ

**Q: What if members join after all retries fail?**
A: Channels won't be created. Members must join before the final retry (T-2 min).

**Q: Can I change retry intervals?**
A: Currently retry intervals are fixed at 10, 5, and 2 minutes before event start.

**Q: Does this work without voice multipliers?**
A: No, you must have a voice multiplier configured for the keyword first.

**Q: Will the divider channel be created if minimum fails?**
A: No, if minimum isn't met, no channels are created (including divider).

[← Back to Overview](Overview) | [Commands Reference](Commands-Reference) | [Home](../Home)
