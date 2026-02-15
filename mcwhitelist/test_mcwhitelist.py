"""Tests for MCWhitelist cog."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import discord
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcwhitelist.mcwhitelist import MCWhitelist

@pytest.mark.asyncio
class TestMCWhitelist:
    """Test suite for MCWhitelist cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create a MCWhitelist cog instance with mocked config."""
        with patch('redbot.core.Config.get_conf'):
            cog = MCWhitelist(bot)
            cog.config = MagicMock()
            
            # Setup default config mock
            async def get_all():
                return {
                    "host": "127.0.0.1",
                    "port": 25575,
                    "password": "password123",
                }
            cog.config.guild.return_value.all = get_all
            yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog initializes correctly."""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'config')

    async def test_whitelist_add(self, cog):
        """Test the whitelist add command."""
        ctx = MagicMock()
        ctx.invoked_subcommand = None
        ctx.guild.id = 123
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.send_cmd.return_value = ("Added PlayerX to the whitelist", 1)
            
            await cog.whitelist(ctx, "PlayerX")
            
            # Verify RCON was called correctly
            mock_client_class.assert_called_with("127.0.0.1", 25575, "password123")
            mock_client.connect.assert_called_once()
            mock_client.send_cmd.assert_called_with("easywhitelist add PlayerX")
            mock_client.close.assert_called_once()
            
            # Verify response message
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            assert "Successfully added `PlayerX`" in args[0]

    async def test_whitelist_remove(self, cog):
        """Test the whitelist remove command."""
        ctx = MagicMock()
        ctx.guild.id = 123
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.send_cmd.return_value = ("Removed PlayerX from the whitelist", 1)
            
            await cog.whitelist_remove(ctx, "PlayerX")
            
            # Verify RCON was called correctly
            mock_client.send_cmd.assert_called_with("easywhitelist remove PlayerX")
            
            # Verify response message
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            assert "Successfully removed `PlayerX`" in args[0]

    async def test_no_password_error(self, cog):
        """Test error when no password is set."""
        ctx = MagicMock()
        ctx.guild.id = 123
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Override config to have no password
        async def get_all_no_pass():
            return {
                "host": "127.0.0.1",
                "port": 25575,
                "password": "",
            }
        cog.config.guild.return_value.all = get_all_no_pass
        
        await cog.whitelist_remove(ctx, "PlayerX")
        
        ctx.send.assert_called()
        args, _ = ctx.send.call_args
        assert "RCON password is not set" in args[0]
