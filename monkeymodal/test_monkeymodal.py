"""
Tests for the MonkeyModal cog

These tests verify:
- Cog initialization
- ModalBuilder component construction
- Component type enums
- Modal payload building
- Data parsing logic
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from discord import ChannelType
from monkeymodal import MonkeyModal, ModalBuilder, ComponentType, TextInputStyle


@pytest.mark.asyncio
class TestMonkeyModal:
    """Test suite for MonkeyModal cog"""

    @pytest.fixture
    def bot(self):
        """Create a mock bot instance"""
        bot = MagicMock()
        bot.http = MagicMock()
        bot.http.request = AsyncMock()
        return bot

    @pytest.fixture
    def cog(self, bot):
        """Create a MonkeyModal cog instance"""
        return MonkeyModal(bot)

    async def test_cog_loads(self, cog):
        """Test that the cog loads correctly"""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'pending_modals')
        assert isinstance(cog.pending_modals, dict)
        assert len(cog.pending_modals) == 0

    async def test_create_builder(self, cog):
        """Test creating a ModalBuilder instance"""
        builder = cog.create_builder("test_modal", "Test Modal")

        assert builder is not None
        assert isinstance(builder, ModalBuilder)
        assert builder.custom_id == "test_modal"
        assert builder.title == "Test Modal"
        assert builder.components == []

    async def test_modal_builder_text_input(self):
        """Test adding a text input to a modal"""
        builder = ModalBuilder("test", "Test")
        builder.add_text_input(
            "name",
            "Your Name",
            style=TextInputStyle.SHORT,
            placeholder="Enter name...",
            required=True,
            max_length=50
        )

        payload = builder.build()

        assert len(payload["components"]) == 1
        action_row = payload["components"][0]
        assert action_row["type"] == ComponentType.ACTION_ROW

        component = action_row["components"][0]
        assert component["type"] == ComponentType.TEXT_INPUT
        assert component["custom_id"] == "name"
        assert component["label"] == "Your Name"
        assert component["style"] == TextInputStyle.SHORT
        assert component["placeholder"] == "Enter name..."
        assert component["required"] is True
        assert component["max_length"] == 50

    async def test_modal_builder_string_select(self):
        """Test adding a string select to a modal"""
        builder = ModalBuilder("test", "Test")
        builder.add_string_select(
            "color",
            options=[
                {"label": "Red", "value": "red"},
                {"label": "Blue", "value": "blue"}
            ],
            placeholder="Pick a color",
            min_values=1,
            max_values=2
        )

        payload = builder.build()

        assert len(payload["components"]) == 1
        component = payload["components"][0]["components"][0]
        assert component["type"] == ComponentType.STRING_SELECT
        assert component["custom_id"] == "color"
        assert component["placeholder"] == "Pick a color"
        assert component["min_values"] == 1
        assert component["max_values"] == 2
        assert len(component["options"]) == 2

    async def test_modal_builder_user_select(self):
        """Test adding a user select to a modal"""
        builder = ModalBuilder("test", "Test")
        builder.add_user_select(
            "users",
            placeholder="Pick users",
            min_values=1,
            max_values=5
        )

        payload = builder.build()

        component = payload["components"][0]["components"][0]
        assert component["type"] == ComponentType.USER_SELECT
        assert component["custom_id"] == "users"
        assert component["min_values"] == 1
        assert component["max_values"] == 5

    async def test_modal_builder_role_select(self):
        """Test adding a role select to a modal"""
        builder = ModalBuilder("test", "Test")
        builder.add_role_select(
            "roles",
            placeholder="Pick roles",
            max_values=3
        )

        payload = builder.build()

        component = payload["components"][0]["components"][0]
        assert component["type"] == ComponentType.ROLE_SELECT
        assert component["custom_id"] == "roles"
        assert component["max_values"] == 3

    async def test_modal_builder_mentionable_select(self):
        """Test adding a mentionable select to a modal"""
        builder = ModalBuilder("test", "Test")
        builder.add_mentionable_select(
            "mentions",
            placeholder="Pick users or roles"
        )

        payload = builder.build()

        component = payload["components"][0]["components"][0]
        assert component["type"] == ComponentType.MENTIONABLE_SELECT
        assert component["custom_id"] == "mentions"

    async def test_modal_builder_channel_select(self):
        """Test adding a channel select to a modal"""
        builder = ModalBuilder("test", "Test")
        builder.add_channel_select(
            "channels",
            placeholder="Pick channels",
            channel_types=[ChannelType.text, ChannelType.voice]
        )

        payload = builder.build()

        component = payload["components"][0]["components"][0]
        assert component["type"] == ComponentType.CHANNEL_SELECT
        assert component["custom_id"] == "channels"
        assert "channel_types" in component
        # Verify ChannelType objects are converted to integers
        assert all(isinstance(ct, int) for ct in component["channel_types"])

    async def test_modal_builder_channel_types_integers(self):
        """Test that channel_types can accept raw integers"""
        builder = ModalBuilder("test", "Test")
        builder.add_channel_select(
            "channels",
            channel_types=[0, 2]  # Text and Voice as integers
        )

        payload = builder.build()

        component = payload["components"][0]["components"][0]
        assert component["channel_types"] == [0, 2]

    async def test_modal_builder_fluent_interface(self):
        """Test that builder methods can be chained"""
        builder = (
            ModalBuilder("test", "Test")
            .add_text_input("name", "Name")
            .add_string_select("color", [{"label": "Red", "value": "red"}])
            .add_role_select("role")
        )

        payload = builder.build()

        assert len(payload["components"]) == 3
        assert payload["components"][0]["components"][0]["type"] == ComponentType.TEXT_INPUT
        assert payload["components"][1]["components"][0]["type"] == ComponentType.STRING_SELECT
        assert payload["components"][2]["components"][0]["type"] == ComponentType.ROLE_SELECT

    async def test_parse_modal_data_text_input(self, cog):
        """Test parsing text input from modal submission"""
        components = [
            {
                "type": ComponentType.ACTION_ROW,
                "components": [
                    {
                        "type": ComponentType.TEXT_INPUT,
                        "custom_id": "name",
                        "value": "John Doe"
                    }
                ]
            }
        ]

        result = cog._parse_modal_data(components)

        assert result == {"name": "John Doe"}

    async def test_parse_modal_data_select(self, cog):
        """Test parsing select components from modal submission"""
        components = [
            {
                "type": ComponentType.ACTION_ROW,
                "components": [
                    {
                        "type": ComponentType.ROLE_SELECT,
                        "custom_id": "roles",
                        "values": ["123456", "789012"]
                    }
                ]
            }
        ]

        result = cog._parse_modal_data(components)

        assert result == {"roles": ["123456", "789012"]}

    async def test_parse_modal_data_mixed(self, cog):
        """Test parsing mixed components from modal submission"""
        components = [
            {
                "type": ComponentType.ACTION_ROW,
                "components": [
                    {
                        "type": ComponentType.TEXT_INPUT,
                        "custom_id": "name",
                        "value": "Jane Doe"
                    }
                ]
            },
            {
                "type": ComponentType.ACTION_ROW,
                "components": [
                    {
                        "type": ComponentType.STRING_SELECT,
                        "custom_id": "color",
                        "values": ["blue"]
                    }
                ]
            },
            {
                "type": ComponentType.ACTION_ROW,
                "components": [
                    {
                        "type": ComponentType.CHANNEL_SELECT,
                        "custom_id": "channel",
                        "values": ["999888777"]
                    }
                ]
            }
        ]

        result = cog._parse_modal_data(components)

        assert result == {
            "name": "Jane Doe",
            "color": ["blue"],
            "channel": ["999888777"]
        }

    async def test_cog_unload_cancels_futures(self, cog):
        """Test that cog_unload cancels pending futures"""
        import asyncio

        # Create some mock pending futures
        future1 = asyncio.Future()
        future2 = asyncio.Future()

        cog.pending_modals["modal1"] = future1
        cog.pending_modals["modal2"] = future2

        # Unload the cog
        cog.cog_unload()

        # Verify futures are cancelled
        assert future1.cancelled()
        assert future2.cancelled()
        assert len(cog.pending_modals) == 0

    async def test_component_type_values(self):
        """Test that ComponentType enum has correct values"""
        assert ComponentType.ACTION_ROW == 1
        assert ComponentType.BUTTON == 2
        assert ComponentType.STRING_SELECT == 3
        assert ComponentType.TEXT_INPUT == 4
        assert ComponentType.USER_SELECT == 5
        assert ComponentType.ROLE_SELECT == 6
        assert ComponentType.MENTIONABLE_SELECT == 7
        assert ComponentType.CHANNEL_SELECT == 8

    async def test_text_input_style_values(self):
        """Test that TextInputStyle enum has correct values"""
        assert TextInputStyle.SHORT == 1
        assert TextInputStyle.PARAGRAPH == 2
