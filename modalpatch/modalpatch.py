import logging
import discord
from discord.ui import Modal, Item, TextInput, View

# --- Compatibility Shim Start ---
try:
    # Attempt to import modern components (discord.py 2.3+)
    from discord.ui import StringSelect, string_select
except ImportError:
    # Fallback for legacy components (discord.py 2.0 - 2.2)
    # In these versions, 'Select' is the class for String Selects.
    # We alias it to 'StringSelect' to maintain forward compatibility.
    from discord.ui import Select as StringSelect
    from discord.ui import select as string_select
# --- Compatibility Shim End ---

# Safe access to the component type enum
try:
    # Modern naming
    STRING_SELECT_TYPE = discord.ComponentType.string_select
except AttributeError:
    # Legacy naming (Both map to value 3)
    STRING_SELECT_TYPE = discord.ComponentType.select

# Import all Select types to ensure availability
from discord.ui import (
    RoleSelect,
    ChannelSelect,
    UserSelect,
    MentionableSelect,
)
from redbot.core import commands, app_commands
from typing import List, Dict, Any, Optional

log = logging.getLogger("red.modalpatch")

# ==============================================================================
# Missing Component Definitions (Schema Implementation)
# ==============================================================================

class TextDisplay(Item):
    """
    Represents a TextDisplay component (Type 10).
    Schema: type: 10, content (str), style (int).
    """
    def __init__(self, content: str, style: int = 1, row: Optional[int] = None):
        super().__init__()
        self.content = content
        self.style = style
        self._row = row
        self._rendered_row = None

    @property
    def type(self) -> discord.ComponentType:
        return discord.ComponentType(10)

    def to_component_dict(self) -> Dict[str, Any]:
        return {
            "type": 10,
            "content": self.content,
            "style": self.style,
        }

    def refresh_component(self, component: Any) -> None:
        # TextDisplay has no state to refresh from interaction
        pass

    def refresh_state(self, interaction: discord.Interaction) -> None:
        pass


class Label(Item):
    """
    Represents a Label wrapper component (Type 10).
    Schema: type: 10, label (str), components (list of 1 child).
    Used for Auto-Boxing Selects.
    """
    def __init__(self, label: str, child: Item):
        super().__init__()
        self.label = label
        self.child = child
        self._row = None

    @property
    def type(self) -> discord.ComponentType:
        return discord.ComponentType(10)

    def to_component_dict(self) -> Dict[str, Any]:
        child_payload = self.child.to_component_dict()
        
        # Sanitize: Remove disabled fields from Selects inside Modals
        if isinstance(self.child, (StringSelect, RoleSelect, ChannelSelect, UserSelect, MentionableSelect)):
            child_payload.pop("disabled", None)

        return {
            "type": 10,
            "label": self.label,
            "content": " ",
            "components": [child_payload]
        }

    def refresh_component(self, component: Any) -> None:
        pass

    def refresh_state(self, interaction: discord.Interaction) -> None:
        pass


# ==============================================================================
# Monkey-Patching Logic
# ==============================================================================

_original_add_item = Modal.add_item
_original_to_dict = Modal.to_dict
_original_refresh = getattr(Modal, "_refresh", None) # Safe access in case name changes, though prompt implies it exists

def _patched_add_item(self, item: Item):
    """
    Patched add_item to allow Selects, TextDisplay, and Label.
    Bypasses strict TextInput type checking for these items.
    """
    if isinstance(item, TextInput):
        return _original_add_item(self, item)
    
    # Validation logic mimicked from original but expanded
    if len(self._children) >= 5:
        raise ValueError('Modal cannot have more than 5 items')
    
    if not isinstance(item, Item):
        raise TypeError(f'expected Item not {item.__class__!r}')
    
    self._children.append(item)
    return self

def _patched_to_dict(self):
    """
    Patched serialization to handle Auto-Boxing of Selects and strict Schema compliance.
    """
    payload = {
        'title': self.title,
        'custom_id': self.custom_id,
        'components': [],
    }

    for item in self._children:
        if isinstance(item, (StringSelect, RoleSelect, ChannelSelect, UserSelect, MentionableSelect)):
            # Auto-Boxing: Wrap Select in Label
            # Using a default label if one isn't clearly associated, or empty string.
            # The prompt implies the Select acts as the body. 
            # We wrap it in the Label structure as requested.
            # Using the placeholder as the label if available, else generic.
            label_text = getattr(item, 'placeholder', None) or "Select Option"
            
            # Create a temporary Label wrapper just for serialization
            wrapper = Label(label=label_text, child=item)
            payload['components'].append(wrapper.to_component_dict())
            
        elif isinstance(item, TextDisplay):
            # Serialize TextDisplay directly (Type 10)
            payload['components'].append(item.to_component_dict())
            
        elif isinstance(item, TextInput):
            # Standard TextInput (usually wrapped in ActionRow Type 1 by default library behavior)
            # discord.py's TextInput.to_component_dict returns Type 4. 
            # Modals expect ActionRow(TextInput). 
            # We must wrap TextInput in ActionRow (Type 1) as discord.py usually does.
            payload['components'].append({
                'type': 1,
                'components': [item.to_component_dict()]
            })
        else:
            # Fallback for other items (like the Label class if added directly)
            payload['components'].append(item.to_component_dict())

    return payload

async def _patched_refresh(self, interaction: discord.Interaction):
    """
    Patched hydration loop to handle new component types.
    """
    # Get component data from interaction
    data = interaction.data
    components = data.get('components', [])
    
    # Flatten components from ActionRows/Labels for easier matching
    # Interaction data structure: 
    # Standard: list of ActionRows, each containing components.
    # Rich Modal (assumed): list of ActionRows OR Type 10 structures?
    # We need to flatten to find values by custom_id.
    
    flat_components = []
    for row in components:
        if row['type'] == 1: # ActionRow
            flat_components.extend(row.get('components', []))
        elif row['type'] == 10: # Label/TextDisplay structure in response?
            # If the response echoes the structure, we might find inner components here
            if 'components' in row:
                flat_components.extend(row.get('components', []))
            # If it's just a TextDisplay, it has no value, we ignore.
    
    # Map custom_id to component data
    component_map = {c['custom_id']: c for c in flat_components if 'custom_id' in c}

    for item in self._children:
        # Skip TextDisplay during hydration (no value)
        if isinstance(item, TextDisplay):
            continue
            
        # Handle Selects
        if isinstance(item, (StringSelect, RoleSelect, ChannelSelect, UserSelect, MentionableSelect)):
            # Selects in Modals return 'values'
            c_data = component_map.get(item.custom_id)
            if c_data and 'values' in c_data:
                # Update the item's values
                # We need to access the internal mechanism or refresh_state
                item._values = c_data['values']
                # Trigger callback if necessary or just update state
                # discord.py items usually update via refresh_state or similar
                try:
                    item.refresh_state(interaction) 
                except Exception:
                    # Manually set if refresh_state isn't standard on all versions for Selects in Modals
                    pass
            continue

        # Handle TextInputs (Standard)
        if isinstance(item, TextInput):
            c_data = component_map.get(item.custom_id)
            if c_data and 'value' in c_data:
                item._value = c_data['value']
                # refresh_state is handled by base usually, but we are overriding the loop
                continue

    # Call original or super logic? 
    # _refresh in discord.py is responsible for updating state before on_submit.
    # Since we replaced it, we are responsible for all state updates.
    pass

# ==============================================================================
# Cog Implementation
# ==============================================================================

class RichTestModal(Modal, title="Rich Modal Test"):
    def __init__(self):
        super().__init__()
        
        # 1. Header: TextDisplay
        self.header = TextDisplay(
            content="Please configure your role",
            style=1 # Primary/Blurple style if supported by client for TextDisplay
        )
        self.add_item(self.header)

        # 2. Body: RoleSelect (Auto-boxed)
        self.role_select = RoleSelect(
            placeholder="Select a Role",
            min_values=1,
            max_values=1,
            custom_id="test_role_select" # explicit ID
        )
        self.add_item(self.role_select)

        # 3. Footer: TextInput
        self.reason = TextInput(
            label="Reason",
            placeholder="Why are you selecting this?",
            custom_id="test_reason_input"
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        # Callback: Echo results
        selected_role_ids = []
        if self.role_select.values:
            # RoleSelect values are typically objects in some contexts or IDs in others depending on hydration
            # discord.py Selects usually hydrate .values with the selected strings/IDs
            selected_role_ids = self.role_select.values
        
        reason_val = self.reason.value

        await interaction.response.send_message(
            f"**Success!**\n"
            f"Selected Role IDs: `{selected_role_ids}`\n"
            f"Reason: `{reason_val}`",
            ephemeral=True
        )

class ModalLauncher(View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Open Form", style=discord.ButtonStyle.primary, emoji="📝")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        # The interaction from the button click carries the token needed for the Modal
        await interaction.response.send_modal(RichTestModal())

class ModalPatch(commands.Cog):
    """
    Cog to enable and manage Rich Modal patches.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._apply_patches()

    def cog_unload(self):
        self._revert_patches()

    def _apply_patches(self):
        try:
            # Inject Classes into discord.ui if missing
            if not hasattr(discord.ui, 'TextDisplay'):
                setattr(discord.ui, 'TextDisplay', TextDisplay)
            
            if not hasattr(discord.ui, 'Label'):
                setattr(discord.ui, 'Label', Label)

            # Apply Monkey Patches
            Modal.add_item = _patched_add_item
            Modal.to_dict = _patched_to_dict
            setattr(Modal, '_refresh', _patched_refresh)

            log.info("ModalPatch: Successfully applied runtime patches for API v10 Rich Modals.")
        except Exception as e:
            log.error(f"ModalPatch: Failed to apply patches: {e}", exc_info=True)

    def _revert_patches(self):
        try:
            # Revert Monkey Patches
            Modal.add_item = _original_add_item
            Modal.to_dict = _original_to_dict
            if _original_refresh:
                setattr(Modal, '_refresh', _original_refresh)
            
            # Note: We do not remove injected classes (TextDisplay, Label) to prevent 
            # import errors in other modules that might have imported them already,
            # but we restore the behavior of the core Modal class.
            
            log.info("ModalPatch: Successfully reverted runtime patches.")
        except Exception as e:
            log.error(f"ModalPatch: Failed to revert patches: {e}", exc_info=True)

    @commands.command(name="modal_test")
    @commands.is_owner()
    async def modal_test(self, ctx: commands.Context):
        """
        Launches the modal via a button bridge to ensure API v10 compliance.
        """
        view = ModalLauncher()
        await ctx.send("To access the modal, please click the button below:", view=view)
