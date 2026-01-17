"""Tests for BorkedSince cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from borkedsince.borkedsince import BorkedSince


@pytest.mark.asyncio
class TestBorkedSinceCog:
    """Test suite for BorkedSince cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create BorkedSince cog instance."""
        with patch('borkedsince.borkedsince.Config'):
            cog = BorkedSince(bot)
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
        assert hasattr(cog, 'borkedsince')
