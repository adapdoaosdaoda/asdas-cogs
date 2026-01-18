import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

@pytest.mark.asyncio
class TestModalPatch:
    @pytest.fixture
    async def cog(self, bot):
        """Create a ModalPatch cog instance for testing"""
        from modalpatch.modalpatch import ModalPatch
        cog = ModalPatch(bot)
        yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog loads correctly"""
        assert cog is not None
        assert hasattr(cog, 'bot')

    async def test_modalpatchstatus_command_exists(self, cog):
        """Test that modalpatchstatus command exists"""
        assert hasattr(cog, 'modalpatchstatus')
        assert callable(cog.modalpatchstatus)

    async def test_modalpatchtest_command_exists(self, cog):
        """Test that modalpatchtest command exists"""
        assert hasattr(cog, 'modalpatchtest')
        assert callable(cog.modalpatchtest)

    @patch('discord.__version__', '2.6.0')
    @patch('discord.ui.Label', create=True)
    async def test_modalpatchstatus_compatible_version(self, cog, ctx):
        """Test status command with compatible discord.py version"""
        await cog.modalpatchstatus(ctx)

        # Verify that send was called
        assert ctx.send.called

        # Get the message that was sent
        call_args = ctx.send.call_args
        message = call_args[0][0] if call_args[0] else ""

        # Should indicate compatibility
        assert "✅" in message or "Compatible" in message

    @patch('discord.__version__', '2.5.0')
    async def test_modalpatchstatus_incompatible_version(self, cog, ctx):
        """Test status command with incompatible discord.py version"""
        await cog.modalpatchstatus(ctx)

        # Verify that send was called
        assert ctx.send.called

        # Get the message that was sent
        call_args = ctx.send.call_args
        message = call_args[0][0] if call_args[0] else ""

        # Should indicate incompatibility
        assert "❌" in message or "Incompatible" in message or "2.6.0" in message

    @patch('discord.ui.Label', create=True)
    async def test_modalpatchtest_with_label_support(self, cog, ctx):
        """Test that modalpatchtest works when Label is available"""
        # Mock hasattr to return True for Label
        with patch('builtins.hasattr', return_value=True):
            await cog.modalpatchtest(ctx)

            # Should send a message with a view
            assert ctx.send.called
            call_args = ctx.send.call_args

            # Check that view parameter was passed
            assert 'view' in call_args[1]

    async def test_modalpatchtest_without_label_support(self, cog, ctx):
        """Test that modalpatchtest fails gracefully without Label support"""
        # Mock hasattr to return False for Label
        with patch('builtins.hasattr', return_value=False):
            await cog.modalpatchtest(ctx)

            # Should send an error message
            assert ctx.send.called
            call_args = ctx.send.call_args
            message = call_args[0][0] if call_args[0] else ""

            # Should indicate an error
            assert "❌" in message or "Error" in message or "2.6.0" in message

    def test_cog_unload(self, cog):
        """Test that cog_unload runs without errors"""
        # Should not raise any exceptions
        cog.cog_unload()
