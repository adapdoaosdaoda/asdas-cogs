import logging
import discord
from discord.ui import Modal, Item, TextInput, View

# --- Compatibility Shim Start ---
try:
    # Attempt to import modern components (discord.py 2.3+)
    from discord.ui import StringSelect, string_select
except ImportError:
    # Fallback for legacy components (discord.py 2.0 - 2.2)
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
        pass

    def refresh_state(self, interaction: discord.Interaction) -> None:
        pass


class Label(Item):
    """
    Represents a Label wrapper component (Type 18).
    Schema: type: 18, label (str), component (object).
    Used for Auto-Boxing Selects.
    """
    def __init__(self, label: str, child: Item, description: Optional[str] = None):
        super().__init__()
        self.label = label
        self.child = child
        self.description = description
        self._row = None

    @property
    def type(self) -> discord.ComponentType:
        return discord.ComponentType(18) # Type 18 is the V2 Container for Selects

    def to_component_dict(self) -> Dict[str, Any]:
        child_payload = self.child.to_component_dict()
        
        # Check if child is optional (min_values == 0)
        # Default to 1 if attribute missing
        is_optional = getattr(self.child, 'min_values', 1) == 0

        # Sanitize: Remove disabled fields from Selects inside Modals
        if isinstance(self.child, (StringSelect, RoleSelect, ChannelSelect, UserSelect, MentionableSelect)):
            child_payload.pop("disabled", None)

        payload = {
            "type": 18,
            "label": self.label or " ", 
            # FIX: Changed from 'components' (list) to 'component' (singular object)
            "component": child_payload
        }
        
        # Propagate optional state to the Label wrapper (Type 18)
        # This fixes the UI showing "Required" asterisk even when min_values=0
        if is_optional:
            payload["required"] = False
        
        if self.description:
            payload["description"] = self.description
            
        return payload

    def refresh_component(self, component: Any) -> None:
        pass

    def refresh_state(self, interaction: discord.Interaction) -> None:
        pass


# ==============================================================================
# Monkey-Patching Logic
# ==============================================================================

_original_add_item = Modal.add_item
_original_to_dict = Modal.to_dict
_original_refresh = getattr(Modal, "_refresh", None)

def _patched_add_item(self, item: Item):
    """
    Patched add_item to allow Selects, TextDisplay, and Label.
    """
    if isinstance(item, TextInput):
        return _original_add_item(self, item)
    
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
            label_text = getattr(item, 'placeholder', None) or "Select Option"
            
            # Create a temporary Label wrapper just for serialization
            wrapper = Label(label=label_text, child=item)
            payload['components'].append(wrapper.to_component_dict())
            
        elif isinstance(item, TextDisplay):
            # Serialize TextDisplay directly (Type 10)
            payload['components'].append(item.to_component_dict())
            
        elif isinstance(item, TextInput):
            # Standard TextInput must be wrapped in ActionRow (Type 1)
            payload['components'].append({
                'type': 1,
                'components': [item.to_component_dict()]
            })
        else:
            payload['components'].append(item.to_component_dict())

    return payload

def _patched_refresh(self, interaction: discord.Interaction, components: List[Dict[str, Any]] = None):
    """
    Patched hydration loop to handle new component types.
    """
    if components is None:
        components = interaction.data.get('components', [])
    
    flat_components = []
    for row in components:
        if row['type'] == 1: # ActionRow
            flat_components.extend(row.get('components', []))
        
        elif row['type'] == 18: # Label (Type 18) unwrapping
            # The interaction response returns the inner component in 'component'
            if 'component' in row:
                flat_components.append(row['component'])
                
        elif row['type'] == 10: # TextDisplay
            if 'components' in row:
                flat_components.extend(row.get('components', []))
    
    # Map custom_id to component data
    component_map = {c['custom_id']: c for c in flat_components if 'custom_id' in c}

    def update_item_state(item):
        if isinstance(item, TextDisplay):
            return
            
        # If item is a Label, update its child instead
        if isinstance(item, Label):
            update_item_state(item.child)
            return

        # Handle Selects
        if isinstance(item, (StringSelect, RoleSelect, ChannelSelect, UserSelect, MentionableSelect)):
            c_data = component_map.get(item.custom_id)
            if c_data and 'values' in c_data:
                item._values = c_data['values']
                try:
                    item.refresh_state(interaction) 
                except Exception:
                    pass
            return

        # Handle TextInputs (Standard)
        if isinstance(item, TextInput):
            c_data = component_map.get(item.custom_id)
            if c_data and 'value' in c_data:
                item._value = c_data['value']
            return

    for item in self._children:
        update_item_state(item)

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
            style=1 
        )
        self.add_item(self.header)

        # 2. Body: RoleSelect (Auto-boxed)
        self.role_select = RoleSelect(
            placeholder="Select a Role",
            min_values=1,
            max_values=1,
            custom_id="test_role_select"
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
        selected_role_ids = []
        if self.role_select.values:
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
            # Inject Classes into discord.ui (Force update to ensure latest version)
            setattr(discord.ui, 'TextDisplay', TextDisplay)
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
            
            log.info("ModalPatch: Successfully reverted runtime patches.")
        except Exception as e:
            log.error(f"ModalPatch: Failed to revert patches: {e}", exc_info=True)

    @commands.command(name="modal_test")
    @commands.is_owner()
    async def modal_test(self, ctx: commands.Context):
        """
        Launches the modal via a button bridge.
        """
        view = ModalLauncher()
        await ctx.send("To access the modal, please click the button below:", view=view)