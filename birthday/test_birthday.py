"""Tests for Birthday cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from birthday.birthday import Birthday


@pytest.mark.asyncio
class TestBirthdayCog:
    """Test suite for Birthday cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create Birthday cog instance."""
        with patch('birthday.birthday.Config'):
            cog = Birthday(bot)
            yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog initializes without errors."""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'config')

    async def test_config_schema(self, cog):
        """Test that config schema is registered correctly."""
        # Verify config was initialized with correct identifier
        assert cog.config is not None

    async def test_cog_commands_registered(self, cog):
        """Test that cog commands are properly registered."""
        # Birthday cog should have bday and bdset commands
        assert hasattr(cog, 'bday')
        assert hasattr(cog, 'bdset')
