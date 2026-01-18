# MonkeyModal

A robust utility cog for creating "Modern Modals" with Discord API v10 components.

## Overview

MonkeyModal acts as a shared service allowing other cogs to create and await modals containing Select Menus and other Discord API v10 components that are not yet natively supported in discord.py. It bypasses discord.py's validation by making raw API calls, providing a clean, Pythonic interface for building complex modals and awaiting user submissions.

## Features

- **ModalBuilder**: Fluent API for constructing modal payloads
- **All API v10 Component Types**:
  - Type 4: Text Input (SHORT and PARAGRAPH styles)
  - Type 3: String Select (dropdowns with custom options)
  - Type 5: User Select (select Discord users)
  - Type 6: Role Select (select server roles)
  - Type 7: Mentionable Select (select users or roles)
  - Type 8: Channel Select (with optional type filters)
- **Raw API Bypass**: Sends modals directly via `bot.http.request` to avoid discord.py validation
- **Future-Based Awaiting**: Clean async/await pattern for receiving modal submissions
- **Automatic Parsing**: Extracts and formats submission data based on component type

## Installation

```
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs
[p]cog install asdas-cogs monkeymodal
[p]load monkeymodal
```

## Usage for Developers

### Basic Example

```python
@commands.command()
async def example(self, ctx):
    """Example command that uses MonkeyModal"""
    # Get the MonkeyModal cog
    monkey_cog = self.bot.get_cog("MonkeyModal")
    if not monkey_cog:
        await ctx.send("MonkeyModal is not loaded!")
        return

    # Create a view with a button that opens the modal
    class ModalButton(discord.ui.View):
        @discord.ui.button(label="Open Modal", style=discord.ButtonStyle.primary)
        async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Build the modal
            builder = monkey_cog.create_builder("my_modal", "My Modal Title")

            builder.add_text_input(
                "name",
                "Your Name",
                placeholder="Enter your name...",
                max_length=50
            )

            builder.add_role_select(
                "role",
                placeholder="Pick a role",
                max_values=3
            )

            # Send modal and await response
            result = await monkey_cog.prompt(interaction, builder, timeout=300)

            if result:
                name = result.get("name", "Unknown")
                roles = result.get("role", [])
                await interaction.followup.send(
                    f"Name: {name}\nRoles: {', '.join(roles)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("Modal timed out", ephemeral=True)

    view = ModalButton()
    await ctx.send("Click to open the modal:", view=view)
```

### Component Types

#### Text Input

```python
builder.add_text_input(
    custom_id="field_id",
    label="Field Label",
    style=1,  # 1=SHORT, 2=PARAGRAPH
    placeholder="Optional placeholder...",
    value="Optional pre-filled value",
    required=True,
    min_length=1,
    max_length=100
)
```

#### String Select

```python
builder.add_string_select(
    custom_id="color",
    options=[
        {"label": "Red", "value": "red", "emoji": {"name": "🔴"}},
        {"label": "Blue", "value": "blue", "description": "The color blue"}
    ],
    placeholder="Pick a color",
    min_values=1,
    max_values=2
)
```

#### User Select

```python
builder.add_user_select(
    custom_id="users",
    placeholder="Select users",
    min_values=1,
    max_values=5,
    default_values=[{"id": "123456789", "type": "user"}]  # Optional
)
```

#### Role Select

```python
builder.add_role_select(
    custom_id="roles",
    placeholder="Select roles",
    min_values=1,
    max_values=10
)
```

#### Mentionable Select

```python
builder.add_mentionable_select(
    custom_id="mentions",
    placeholder="Select users or roles",
    min_values=1,
    max_values=5
)
```

#### Channel Select

```python
from discord import ChannelType

builder.add_channel_select(
    custom_id="channels",
    placeholder="Select text channels",
    channel_types=[ChannelType.text, ChannelType.voice],  # Filter by type
    min_values=1,
    max_values=3
)
```

### Return Data Format

The `prompt()` method returns a dictionary mapping `custom_id` to parsed values:

```python
{
    'name': 'John Doe',              # Text input: string value
    'color': ['red'],                 # String select: list of values
    'users': ['123456789'],           # User select: list of user IDs
    'roles': ['987654321'],           # Role select: list of role IDs
    'channels': ['555666777']         # Channel select: list of channel IDs
}
```

Returns `None` if the modal times out.

## API Reference

### `MonkeyModal.create_builder(custom_id: str, title: str) -> ModalBuilder`

Create a new ModalBuilder instance.

**Parameters:**
- `custom_id`: Unique identifier for the modal (used to match submissions)
- `title`: Display title shown at the top of the modal

**Returns:** `ModalBuilder` instance

### `MonkeyModal.prompt(interaction, modal_builder, timeout=300.0) -> Optional[Dict]`

Send a modal and await the user's submission.

**Parameters:**
- `interaction`: The interaction to respond to with a modal
- `modal_builder`: ModalBuilder instance with the modal components
- `timeout`: Seconds to wait for submission (default: 300 = 5 minutes)

**Returns:** Dictionary mapping custom_id to parsed values, or None if timed out

**Raises:** `discord.HTTPException` if sending the modal fails

### `MonkeyModal.send_modal(interaction, modal_builder) -> None`

Send a modal without awaiting (for advanced use cases).

**Parameters:**
- `interaction`: The interaction to respond to with a modal
- `modal_builder`: ModalBuilder instance with the modal components

**Raises:** `discord.HTTPException` if the API request fails

## Component Type Reference

| Type | Name | Description |
|------|------|-------------|
| 1 | Action Row | Container for components (added automatically) |
| 2 | Button | Not supported in modals |
| 3 | String Select | Dropdown with custom options |
| 4 | Text Input | Text field (SHORT or PARAGRAPH) |
| 5 | User Select | Select Discord users |
| 6 | Role Select | Select server roles |
| 7 | Mentionable Select | Select users or roles |
| 8 | Channel Select | Select channels (with optional type filter) |

## Testing

The cog includes a comprehensive test suite. Install test dependencies and run:

```bash
pip install -r asdas-cogs/tests/requirements.txt
python3 -m pytest asdas-cogs/monkeymodal/test_monkeymodal.py -v
```

## End User Commands

### `[p]monkeymodaltest`

Test the MonkeyModal system with a comprehensive modal containing:
- Text Input
- String Select (colors)
- Role Select
- Channel Select

Requires bot owner permissions.

## Technical Details

### How It Works

1. **Building**: `ModalBuilder` constructs a JSON payload matching Discord's API v10 specification
2. **Sending**: `send_modal()` uses `bot.http.request` to POST to `/interactions/{id}/{token}/callback` with type 9 (MODAL)
3. **Awaiting**: `prompt()` registers an `asyncio.Future` in `pending_modals` dict
4. **Listening**: `on_interaction` listener catches modal_submit interactions
5. **Parsing**: `_parse_modal_data()` extracts values based on component type
6. **Resolving**: Future is resolved with parsed data, completing the await

### Why Bypass discord.py?

discord.py has built-in validation that prevents using certain component types (like Select menus) in modals, even though Discord's API v10 supports them. By making raw API calls, MonkeyModal bypasses this validation while maintaining a clean, Pythonic interface.

### Future Compatibility

If discord.py adds native support for these components in the future, you can migrate away from MonkeyModal by:
1. Replacing `ModalBuilder` with `discord.ui.Modal` subclasses
2. Using `interaction.response.send_modal()` instead of `monkey_cog.prompt()`
3. Unloading the MonkeyModal cog

## Support

For issues, questions, or feature requests, please open an issue at:
https://github.com/adapdoaosdaoda/asdas-cogs/issues
