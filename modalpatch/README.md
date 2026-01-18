# ModalPatch Developer Guide

**ModalPatch** is a monkey-patching cog that extends discord.py's `Modal` class to support Discord API v10 Rich Modal features, including Selects, TextDisplay components, and auto-boxing of Select components in Labels.

## Table of Contents

- [What It Does](#what-it-does)
- [Installation](#installation)
- [Using ModalPatch in Your Cog](#using-modalpatch-in-your-cog)
  - [Basic Usage](#basic-usage)
  - [Available Components](#available-components)
  - [Complete Example](#complete-example)
- [Component Reference](#component-reference)
  - [TextDisplay](#textdisplay)
  - [Label (Auto-Boxing)](#label-auto-boxing)
  - [Selects in Modals](#selects-in-modals)
- [How It Works](#how-it-works)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)

---

## What It Does

Discord API v10 introduced **Rich Modals** with these features:
- **TextDisplay (Type 10)**: Read-only text for headers/instructions
- **Selects in Modals**: RoleSelect, ChannelSelect, UserSelect, MentionableSelect, StringSelect
- **Label Auto-Boxing (Type 18)**: Selects must be wrapped in a Label container

discord.py does **not** natively support these features. ModalPatch bridges the gap by:
1. Adding `TextDisplay` and `Label` component classes to `discord.ui`
2. Patching `Modal.add_item()` to accept Selects and custom components
3. Patching `Modal.to_dict()` to auto-box Selects and serialize custom components
4. Patching `Modal._refresh()` to hydrate Select values from interaction responses

---

## Installation

ModalPatch must be loaded **before** any cog that uses Rich Modal features.

```bash
[p]load modalpatch
[p]load yourcog  # Your cog that uses Rich Modals
```

If ModalPatch is loaded after your cog, your cog must be reloaded:
```bash
[p]load modalpatch
[p]reload yourcog
```

---

## Using ModalPatch in Your Cog

### Basic Usage

1. **Check if ModalPatch is loaded** (optional but recommended):
```python
from redbot.core import commands

class YourCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not bot.get_cog("ModalPatch"):
            raise RuntimeError("ModalPatch must be loaded before YourCog")
```

2. **Import components from discord.ui**:
```python
from discord.ui import Modal, TextInput, RoleSelect
# TextDisplay and Label are injected by ModalPatch
from discord.ui import TextDisplay, Label  # Available after ModalPatch loads
```

3. **Build your modal**:
```python
class MyModal(Modal, title="Example Form"):
    def __init__(self):
        super().__init__()

        # Add a header
        self.add_item(TextDisplay(content="Please select your role", style=1))

        # Add a RoleSelect (auto-boxed by ModalPatch)
        self.role_select = RoleSelect(
            placeholder="Choose a role",
            min_values=1,
            max_values=1,
            custom_id="role_input"
        )
        self.add_item(self.role_select)

        # Add a TextInput
        self.reason = TextInput(
            label="Reason",
            placeholder="Why are you selecting this?",
            custom_id="reason_input"
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        selected_roles = self.role_select.values  # List of discord.Role objects
        reason_text = self.reason.value

        await interaction.response.send_message(
            f"You selected: {selected_roles[0].name}\nReason: {reason_text}",
            ephemeral=True
        )
```

### Available Components

After ModalPatch loads, you can use these in `Modal.add_item()`:

| Component | Type | Description | Auto-Boxed? |
|-----------|------|-------------|-------------|
| `TextInput` | 4 | Standard text input (native discord.py) | No |
| `TextDisplay` | 10 | Read-only text display | No |
| `StringSelect` | 3 | String dropdown | Yes |
| `RoleSelect` | 8 | Role picker | Yes |
| `ChannelSelect` | 8 | Channel picker | Yes |
| `UserSelect` | 5 | User picker | Yes |
| `MentionableSelect` | 7 | User/Role picker | Yes |

**Auto-Boxing**: Selects are automatically wrapped in a `Label` (Type 18) container during serialization. You don't need to manually wrap them.

### Complete Example

```python
import discord
from discord.ui import Modal, TextInput, RoleSelect, ChannelSelect, TextDisplay
from redbot.core import commands

class ConfigModal(Modal, title="Server Configuration"):
    def __init__(self):
        super().__init__()

        # 1. Header
        self.add_item(TextDisplay(
            content="Configure your server settings",
            style=1
        ))

        # 2. Role Selection
        self.admin_role = RoleSelect(
            placeholder="Select admin role",
            min_values=1,
            max_values=1,
            custom_id="admin_role_select"
        )
        self.add_item(self.admin_role)

        # 3. Channel Selection
        self.log_channel = ChannelSelect(
            placeholder="Select log channel",
            min_values=1,
            max_values=1,
            custom_id="log_channel_select"
        )
        self.add_item(self.log_channel)

        # 4. Text Input
        self.prefix = TextInput(
            label="Server Prefix",
            placeholder="Enter custom prefix",
            default="!",
            max_length=3,
            custom_id="prefix_input"
        )
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction):
        admin_role = self.admin_role.values[0]  # discord.Role
        log_channel = self.log_channel.values[0]  # discord.TextChannel/etc
        prefix = self.prefix.value  # str

        await interaction.response.send_message(
            f"Configuration saved!\n"
            f"Admin Role: {admin_role.mention}\n"
            f"Log Channel: {log_channel.mention}\n"
            f"Prefix: `{prefix}`",
            ephemeral=True
        )

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not bot.get_cog("ModalPatch"):
            raise RuntimeError("ModalPatch must be loaded first")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def configure(self, ctx: commands.Context):
        """Opens the configuration modal"""
        await ctx.send("Opening configuration form...", delete_after=3)
        await ctx.interaction.response.send_modal(ConfigModal())
```

---

## Component Reference

### TextDisplay

Read-only text for headers, instructions, or separators.

```python
from discord.ui import TextDisplay

TextDisplay(
    content: str,      # The text to display
    style: int = 1,    # Visual style (1 = default)
    row: Optional[int] = None  # Row position (0-4)
)
```

**Example:**
```python
header = TextDisplay(content="Please fill out the form below", style=1)
self.add_item(header)
```

**Note:** TextDisplay components are **not interactive** and do not appear in `on_submit()` values.

---

### Label (Auto-Boxing)

ModalPatch **automatically** wraps Selects in Labels. You don't need to manually create Labels.

**Manual Usage (advanced):**
```python
from discord.ui import Label, RoleSelect

role_select = RoleSelect(placeholder="Pick a role", custom_id="role")
labeled_select = Label(label="Role Selection", child=role_select)
self.add_item(labeled_select)
```

**Auto-Boxing (recommended):**
```python
# ModalPatch auto-wraps this during serialization
role_select = RoleSelect(placeholder="Pick a role", custom_id="role")
self.add_item(role_select)  # Automatically wrapped with placeholder as label
```

---

### Selects in Modals

All discord.py Select types are supported:

```python
from discord.ui import (
    StringSelect,
    RoleSelect,
    ChannelSelect,
    UserSelect,
    MentionableSelect
)

# StringSelect
options_select = StringSelect(
    placeholder="Choose an option",
    options=[
        discord.SelectOption(label="Option 1", value="opt1"),
        discord.SelectOption(label="Option 2", value="opt2"),
    ],
    custom_id="string_select"
)

# RoleSelect
role_select = RoleSelect(
    placeholder="Select roles",
    min_values=1,
    max_values=3,
    custom_id="role_select"
)

# ChannelSelect
channel_select = ChannelSelect(
    placeholder="Select a channel",
    channel_types=[discord.ChannelType.text],
    custom_id="channel_select"
)

# UserSelect
user_select = UserSelect(
    placeholder="Select users",
    min_values=1,
    max_values=5,
    custom_id="user_select"
)

# MentionableSelect (users + roles)
mention_select = MentionableSelect(
    placeholder="Mention someone",
    custom_id="mention_select"
)
```

**Accessing Values in `on_submit()`:**
```python
async def on_submit(self, interaction: discord.Interaction):
    # Selects return a list of discord objects
    selected_roles = self.role_select.values  # List[discord.Role]
    selected_channels = self.channel_select.values  # List[discord.abc.GuildChannel]
    selected_users = self.user_select.values  # List[discord.User]

    # StringSelect returns a list of value strings
    selected_options = self.options_select.values  # List[str]
```

---

## How It Works

ModalPatch applies three monkey-patches to `discord.ui.Modal`:

### 1. `Modal.add_item()` Patch
Allows Selects and custom components (TextDisplay, Label) to be added:

```python
def _patched_add_item(self, item: Item):
    if isinstance(item, TextInput):
        return _original_add_item(self, item)  # Use original logic

    # Allow any Item type (Selects, TextDisplay, etc.)
    if len(self._children) >= 5:
        raise ValueError('Modal cannot have more than 5 items')

    self._children.append(item)
    return self
```

### 2. `Modal.to_dict()` Patch
Serializes components according to Discord API v10 schema:

```python
def _patched_to_dict(self):
    payload = {'title': self.title, 'custom_id': self.custom_id, 'components': []}

    for item in self._children:
        if isinstance(item, (StringSelect, RoleSelect, ...)):
            # Auto-Box Selects in Label (Type 18)
            label_text = item.placeholder or "Select Option"
            wrapper = Label(label=label_text, child=item)
            payload['components'].append(wrapper.to_component_dict())

        elif isinstance(item, TextDisplay):
            # Serialize TextDisplay (Type 10)
            payload['components'].append(item.to_component_dict())

        elif isinstance(item, TextInput):
            # Wrap TextInput in ActionRow (Type 1)
            payload['components'].append({
                'type': 1,
                'components': [item.to_component_dict()]
            })

    return payload
```

### 3. `Modal._refresh()` Patch
Hydrates Select values from interaction responses:

```python
def _patched_refresh(self, interaction: discord.Interaction, components=None):
    # Flatten components and handle Type 18 unwrapping
    flat_components = []
    for row in components:
        if row['type'] == 18:  # Label wrapper
            flat_components.append(row['component'])  # Unwrap
        elif row['type'] == 1:  # ActionRow
            flat_components.extend(row.get('components', []))

    # Map custom_id to component data
    component_map = {c['custom_id']: c for c in flat_components if 'custom_id' in c}

    # Hydrate Select values
    for item in self._children:
        if isinstance(item, (StringSelect, RoleSelect, ...)):
            c_data = component_map.get(item.custom_id)
            if c_data and 'values' in c_data:
                item._values = c_data['values']
                item.refresh_state(interaction)
```

---

## Limitations

1. **Maximum 5 Components**: Discord limits Modals to 5 top-level components (enforced by ModalPatch).

2. **No Buttons**: Modals cannot contain Buttons (Discord API limitation).

3. **discord.py Compatibility**: Requires discord.py 2.0+ (tested with 2.3+). Uses compatibility shims for `StringSelect` vs legacy `Select`.

4. **Load Order**: ModalPatch **must** be loaded before any cog that uses Rich Modals.

5. **No `disabled` on Selects**: The `disabled` parameter is sanitized (removed) from Selects in Modals to comply with Discord's schema.

---

## Troubleshooting

### ImportError: cannot import name 'TextDisplay'

**Cause:** ModalPatch is not loaded yet.

**Fix:**
```bash
[p]load modalpatch
[p]reload yourcog
```

### Modal submission returns empty Select values

**Cause:** Missing or incorrect `custom_id` on Select components.

**Fix:** Always set a unique `custom_id`:
```python
role_select = RoleSelect(
    placeholder="Select role",
    custom_id="my_unique_role_select"  # Required!
)
```

### TypeError: Modal cannot have more than 5 items

**Cause:** You're adding more than 5 components to the Modal.

**Fix:** Reduce the number of components or combine multiple Selects into a single StringSelect with options.

### Select values are `None` in `on_submit()`

**Cause:** The `_refresh()` patch failed to hydrate values (likely due to `custom_id` mismatch).

**Fix:** Verify:
1. Each Select has a **unique** `custom_id`
2. You're accessing `.values` (not `.value`)
3. ModalPatch is loaded

---

## Testing

ModalPatch includes a test command:

```bash
[p]modal_test
```

This launches a test modal with:
- TextDisplay header
- RoleSelect
- TextInput

Use this to verify ModalPatch is working correctly before building your own modals.

---

## Example Cogs Using ModalPatch

See these cogs for real-world examples:
- `eventchannels` (modalpatch/modalpatch.py:216-257) - Uses `RichTestModal` with TextDisplay, RoleSelect, and TextInput

---

## License

This cog is part of the asdas-cogs repository and follows the same license terms.

## Support

If you encounter issues:
1. Verify ModalPatch is loaded: `[p]cogs`
2. Check discord.py version: `[p]debuginfo`
3. Review logs: `[p]debug bot.get_cog("ModalPatch")`

For bugs or feature requests, open an issue at the asdas-cogs repository.
