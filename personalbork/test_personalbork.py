"""Tests for PersonalBork cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

from personalbork.personalbork import PersonalBork


@pytest.mark.asyncio
class TestPersonalBorkCog:
    """Test suite for PersonalBork cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create PersonalBork cog instance."""
        with patch('personalbork.personalbork.Config'):
            cog = PersonalBork(bot)
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
        assert any(cmd.name == 'bork' for cmd in cog.get_commands())
        assert any(cmd.name == 'undo' for cmd in cog.get_commands())
        assert any(cmd.name == 'borked' for cmd in cog.get_commands())
        assert any(cmd.name == 'pborkset' for cmd in cog.get_commands())
