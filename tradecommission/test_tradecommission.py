"""Tests for TradeCommission cog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradecommission.tradecommission import TradeCommission


@pytest.mark.asyncio
class TestTradeCommissionCog:
    """Test suite for TradeCommission cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create TradeCommission cog instance."""
        with patch('tradecommission.tradecommission.Config'):
            cog = TradeCommission(bot)
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
        # TradeCommission should have tc and tcset command groups
        assert hasattr(cog, 'tc')
        assert hasattr(cog, 'tcset')
