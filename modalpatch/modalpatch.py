"""
ModalPatch - Experimental monkey-patch for discord.py Modal Select support

This cog patches discord.py's Modal class to enable Select components,
which are supported in discord.js but not officially in discord.py.

WARNING: This is experimental and may break if:
1. Discord's API rejects select components in modals
2. discord.py updates change Modal implementation
3. Other cogs depend on original Modal behavior
"""

import discord
from discord.ui import Modal, Select
from redbot.core import commands
import logging
from typing import Any, Optional

log = logging.getLogger("red.asdas-cogs.modalpatch")


class ModalPatch(commands.Cog):
    """Experimental patch to enable Select components in discord.py Modals"""

    def __init__(self, bot):
        self.bot = bot
        self._original_modal_refresh = None
        self._patched = False
        self._apply_patch()

    def _apply_patch(self):
        """Apply monkey-patch to discord.ui.Modal"""
        if self._patched:
            log.warning("Modal patch already applied, skipping")
            return

        try:
            # Store original _refresh method
            self._original_modal_refresh = Modal._refresh

            # Create patched _refresh method
            def patched_refresh(modal_self, components):
                """
                Patched _refresh to handle both TextInput (type 4) and Select components (types 3, 5-8)

                Component types:
                - 4: TextInput (officially supported)
                - 3: String Select
                - 5: User Select
                - 6: Role Select
                - 7: Mentionable Select
                - 8: Channel Select
                """
                for component in components:
                    if component['type'] == 1:  # Action Row
                        for child in component.get('components', []):
                            custom_id = child.get('custom_id')
                            component_type = child.get('type')

                            if custom_id is None:
                                continue

                            # Find the matching child in the modal
                            for item in modal_self.children:
                                if item.custom_id != custom_id:
                                    continue

                                # Handle TextInput (type 4) - original behavior
                                if component_type == 4:
                                    item.value = child.get('value')

                                # Handle Select components (types 3, 5-8) - NEW
                                elif component_type in (3, 5, 6, 7, 8) and isinstance(item, discord.ui.Select):
                                    # Select components return 'values' array instead of 'value' string
                                    selected_values = child.get('values', [])
                                    if selected_values:
                                        # Update the select's values
                                        item.values = selected_values
                                        # Also set a 'value' attribute for easier access (first selected value)
                                        item.value = selected_values[0] if len(selected_values) == 1 else selected_values

                                break

            # Apply the patch
            Modal._refresh = patched_refresh
            self._patched = True
            log.info("Successfully patched discord.ui.Modal to support Select components")

        except Exception as e:
            log.error(f"Failed to apply Modal patch: {e}", exc_info=True)
            raise

    def _remove_patch(self):
        """Remove monkey-patch and restore original Modal behavior"""
        if not self._patched:
            return

        try:
            if self._original_modal_refresh:
                Modal._refresh = self._original_modal_refresh
                self._patched = False
                log.info("Successfully removed Modal patch, restored original behavior")
        except Exception as e:
            log.error(f"Failed to remove Modal patch: {e}", exc_info=True)

    @commands.command()
    @commands.is_owner()
    async def modalpatchstatus(self, ctx):
        """Check if the Modal patch is active"""
        if self._patched:
            await ctx.send(
                "✅ Modal patch is **ACTIVE**\n"
                "Select components should work in Modals.\n\n"
                "**Note:** This is experimental. Discord's API may still reject select components."
            )
        else:
            await ctx.send(
                "❌ Modal patch is **NOT ACTIVE**\n"
                "Select components will not work in Modals."
            )

    @commands.command()
    @commands.is_owner()
    async def modalpatchtest(self, ctx):
        """Test the Modal patch with a sample modal containing a select menu"""

        class TestModal(discord.ui.Modal, title="Modal Select Test"):
            """Test modal with a select component"""

            # Regular text input (always supported)
            name = discord.ui.TextInput(
                label="Your Name",
                placeholder="Enter your name...",
                required=False,
                max_length=50
            )

            # Select menu (requires patch)
            # Note: We create this in __init__ because Select needs to be added via add_item
            def __init__(self):
                super().__init__()

                # Add a string select menu
                self.color_select = discord.ui.Select(
                    placeholder="Choose your favorite color",
                    options=[
                        discord.SelectOption(label="Red", value="red", emoji="🔴"),
                        discord.SelectOption(label="Blue", value="blue", emoji="🔵"),
                        discord.SelectOption(label="Green", value="green", emoji="🟢"),
                        discord.SelectOption(label="Yellow", value="yellow", emoji="🟡"),
                    ],
                    custom_id="color_select"
                )
                self.add_item(self.color_select)

            async def on_submit(self, interaction: discord.Interaction):
                """Handle modal submission"""
                name_value = self.name.value or "Anonymous"

                # Try to get the selected color
                try:
                    if hasattr(self.color_select, 'values') and self.color_select.values:
                        color_value = self.color_select.values[0]
                        message = f"✅ **Patch Working!**\n\nName: {name_value}\nColor: {color_value}"
                    elif hasattr(self.color_select, 'value') and self.color_select.value:
                        color_value = self.color_select.value
                        message = f"✅ **Patch Working!**\n\nName: {name_value}\nColor: {color_value}"
                    else:
                        message = f"⚠️ **Partial Success**\n\nName: {name_value}\nColor: No selection received (API may have rejected select component)"
                except Exception as e:
                    message = f"❌ **Patch Failed**\n\nName: {name_value}\nError: {str(e)}"

                await interaction.response.send_message(message, ephemeral=True)

        # Send the modal
        await ctx.send("Opening test modal... Check your DMs or look for the modal popup!")

        # Create a view with a button that opens the modal
        class ModalButton(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)

            @discord.ui.button(label="Open Test Modal", style=discord.ButtonStyle.primary, emoji="📝")
            async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = TestModal()
                await interaction.response.send_modal(modal)

        view = ModalButton()
        await ctx.send("Click the button below to open the test modal:", view=view)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self._remove_patch()
        log.info("ModalPatch cog unloaded")
