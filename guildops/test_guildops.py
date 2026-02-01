"""Tests for GuildOps cog."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import discord
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guildops.guildops import GuildOps


@pytest.mark.asyncio
class TestGuildOps:
    """Test suite for GuildOps cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create a GuildOps cog instance with mocked config."""
        with patch('guildops.guildops.Config'):
            cog = GuildOps(bot)
            yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog initializes correctly."""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'config')
        assert hasattr(cog, 'data_path')
        assert hasattr(cog, 'creds_file')

    async def test_cog_has_commands(self, cog):
        """Test that all expected commands exist."""
        # Configuration commands
        assert hasattr(cog, 'opset')
        assert hasattr(cog, 'guildops')

        # Check opset subcommands
        opset_commands = [cmd.name for cmd in cog.opset.commands]
        assert 'sheet' in opset_commands
        assert 'forms' in opset_commands
        assert 'ocr' in opset_commands
        assert 'roles' in opset_commands
        assert 'creds' in opset_commands
        assert 'status' in opset_commands

        # Check guildops subcommands
        guildops_commands = [cmd.name for cmd in cog.guildops.commands]
        assert 'status' in guildops_commands
        assert 'processform' in guildops_commands
        assert 'processocr' in guildops_commands

    async def test_extract_all_text_basic(self, cog):
        """Test text extraction from components."""
        # Mock component with label
        mock_component = MagicMock()
        mock_component.label = "Test Label"
        mock_component.placeholder = None
        mock_component.value = None
        mock_component.options = None
        mock_component.children = []
        mock_component.to_dict.return_value = {}

        result = cog._extract_all_text([mock_component])
        assert "Test Label" in result

    async def test_parse_forms_message_missing_data(self, cog):
        """Test form parsing with missing required fields."""
        # Mock message without required data
        mock_message = MagicMock(spec=discord.Message)
        mock_message.content = "Test message"
        mock_message.embeds = []
        mock_message.components = []

        data, reasons = cog._parse_forms_message(mock_message)

        assert data is None
        assert len(reasons) > 0
        assert any("Discord User ID" in r for r in reasons)

    async def test_parse_forms_message_with_valid_data(self, cog):
        """Test form parsing with valid embed data."""
        # Mock message with valid data
        mock_message = MagicMock(spec=discord.Message)
        mock_message.content = "Application Accepted by <@123456789>"
        mock_message.created_at = MagicMock()
        mock_message.created_at.strftime = MagicMock(return_value="2024-01-01")

        # Mock embed with IGN field
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.title = "Application"
        mock_embed.description = "Test"
        mock_embed.footer = MagicMock()
        mock_embed.footer.text = ""

        mock_field = MagicMock()
        mock_field.name = "IGN"
        mock_field.value = "TestPlayer123"
        mock_embed.fields = [mock_field]

        mock_message.embeds = [mock_embed]
        mock_message.components = []

        data, reasons = cog._parse_forms_message(mock_message)

        assert data is not None
        assert data['discord_id'] == "123456789"
        assert data['ign'] == "TestPlayer123"
        assert data['date_accepted'] == "2024-01-01"
        assert len(reasons) == 0

    async def test_get_gc_no_credentials(self, cog):
        """Test Google Sheets client when credentials are missing."""
        cog.creds_file.exists = MagicMock(return_value=False)

        result = await cog._get_gc()
        assert result is None

    async def test_listener_registered(self, cog):
        """Test that the on_message listener is registered."""
        assert hasattr(cog, 'on_message')
        assert callable(cog.on_message)

    async def test_on_message_ignores_bot_messages(self, cog):
        """Test that bot messages are ignored."""
        mock_message = MagicMock(spec=discord.Message)
        mock_message.guild = MagicMock()
        mock_message.author.id = cog.bot.user.id

        # Should return early without processing
        result = await cog.on_message(mock_message)
        assert result is None

    async def test_on_message_ignores_dm(self, cog):
        """Test that DM messages are ignored."""
        mock_message = MagicMock(spec=discord.Message)
        mock_message.guild = None

        # Should return early without processing
        result = await cog.on_message(mock_message)
        assert result is None
