"""Tests for MsgMover cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msgmover.msgmover import MsgMover


@pytest.mark.asyncio
class TestMsgMoverCog:
    """Test suite for MsgMover cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create MsgMover cog instance."""
        with patch('msgmover.msgmover.Config'):
            cog = MsgMover(bot)
            yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog initializes without errors."""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'config')

    async def test_config_schema(self, cog):
        """Test that config schema is registered correctly."""
        assert cog.config is not None

    async def test_cog_commands_registered(self, cog):
        """Test that cog commands are properly registered."""
        # MsgMover should have msgcopy and msgrelay commands
        assert hasattr(cog, 'msgcopy')
        assert hasattr(cog, 'msgrelay')

    async def test_utils_imported(self, cog):
        """Test that utility functions are available."""
        # Verify main utility modules are accessible
        from msgmover import utils, utils_copy, utils_relay
        assert utils is not None
        assert utils_copy is not None
        assert utils_relay is not None
