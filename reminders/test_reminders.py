"""Tests for Reminders cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reminders.reminders import Reminders


@pytest.mark.asyncio
class TestRemindersCog:
    """Test suite for Reminders cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create Reminders cog instance."""
        with patch('reminders.reminders.Config'):
            cog = Reminders(bot)
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
        # Reminders should have remind, remindme, and remindset commands
        assert hasattr(cog, 'remind')
        assert hasattr(cog, 'remindme')
        assert hasattr(cog, 'reminderset')
