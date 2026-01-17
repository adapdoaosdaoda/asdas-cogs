# ModalPatch Quick Start Guide

## 🚀 Installation (2 minutes)

```bash
# 1. Add the repo (if not already added)
[p]repo add asdas-cogs https://github.com/adapdoaosdaoda/asdas-cogs

# 2. Install the cog
[p]cog install asdas-cogs modalpatch

# 3. Load it (BEFORE other cogs that use modals)
[p]load modalpatch

# 4. Verify it's working
[p]modalpatchstatus
```

## ✅ Test It

```bash
[p]modalpatchtest
```

Click the button, fill out the modal with both text and select menu, submit. If you see both values, it works! 🎉

## 💻 Use It In Your Cog

### Minimal Example

```python
import discord
from discord.ui import Modal, TextInput, Select

class MyModal(Modal, title="My Form"):
    # Text input (always works)
    name = TextInput(label="Name")

    def __init__(self):
        super().__init__()

        # Select menu (needs ModalPatch)
        self.color = Select(
            placeholder="Pick a color",
            options=[
                discord.SelectOption(label="Red", value="red"),
                discord.SelectOption(label="Blue", value="blue"),
            ],
            custom_id="color"
        )
        self.add_item(self.color)

    async def on_submit(self, interaction):
        name = self.name.value
        color = self.color.values[0]  # First selected value

        await interaction.response.send_message(
            f"Hello {name}! You chose {color}.",
            ephemeral=True
        )

# Usage in a command
@commands.command()
async def myform(self, ctx):
    # Create button that opens modal
    class OpenButton(discord.ui.View):
        @discord.ui.button(label="Open Form")
        async def open(self, interaction, button):
            await interaction.response.send_modal(MyModal())

    await ctx.send("Click to open:", view=OpenButton())
```

## 🔍 Common Patterns

### String Select (Dropdown)

```python
self.choice = Select(
    placeholder="Choose an option",
    options=[
        discord.SelectOption(label="Option 1", value="opt1", emoji="1️⃣"),
        discord.SelectOption(label="Option 2", value="opt2", emoji="2️⃣"),
    ],
    custom_id="choice"
)
self.add_item(self.choice)

# In on_submit:
selected = self.choice.values[0]
```

### User Select

```python
self.user = discord.ui.UserSelect(
    placeholder="Pick a user",
    custom_id="user"
)
self.add_item(self.user)

# In on_submit:
user_id = self.user.values[0]  # Discord user ID
```

### Role Select

```python
self.role = discord.ui.RoleSelect(
    placeholder="Pick a role",
    custom_id="role"
)
self.add_item(self.role)

# In on_submit:
role_id = self.role.values[0]  # Discord role ID
```

### Channel Select

```python
self.channel = discord.ui.ChannelSelect(
    placeholder="Pick a channel",
    custom_id="channel"
)
self.add_item(self.channel)

# In on_submit:
channel_id = self.channel.values[0]  # Discord channel ID
```

### Multiple Selections

```python
self.roles = discord.ui.RoleSelect(
    placeholder="Pick roles",
    min_values=1,
    max_values=3,
    custom_id="roles"
)
self.add_item(self.roles)

# In on_submit:
role_ids = self.roles.values  # List of role IDs
```

## 🎨 Full-Featured Example

```python
class EventSignupModal(Modal, title="Event Signup"):
    # Text inputs
    character_name = TextInput(
        label="Character Name",
        placeholder="Enter your character name...",
        max_length=50
    )

    notes = TextInput(
        label="Additional Notes",
        style=discord.TextStyle.paragraph,
        placeholder="Any special requests?",
        required=False,
        max_length=500
    )

    def __init__(self):
        super().__init__()

        # Event type select
        self.event_type = Select(
            placeholder="Choose event type",
            options=[
                discord.SelectOption(
                    label="Hero's Realm",
                    value="heros_realm",
                    emoji="⚔️",
                    description="PvE dungeon"
                ),
                discord.SelectOption(
                    label="Sword Trial",
                    value="sword_trial",
                    emoji="🗡️",
                    description="Solo challenge"
                ),
                discord.SelectOption(
                    label="Party",
                    value="party",
                    emoji="🎉",
                    description="Social event"
                ),
            ],
            custom_id="event_type"
        )
        self.add_item(self.event_type)

        # Role select
        self.role = discord.ui.RoleSelect(
            placeholder="Select your preferred role",
            custom_id="role"
        )
        self.add_item(self.role)

    async def on_submit(self, interaction: discord.Interaction):
        char_name = self.character_name.value
        event = self.event_type.values[0]
        role = self.role.values[0] if self.role.values else None
        notes = self.notes.value or "None"

        embed = discord.Embed(
            title="✅ Signup Confirmed",
            color=discord.Color.green()
        )
        embed.add_field(name="Character", value=char_name)
        embed.add_field(name="Event", value=event)
        embed.add_field(name="Role", value=f"<@&{role}>" if role else "Not selected")
        embed.add_field(name="Notes", value=notes, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
```

## ❓ Troubleshooting

### Modal shows but select is empty
- Discord's API might be rejecting it
- Check `[p]modalpatchstatus`
- Try `[p]reload modalpatch`

### Values are None after submit
- Discord rejected the select component
- Check bot logs for errors
- Fall back to View-based approach

### Error on cog load
- Check discord.py version compatibility
- Look for conflicting cogs
- Check bot logs

### Select not appearing in modal
- Ensure ModalPatch is loaded: `[p]cog list`
- Load order: ModalPatch must load first
- Verify with: `[p]modalpatchtest`

## 📚 Next Steps

- Read [README.md](README.md) for full documentation
- Check [IMPLEMENTATION.md](IMPLEMENTATION.md) for technical details
- Review [test_modalpatch.py](test_modalpatch.py) for test examples

## ⚠️ Important Reminders

1. **Load ModalPatch FIRST** before cogs that use modals
2. **Test with `[p]modalpatchtest`** before deploying
3. **Monitor bot logs** for Discord API rejections
4. **Have fallback** to View-based approach
5. **Update regularly** - check for new versions

## 🆘 Getting Help

- Check logs: `[p]logs`
- Test patch: `[p]modalpatchtest`
- Status: `[p]modalpatchstatus`
- Report issues on GitHub

Happy modal building! 🎉
