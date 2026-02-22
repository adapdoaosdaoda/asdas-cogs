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
    async def cog(self):
        """Create a MCWhitelist cog instance with mocked config."""
        bot = MagicMock()
        with patch('redbot.core.Config.get_conf'):
            cog = MCWhitelist(bot)
            cog.config = MagicMock()
            
            # Setup default config mock
            async def get_all():
                return {
                    "host": "127.0.0.1",
                    "port": 25575,
                    "password": "password123",
                    "java_prefix": "",
                    "bedrock_prefix": ".",
                }
            cog.config.all = get_all
            
            # Mock individual config attributes
            cog.config.java_prefix = AsyncMock(return_value="")
            cog.config.bedrock_prefix = AsyncMock(return_value=".")
            
            yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog initializes correctly."""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'config')

    async def test_whitelist_add(self, cog):
        """Test the whitelist add command (Java)."""
        ctx = MagicMock()
        ctx.invoked_subcommand = None
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.send_cmd.return_value = ("Added PlayerX to the whitelist", 1)
            
            await cog.mcwhitelist(ctx, "PlayerX")
            
            # Verify RCON was called correctly
            mock_client_class.assert_called_with("127.0.0.1", 25575, "password123")
            mock_client.connect.assert_called_once()
            mock_client.send_cmd.assert_called_with("whitelist add PlayerX")
            mock_client.close.assert_called_once()
            
            # Verify response message
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            assert "Successfully added `PlayerX`" in args[0]

    async def test_whitelist_remove(self, cog):
        """Test the whitelist remove command (Java)."""
        ctx = MagicMock()
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.send_cmd.return_value = ("Removed PlayerX from the whitelist", 1)
            
            await cog.mcwhitelist_remove(ctx, "PlayerX")
            
            # Verify RCON was called correctly
            mock_client.send_cmd.assert_called_with("whitelist remove PlayerX")
            
            # Verify response message
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            assert "Successfully removed `PlayerX`" in args[0]

    async def test_whitelist_bedrock_add(self, cog):
        """Test the bedrock whitelist add command."""
        ctx = MagicMock()
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.send_cmd.return_value = ("Added Bedrock player to the whitelist", 1)
            
            await cog.mcwhitelist_bedrock(ctx, "PlayerX")
            
            # Verify RCON was called correctly with fwhitelist and NO prefix
            mock_client.send_cmd.assert_called_with("fwhitelist add PlayerX")
            
            # Verify response message
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            assert "Successfully added Bedrock player `PlayerX`" in args[0]

    async def test_whitelist_bedrock_remove(self, cog):
        """Test the bedrock whitelist remove command."""
        ctx = MagicMock()
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.send_cmd.return_value = ("Removed Bedrock player from the whitelist", 1)
            
            await cog.mcwhitelist_remove_bedrock(ctx, "PlayerX")
            
            # Verify RCON was called correctly with fwhitelist and NO prefix
            mock_client.send_cmd.assert_called_with("fwhitelist remove PlayerX")
            
            # Verify response message
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            assert "Successfully removed Bedrock player `PlayerX`" in args[0]

    async def test_whitelist_list(self, cog):
        """Test the whitelist list command."""
        ctx = MagicMock()
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Mock RCON Client
        with patch('mcwhitelist.mcwhitelist.Client') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock response with mixed Java and Bedrock (prefixed with .) players, using player(s): format
            mock_client.send_cmd.return_value = ("There are 3 whitelisted player(s): JavaPlayer, .BedrockPlayer, OtherPlayer", 1)
            
            await cog.mcwhitelist_list(ctx)
            
            # Verify RCON was called correctly
            mock_client.send_cmd.assert_called_with("whitelist list")
            
            # Verify response message (embed)
            ctx.send.assert_called()
            args, _ = ctx.send.call_args
            embed = args[0]
            assert isinstance(embed, discord.Embed)
            assert embed.title == "Whitelisted Players"
            
            # Check fields
            fields = {field.name: field.value for field in embed.fields}
            assert "☕ Java Players" in fields
            assert "JavaPlayer" in fields["☕ Java Players"]
            assert "OtherPlayer" in fields["☕ Java Players"]
            assert "📱 Bedrock Players" in fields
            assert ".BedrockPlayer" in fields["📱 Bedrock Players"]

    async def test_no_password_error(self, cog):
        """Test error when no password is set."""
        ctx = MagicMock()
        ctx.typing.return_value.__aenter__ = AsyncMock()
        ctx.typing.return_value.__aexit__ = AsyncMock()
        
        # Override config to have no password
        async def get_all_no_pass():
            return {
                "host": "127.0.0.1",
                "port": 25575,
                "password": "",
            }
        cog.config.all = get_all_no_pass
        
        await cog.mcwhitelist_remove(ctx, "PlayerX")
        
        ctx.send.assert_called()
        args, _ = ctx.send.call_args
        assert "RCON password is not set" in args[0]
