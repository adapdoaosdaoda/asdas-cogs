"""Tests for EventChannels cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eventchannels.eventchannels import EventChannels


@pytest.mark.asyncio
class TestEventChannelsCog:
    """Test suite for EventChannels cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create EventChannels cog instance."""
        with patch('eventchannels.eventchannels.Config'):
            cog = EventChannels(bot)
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
        # EventChannels should have ecset, ecview, and ectest command groups
        assert hasattr(cog, 'ecset')
        assert hasattr(cog, 'ecview')
        assert hasattr(cog, 'ectest')

    async def test_mixins_integrated(self, cog):
        """Test that all mixins are properly integrated."""
        # Verify mixin methods are accessible
        assert hasattr(cog, '_handle_event')  # HandlersMixin
        assert hasattr(cog, 'on_scheduled_event_create')  # EventsMixin
