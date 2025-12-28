# EventChannels - Troubleshooting

Common issues and solutions.

## Channels Not Being Created

### Check Configuration
```
[p]eventchannels viewsettings
```

Verify:
- ✅ Category is set
- ✅ Timezone is correct
- ✅ Role format matches your roles

### Check Permissions

Bot needs:
- **Manage Channels** (server-wide or in category)
- **Manage Roles** (server-wide)
- **View Channels**

### Check Event

- Event must be scheduled in the future
- Role must exist and match role format
- Event must not be cancelled

## Voice Multiplier Not Working

### Keyword Not Matching

Event name must contain the keyword (case-insensitive):
- Keyword: `raid`
- ✅ Matches: "Weekly Raid", "RAID NIGHT"
- ❌ No match: "Weekly Event"

### No Members in Role

Check that role has members assigned before creation time.

## Minimum Roles Issues

### Channels Never Created

- Check if minimum is too high
- Verify members are in the role
- Check logs for retry attempts

### Always Creating Despite Minimum

- Verify keyword matches
- Check `[p]eventchannels listminimumroles`
- Ensure multiplier keyword matches minimum keyword

## Permission Errors

### "Missing Permissions"

Grant bot these permissions in the event category:
1. Right-click category → Edit Channel
2. Go to Permissions
3. Add your bot
4. Enable:
   - Manage Channels
   - Manage Permissions
   - View Channel

### "Cannot Delete Role"

Bot needs **Manage Roles** at server level, not just category.

## Channel Names Too Long

Discord limits channel names to 100 characters.

**Solution 1: Numeric limit**
```
[p]eventchannels setchannelnamelimit 50
```

**Solution 2: Character-based limit**
```
[p]eventchannels setchannelnamelimit ﹕
```

## Divider Issues

### Divider Not Appearing

- Check if enabled: `[p]eventchannels viewsettings`
- Divider only shows to users with event roles
- Bot needs **Manage Channels** permission

### Divider Permissions Wrong

Bot automatically manages divider permissions. If broken:
1. Manually delete the divider channel
2. Bot will recreate it on next event

## Getting Help

Still having issues?

1. Check bot console for errors
2. Enable debug logging (if available)
3. [Open an issue on GitHub](https://github.com/adapdoaosdaoda/asdas-cogs/issues)
4. Include:
   - Error messages
   - Bot version
   - Configuration (`viewsettings` output)

[← Back to Overview](Overview) | [Home](../Home)
