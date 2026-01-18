"""
ModalPatch - Demonstrates discord.py 2.6+ Modal Select and Label support

This cog demonstrates the proper use of discord.ui.Label and discord.ui.Select
in modals, which is officially supported as of discord.py 2.6.0.

Note: As of discord.py 2.6, Select components can be used in modals when
wrapped in Label components. TextInput.label is deprecated in favor of
using discord.ui.Label.

Requirements:
- discord.py >= 2.6.0
- Red-DiscordBot >= 3.5.0
"""

import discord
from discord.ui import Modal, Select, Label, TextInput
from redbot.core import commands
import logging
from typing import Any, Optional

log = logging.getLogger("red.asdas-cogs.modalpatch")


class ModalPatch(commands.Cog):
    """Demonstrates Select components in discord.py Modals using Labels"""

    def __init__(self, bot):
        self.bot = bot
        log.info("ModalPatch cog initialized - discord.py 2.6+ Label/Select support")

    @commands.command()
    @commands.is_owner()
    async def modalpatchstatus(self, ctx):
        """Check discord.py version and Label/Select modal support"""
        version = discord.__version__
        version_parts = version.split('.')

        try:
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0

            has_label = hasattr(discord.ui, 'Label')

            if major > 2 or (major == 2 and minor >= 6):
                status = "✅ **Compatible**"
                message = (
                    f"{status}\n"
                    f"discord.py version: `{version}`\n"
                    f"Label support: {'✅ Available' if has_label else '⚠️ Not detected'}\n\n"
                    f"Select components can be used in modals when wrapped in Label components."
                )
            else:
                status = "❌ **Incompatible**"
                message = (
                    f"{status}\n"
                    f"discord.py version: `{version}`\n"
                    f"Required version: `2.6.0` or higher\n\n"
                    f"Please update discord.py to use Select components in modals."
                )
        except (ValueError, IndexError):
            message = f"⚠️ Could not parse discord.py version: `{version}`"

        await ctx.send(message)

    @commands.command()
    @commands.is_owner()
    async def modalpatchtest(self, ctx):
        """Test modal with Label-wrapped Select and TextInput components"""

        # Check if Label is available
        if not hasattr(discord.ui, 'Label'):
            await ctx.send(
                "❌ **Error**: discord.ui.Label not available.\n"
                "This feature requires discord.py 2.6.0 or higher.\n"
                f"Current version: `{discord.__version__}`"
            )
            return

        class TestModal(Modal, title="Modal Select Test (discord.py 2.6+)"):
            """Test modal with Label-wrapped components"""

            def __init__(self):
                super().__init__()

                # Create a TextInput (no label parameter, using Label wrapper)
                name_input = TextInput(
                    placeholder="Enter your name...",
                    required=False,
                    max_length=50,
                    custom_id="name_input"
                )

                # Wrap TextInput in Label
                name_label = Label(
                    label="Your Name",
                    component=name_input
                )
                self.add_item(name_label)

                # Create a Select menu
                color_select = Select(
                    placeholder="Choose your favorite color",
                    options=[
                        discord.SelectOption(label="Red", value="red", emoji="🔴"),
                        discord.SelectOption(label="Blue", value="blue", emoji="🔵"),
                        discord.SelectOption(label="Green", value="green", emoji="🟢"),
                        discord.SelectOption(label="Yellow", value="yellow", emoji="🟡"),
                    ],
                    custom_id="color_select"
                )

                # Wrap Select in Label (required for modals)
                color_label = Label(
                    label="Favorite Color",
                    description="Select your favorite color from the dropdown",
                    component=color_select
                )
                self.add_item(color_label)

                # Store references for callback access
                self.name_input = name_input
                self.color_select = color_select

            async def on_submit(self, interaction: discord.Interaction):
                """Handle modal submission"""
                name_value = self.name_input.value or "Anonymous"

                # Get selected color
                try:
                    if hasattr(self.color_select, 'values') and self.color_select.values:
                        color_value = self.color_select.values[0]
                        emoji_map = {"red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡"}
                        emoji = emoji_map.get(color_value, "")

                        message = (
                            f"✅ **Success!**\n\n"
                            f"**Name:** {name_value}\n"
                            f"**Color:** {emoji} {color_value.capitalize()}\n\n"
                            f"_Select components work in modals with discord.py 2.6+_"
                        )
                    else:
                        message = (
                            f"⚠️ **Partial Success**\n\n"
                            f"**Name:** {name_value}\n"
                            f"**Color:** No selection detected\n\n"
                            f"The select component may not have been properly submitted."
                        )
                except Exception as e:
                    message = (
                        f"❌ **Error**\n\n"
                        f"**Name:** {name_value}\n"
                        f"**Error:** {str(e)}\n\n"
                        f"Something went wrong processing the select component."
                    )
                    log.error(f"Modal submission error: {e}", exc_info=True)

                await interaction.response.send_message(message, ephemeral=True)

        # Create a view with a button that opens the modal
        class ModalButton(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)

            @discord.ui.button(label="Open Test Modal", style=discord.ButtonStyle.primary, emoji="📝")
            async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = TestModal()
                await interaction.response.send_modal(modal)

        view = ModalButton()
        await ctx.send(
            "**Modal Select Test** (discord.py 2.6+)\n\n"
            "This modal demonstrates:\n"
            "• TextInput wrapped in Label\n"
            "• Select menu wrapped in Label\n\n"
            "Click the button below to open the test modal:",
            view=view
        )

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        log.info("ModalPatch cog unloaded")
