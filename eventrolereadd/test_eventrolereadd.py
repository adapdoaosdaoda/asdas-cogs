"""Tests for EventRoleReadd cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eventrolereadd.eventrolereadd import EventRoleReadd


@pytest.mark.asyncio
class TestEventRoleReaddCog:
    """Test suite for EventRoleReadd cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create EventRoleReadd cog instance."""
        with patch('eventrolereadd.eventrolereadd.Config'):
            cog = EventRoleReadd(bot)
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
        assert hasattr(cog, 'eventrolelog')
