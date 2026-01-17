# ModalPatch - Experimental Select Support for discord.py Modals

⚠️ **EXPERIMENTAL COG - USE AT YOUR OWN RISK** ⚠️

## Overview

This cog monkey-patches discord.py's `Modal` class to enable `Select` components (dropdowns), which are supported in discord.js but not officially supported in discord.py.

### Why This Exists

- **discord.js** supports select menus in modals (added September 2025)
- **discord.py** only officially supports `TextInput` components in modals
- This cog bridges the gap by patching discord.py to handle select component responses

## How It Works

The cog patches the `Modal._refresh()` method to handle select component types (3, 5-8) in addition to the standard TextInput (type 4):

```python
Component Types:
- Type 4: TextInput (officially supported)
- Type 3: String Select (patched)
- Type 5: User Select (patched)
- Type 6: Role Select (patched)
- Type 7: Mentionable Select (patched)
- Type 8: Channel Select (patched)
```

## Installation

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
[p]cog install asdas-cogs modalpatch
[p]load modalpatch
```

**IMPORTANT:** Load this cog **BEFORE** any cogs that use Modals with Select components.

## Usage

### Basic Example

```python
import discord
from discord.ui import Modal, TextInput, Select

class MyModal(Modal, title="Example Modal"):
    # Regular text input (always works)
    name = TextInput(label="Your Name", placeholder="Enter name...")

    def __init__(self):
        super().__init__()

        # Add select menu (requires ModalPatch)
        self.color = Select(
            placeholder="Choose a color",
            options=[
                discord.SelectOption(label="Red", value="red", emoji="🔴"),
                discord.SelectOption(label="Blue", value="blue", emoji="🔵"),
                discord.SelectOption(label="Green", value="green", emoji="🟢"),
            ],
            custom_id="color_select"
        )
        self.add_item(self.color)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name.value
        # Access selected value (patched by ModalPatch)
        color = self.color.values[0] if self.color.values else "none"

        await interaction.response.send_message(
            f"Name: {name}, Color: {color}",
            ephemeral=True
        )
```

### Testing the Patch

Use the built-in test command:

```
[p]modalpatchtest
```

This will create a test modal with both a text input and a select menu. If the patch is working:
- ✅ You'll see both components in the modal
- ✅ Submitting will show your selections
- ⚠️ If Discord's API rejects it, you'll get a warning message

### Check Patch Status

```
[p]modalpatchstatus
```

Shows whether the patch is currently active.

## Commands

| Command | Description | Required Permission |
|---------|-------------|---------------------|
| `[p]modalpatchstatus` | Check if the patch is active | Bot Owner |
| `[p]modalpatchtest` | Test the patch with a sample modal | Bot Owner |

## Limitations & Risks

### ⚠️ Known Limitations

1. **Discord API May Reject**: Even with the patch, Discord's API might reject modals containing select components. The patch makes discord.py send them, but Discord controls whether they're accepted.

2. **discord.py Version Compatibility**: This patch was designed for discord.py 2.x. Future versions may change Modal implementation, breaking the patch.

3. **Monkey-Patching Risks**:
   - Global modification to `discord.ui.Modal` class
   - May conflict with other cogs that modify Modal behavior
   - Updates to discord.py could break the patch

4. **No Official Support**: This is a workaround, not an official feature. Discord or discord.py could break this at any time.

### 🔒 Safety Considerations

- The patch only modifies the `_refresh()` method, which handles component responses
- Original behavior is preserved for TextInput components
- Patch is cleanly removed when cog is unloaded
- No persistent changes to discord.py files

### 🐛 Potential Issues

**If Discord's API rejects select components in modals:**
- The modal will send, but selected values won't be returned
- Your `on_submit` handler won't receive select values
- No error will occur; values will simply be empty

**If discord.py updates break the patch:**
- The cog will fail to load or log errors
- Unload the cog and wait for an update
- Existing modals without selects will continue working

## Technical Details

### Patching Process

1. **On Load**: Cog stores original `Modal._refresh` method
2. **Patch Applied**: Replaces `_refresh` with patched version that handles types 3-8
3. **On Unload**: Restores original `_refresh` method

### Component Response Handling

**TextInput (Type 4)** - Original behavior:
```python
item.value = child.get('value')  # String value
```

**Select (Types 3, 5-8)** - Patched behavior:
```python
item.values = child.get('values', [])  # Array of selected values
item.value = values[0]  # Convenience: first selected value
```

### Accessing Selected Values

After modal submission, access select values via:

```python
# Multiple selections (if max_values > 1)
selected = self.my_select.values  # List of strings

# Single selection (convenience)
selected = self.my_select.value  # String (first value)
```

## Discord.js Comparison

This patch attempts to replicate discord.js modal behavior:

**discord.js (Native Support):**
```javascript
const modal = new ModalBuilder()
  .addComponents(
    new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder()
        .setCustomId('color')
        .setOptions([...])
    )
  );
```

**discord.py (With ModalPatch):**
```python
class MyModal(Modal):
    def __init__(self):
        super().__init__()
        self.color = Select(custom_id='color', options=[...])
        self.add_item(self.color)
```

## Troubleshooting

### Modal doesn't show select menu
- Ensure ModalPatch is loaded: `[p]cog list`
- Check patch status: `[p]modalpatchstatus`
- Try reloading: `[p]reload modalpatch`

### Select values are None/empty
- Discord's API might be rejecting the select component
- Check bot logs for errors
- Try the test command: `[p]modalpatchtest`

### Patch conflicts with other cogs
- Load order matters: load ModalPatch first
- Check logs for Modal-related errors
- Some cogs may have their own Modal patches

### discord.py update broke the patch
- Check for ModalPatch updates in the repo
- Temporarily unload the cog: `[p]unload modalpatch`
- Report the issue on GitHub

## Development

### Running Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run ModalPatch tests
python3 -m pytest modalpatch/test_modalpatch.py -v
```

### Contributing

If you find issues or improvements:
1. Test your changes thoroughly
2. Ensure backward compatibility
3. Document any Discord API behavior changes
4. Submit a PR with test coverage

## Future Outlook

### If discord.py adds native support:
- This cog will become obsolete (good thing!)
- Unload the cog and use native Select support
- Existing code should work without changes

### If Discord removes API support:
- The patch will stop working
- Fall back to View-based select menus (current polling cog approach)
- Or use multi-step modal flows (text input → select view)

## References

- [Discord.js Modal Select Support](https://discordjs.guide/legacy/interactions/modals)
- [discord.py Modal Discussion](https://github.com/Rapptz/discord.py/discussions/9007)
- [Discord API Component Types](https://discord.com/developers/docs/interactions/message-components)
- [Pycord Modal Dialogs](https://guide.pycord.dev/interactions/ui-components/modal-dialogs)

## License

Same as asdas-cogs repository.

## Support

This is an experimental cog. Support is limited. Use at your own risk.

For bugs specific to this cog, open an issue on the asdas-cogs GitHub repository.
