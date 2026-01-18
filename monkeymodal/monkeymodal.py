"""
MonkeyModal - A robust utility cog for creating "Modern Modals" with Discord API v10 components

This cog acts as a shared service allowing other cogs to create and await modals containing
Select Menus and other Discord API v10 components that are not yet natively supported in discord.py.

The cog bypasses discord.py's validation by making raw API calls, allowing developers to build
modals with all API v10 component types and await user submissions in a clean, Pythonic way.

Requirements:
- Red-DiscordBot >= 3.5.0
- discord.py >= 2.0.0
"""

import discord
from discord import ChannelType
from redbot.core import commands
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union
from enum import IntEnum

log = logging.getLogger("red.asdas-cogs.monkeymodal")


class ComponentType(IntEnum):
    """Discord API v10 Component Types"""
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8


class TextInputStyle(IntEnum):
    """Discord API Text Input Styles"""
    SHORT = 1
    PARAGRAPH = 2


class ModalBuilder:
    """
    Fluent interface for building modal payloads with all Discord API v10 component types.

    Supports:
    - Type 4 (Text Input): Standard text fields
    - Type 3 (String Select): Standard dropdowns
    - Type 5 (User Select): Select specific users
    - Type 6 (Role Select): Select specific roles
    - Type 7 (Mentionable Select): Select users or roles
    - Type 8 (Channel Select): Select channels with optional type filters
    """

    def __init__(self, custom_id: str, title: str):
        """
        Initialize a new modal builder.

        Args:
            custom_id: Unique identifier for the modal (used to match submissions)
            title: Display title shown at the top of the modal
        """
        self.custom_id = custom_id
        self.title = title
        self.components: List[Dict[str, Any]] = []

    def _add_component_in_action_row(self, component: Dict[str, Any]) -> "ModalBuilder":
        """
        Wrap a component in an Action Row (Type 1) and add to the modal.

        Args:
            component: Component dictionary to wrap

        Returns:
            Self for method chaining
        """
        action_row = {
            "type": ComponentType.ACTION_ROW,
            "components": [component]
        }
        self.components.append(action_row)
        return self

    def add_text_input(
        self,
        custom_id: str,
        label: str,
        style: int = TextInputStyle.SHORT,
        placeholder: Optional[str] = None,
        value: Optional[str] = None,
        required: bool = True,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None
    ) -> "ModalBuilder":
        """
        Add a text input field (Type 4) to the modal.

        Args:
            custom_id: Unique identifier for this input
            label: Label displayed above the input
            style: 1 (SHORT) or 2 (PARAGRAPH)
            placeholder: Placeholder text when empty
            value: Pre-filled value
            required: Whether input is required
            min_length: Minimum character length
            max_length: Maximum character length

        Returns:
            Self for method chaining
        """
        component = {
            "type": ComponentType.TEXT_INPUT,
            "custom_id": custom_id,
            "label": label,
            "style": style,
            "required": required
        }

        if placeholder is not None:
            component["placeholder"] = placeholder
        if value is not None:
            component["value"] = value
        if min_length is not None:
            component["min_length"] = min_length
        if max_length is not None:
            component["max_length"] = max_length

        return self._add_component_in_action_row(component)

    def add_string_select(
        self,
        custom_id: str,
        options: List[Dict[str, Any]],
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False
    ) -> "ModalBuilder":
        """
        Add a string select menu (Type 3) to the modal.

        Args:
            custom_id: Unique identifier for this select
            options: List of option dicts with 'label', 'value', optional 'description', 'emoji'
            placeholder: Placeholder text when nothing selected
            min_values: Minimum number of selections
            max_values: Maximum number of selections
            disabled: Whether the select is disabled

        Returns:
            Self for method chaining

        Example options:
            [
                {"label": "Option 1", "value": "opt1", "description": "First option"},
                {"label": "Option 2", "value": "opt2", "emoji": {"name": "🔥"}}
            ]
        """
        component = {
            "type": ComponentType.STRING_SELECT,
            "custom_id": custom_id,
            "options": options,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder

        return self._add_component_in_action_row(component)

    def add_user_select(
        self,
        custom_id: str,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        default_values: Optional[List[Dict[str, str]]] = None
    ) -> "ModalBuilder":
        """
        Add a user select menu (Type 5) to the modal.

        Args:
            custom_id: Unique identifier for this select
            placeholder: Placeholder text when nothing selected
            min_values: Minimum number of selections
            max_values: Maximum number of selections
            disabled: Whether the select is disabled
            default_values: List of default selections [{"id": "user_id", "type": "user"}]

        Returns:
            Self for method chaining
        """
        component = {
            "type": ComponentType.USER_SELECT,
            "custom_id": custom_id,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder
        if default_values is not None:
            component["default_values"] = default_values

        return self._add_component_in_action_row(component)

    def add_role_select(
        self,
        custom_id: str,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        default_values: Optional[List[Dict[str, str]]] = None
    ) -> "ModalBuilder":
        """
        Add a role select menu (Type 6) to the modal.

        Args:
            custom_id: Unique identifier for this select
            placeholder: Placeholder text when nothing selected
            min_values: Minimum number of selections
            max_values: Maximum number of selections
            disabled: Whether the select is disabled
            default_values: List of default selections [{"id": "role_id", "type": "role"}]

        Returns:
            Self for method chaining
        """
        component = {
            "type": ComponentType.ROLE_SELECT,
            "custom_id": custom_id,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder
        if default_values is not None:
            component["default_values"] = default_values

        return self._add_component_in_action_row(component)

    def add_mentionable_select(
        self,
        custom_id: str,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        default_values: Optional[List[Dict[str, str]]] = None
    ) -> "ModalBuilder":
        """
        Add a mentionable select menu (Type 7) - allows selecting users or roles.

        Args:
            custom_id: Unique identifier for this select
            placeholder: Placeholder text when nothing selected
            min_values: Minimum number of selections
            max_values: Maximum number of selections
            disabled: Whether the select is disabled
            default_values: List of default selections [{"id": "...", "type": "user"|"role"}]

        Returns:
            Self for method chaining
        """
        component = {
            "type": ComponentType.MENTIONABLE_SELECT,
            "custom_id": custom_id,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder
        if default_values is not None:
            component["default_values"] = default_values

        return self._add_component_in_action_row(component)

    def add_channel_select(
        self,
        custom_id: str,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        channel_types: Optional[List[Union[ChannelType, int]]] = None,
        default_values: Optional[List[Dict[str, str]]] = None
    ) -> "ModalBuilder":
        """
        Add a channel select menu (Type 8) to the modal.

        Args:
            custom_id: Unique identifier for this select
            placeholder: Placeholder text when nothing selected
            min_values: Minimum number of selections
            max_values: Maximum number of selections
            disabled: Whether the select is disabled
            channel_types: List of ChannelType objects or integers to filter by
            default_values: List of default selections [{"id": "channel_id", "type": "channel"}]

        Returns:
            Self for method chaining

        Example channel_types:
            [ChannelType.text, ChannelType.voice]
            or
            [0, 2]  # Text and Voice channel types
        """
        component = {
            "type": ComponentType.CHANNEL_SELECT,
            "custom_id": custom_id,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder

        if channel_types is not None:
            # Convert ChannelType objects to integers
            component["channel_types"] = [
                ct.value if isinstance(ct, ChannelType) else ct
                for ct in channel_types
            ]

        if default_values is not None:
            component["default_values"] = default_values

        return self._add_component_in_action_row(component)

    def build(self) -> Dict[str, Any]:
        """
        Build the final modal payload for the Discord API.

        Returns:
            Complete modal payload dictionary
        """
        return {
            "title": self.title,
            "custom_id": self.custom_id,
            "components": self.components
        }


class MonkeyModal(commands.Cog):
    """
    A robust utility cog for creating and awaiting "Modern Modals" with Discord API v10 components.

    This cog acts as a shared service allowing other cogs to:
    1. Create modals with all API v10 component types (including selects)
    2. Send them by bypassing discord.py's validation
    3. Await user submissions in a clean, Pythonic way

    Other cogs can use this via:
        monkey_cog = bot.get_cog("MonkeyModal")
        builder = monkey_cog.create_builder("my_modal", "My Modal Title")
        builder.add_text_input("name", "Your Name")
        builder.add_role_select("role", placeholder="Pick a role")
        result = await monkey_cog.prompt(interaction, builder, timeout=300)
    """

    def __init__(self, bot):
        self.bot = bot
        self.pending_modals: Dict[str, asyncio.Future] = {}
        log.info("MonkeyModal cog initialized - raw API v10 modal support enabled")

    def create_builder(self, custom_id: str, title: str) -> ModalBuilder:
        """
        Create a new ModalBuilder instance.

        Args:
            custom_id: Unique identifier for the modal
            title: Display title for the modal

        Returns:
            ModalBuilder instance for fluent construction
        """
        return ModalBuilder(custom_id, title)

    async def send_modal(
        self,
        interaction: discord.Interaction,
        modal_builder: ModalBuilder
    ) -> None:
        """
        Send a modal to Discord using raw API calls, bypassing discord.py validation.

        This method constructs the INTERACTION_CALLBACK response with type 9 (MODAL)
        and sends it directly via bot.http.request.

        Args:
            interaction: The interaction to respond to with a modal
            modal_builder: ModalBuilder instance with the modal components

        Raises:
            discord.HTTPException: If the API request fails
        """
        payload = {
            "type": 9,  # MODAL callback type
            "data": modal_builder.build()
        }

        # Send raw API request to bypass discord.py's component validation
        route = f"/interactions/{interaction.id}/{interaction.token}/callback"

        try:
            await self.bot.http.request(
                discord.http.Route("POST", route),
                json=payload
            )
            log.debug(f"Modal sent successfully: {modal_builder.custom_id}")
        except discord.HTTPException as e:
            log.error(f"Failed to send modal {modal_builder.custom_id}: {e}", exc_info=True)
            raise

    async def prompt(
        self,
        interaction: discord.Interaction,
        modal_builder: ModalBuilder,
        timeout: float = 300.0
    ) -> Optional[Dict[str, Any]]:
        """
        Send a modal and await the user's submission.

        This is the main entry point for other cogs to use MonkeyModal.
        It sends the modal, registers a Future, and awaits the user's response.

        Args:
            interaction: The interaction to respond to with a modal
            modal_builder: ModalBuilder instance with the modal components
            timeout: Seconds to wait for submission (default: 300 = 5 minutes)

        Returns:
            Dictionary mapping custom_id to parsed values, or None if timed out

        Example return:
            {
                'role_select_id': ['123456789'],
                'reason_id': 'Because I said so',
                'users_id': ['111111111', '222222222']
            }

        Raises:
            discord.HTTPException: If sending the modal fails
        """
        custom_id = modal_builder.custom_id

        # Create a Future to await the submission
        future = asyncio.get_event_loop().create_future()
        self.pending_modals[custom_id] = future

        try:
            # Send the modal
            await self.send_modal(interaction, modal_builder)

            # Wait for the submission
            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            log.debug(f"Modal {custom_id} timed out after {timeout}s")
            return None
        finally:
            # Clean up the pending modal
            self.pending_modals.pop(custom_id, None)

    def _parse_modal_data(self, components: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parse the raw interaction data from a modal submission.

        Extracts values from different component types:
        - Type 4 (Text Input): Returns the string value
        - Type 3, 5, 6, 7, 8 (Selects): Returns list of selected IDs/values

        Args:
            components: Raw components list from interaction data

        Returns:
            Dictionary mapping custom_id to parsed values
        """
        result = {}

        for action_row in components:
            if action_row.get("type") != ComponentType.ACTION_ROW:
                continue

            for component in action_row.get("components", []):
                custom_id = component.get("custom_id")
                component_type = component.get("type")

                if not custom_id:
                    continue

                if component_type == ComponentType.TEXT_INPUT:
                    # Text input: return the string value
                    result[custom_id] = component.get("value", "")

                elif component_type in (
                    ComponentType.STRING_SELECT,
                    ComponentType.USER_SELECT,
                    ComponentType.ROLE_SELECT,
                    ComponentType.MENTIONABLE_SELECT,
                    ComponentType.CHANNEL_SELECT
                ):
                    # Select components: return list of values
                    result[custom_id] = component.get("values", [])

        return result

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        Global interaction listener that captures modal submissions.

        When a modal is submitted, this listener:
        1. Checks if it matches a pending modal custom_id
        2. Parses the submission data
        3. Resolves the corresponding Future with the parsed data

        Args:
            interaction: The interaction event (could be any type)
        """
        # Only process modal submissions
        if interaction.type != discord.InteractionType.modal_submit:
            return

        # Get the custom_id from the interaction data
        custom_id = interaction.data.get("custom_id")

        if not custom_id or custom_id not in self.pending_modals:
            return

        # Get the Future for this modal
        future = self.pending_modals.get(custom_id)

        if future and not future.done():
            try:
                # Parse the modal data
                components = interaction.data.get("components", [])
                parsed_data = self._parse_modal_data(components)

                # Resolve the Future with the parsed data
                future.set_result(parsed_data)

                log.debug(f"Modal {custom_id} submitted successfully: {parsed_data}")

            except Exception as e:
                log.error(f"Error parsing modal {custom_id}: {e}", exc_info=True)
                future.set_exception(e)

    @commands.command()
    @commands.is_owner()
    async def monkeymodaltest(self, ctx):
        """Test the MonkeyModal system with a comprehensive modal"""

        class TestButton(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=60)
                self.cog = cog

            @discord.ui.button(label="Open Test Modal", style=discord.ButtonStyle.primary, emoji="🐵")
            async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Build a comprehensive test modal
                builder = self.cog.create_builder("test_modal", "MonkeyModal Test")

                builder.add_text_input(
                    "name_input",
                    "Your Name",
                    placeholder="Enter your name...",
                    max_length=50
                )

                builder.add_string_select(
                    "color_select",
                    options=[
                        {"label": "Red", "value": "red", "emoji": {"name": "🔴"}},
                        {"label": "Blue", "value": "blue", "emoji": {"name": "🔵"}},
                        {"label": "Green", "value": "green", "emoji": {"name": "🟢"}}
                    ],
                    placeholder="Pick your favorite color"
                )

                builder.add_role_select(
                    "role_select",
                    placeholder="Pick a role",
                    max_values=3
                )

                builder.add_channel_select(
                    "channel_select",
                    placeholder="Pick a text channel",
                    channel_types=[ChannelType.text]
                )

                # Send modal and await response
                try:
                    result = await self.cog.prompt(interaction, builder, timeout=300)

                    if result:
                        # Format the results
                        lines = ["✅ **Modal Submission Received:**\n"]

                        for key, value in result.items():
                            if isinstance(value, list):
                                value_str = ", ".join(value) if value else "None"
                            else:
                                value_str = value or "None"
                            lines.append(f"**{key}:** {value_str}")

                        await interaction.followup.send("\n".join(lines), ephemeral=True)
                    else:
                        await interaction.followup.send("⏱️ Modal timed out", ephemeral=True)

                except Exception as e:
                    log.error(f"Test modal error: {e}", exc_info=True)
                    await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

        view = TestButton(self)
        await ctx.send(
            "**MonkeyModal Test**\n\n"
            "This will open a modal with:\n"
            "• Text Input\n"
            "• String Select (colors)\n"
            "• Role Select\n"
            "• Channel Select\n\n"
            "Click the button to test:",
            view=view
        )

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Cancel all pending futures
        for future in self.pending_modals.values():
            if not future.done():
                future.cancel()

        self.pending_modals.clear()
        log.info("MonkeyModal cog unloaded")
