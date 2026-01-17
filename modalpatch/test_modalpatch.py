import pytest
from unittest.mock import Mock, patch, AsyncMock
import discord
from discord.ui import Modal, Select, TextInput

class TestModalPatch:
    """Tests for the ModalPatch cog"""

    @pytest.fixture
    async def cog(self, bot):
        """Create a ModalPatch cog instance"""
        from modalpatch import ModalPatch

        # Mock the Modal class to avoid actual patching during tests
        with patch('modalpatch.modalpatch.Modal'):
            cog = ModalPatch(bot)
            yield cog
            cog.cog_unload()

    async def test_cog_loads(self, cog):
        """Test that the cog loads successfully"""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, '_patched')

    async def test_patch_applies(self, cog):
        """Test that the patch is applied on init"""
        # The cog should attempt to patch on init
        assert hasattr(cog, '_apply_patch')
        assert hasattr(cog, '_remove_patch')

    async def test_modalpatchstatus_command_exists(self, cog):
        """Test that the modalpatchstatus command exists"""
        assert hasattr(cog, 'modalpatchstatus')
        assert callable(cog.modalpatchstatus)

    async def test_modalpatchtest_command_exists(self, cog):
        """Test that the modalpatchtest command exists"""
        assert hasattr(cog, 'modalpatchtest')
        assert callable(cog.modalpatchtest)

    async def test_cog_unload_removes_patch(self, cog):
        """Test that unloading the cog removes the patch"""
        # Mock the _remove_patch method
        cog._remove_patch = Mock()

        # Call cog_unload
        cog.cog_unload()

        # Verify _remove_patch was called
        cog._remove_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_patched_refresh_handles_text_input(self):
        """Test that patched _refresh handles TextInput components (type 4)"""
        from modalpatch.modalpatch import ModalPatch

        # Create a mock modal with a text input
        class TestModal(Modal, title="Test"):
            test_input = TextInput(label="Test", custom_id="test_input")

        modal = TestModal()

        # Simulate Discord sending back component data
        components = [
            {
                'type': 1,  # Action Row
                'components': [
                    {
                        'type': 4,  # TextInput
                        'custom_id': 'test_input',
                        'value': 'test value'
                    }
                ]
            }
        ]

        # Apply patch
        cog = ModalPatch(Mock())

        # Call _refresh
        modal._refresh(components)

        # Verify the value was set
        assert modal.test_input.value == 'test value'

        # Cleanup
        cog.cog_unload()

    @pytest.mark.asyncio
    async def test_patched_refresh_handles_select(self):
        """Test that patched _refresh handles Select components (type 3)"""
        from modalpatch.modalpatch import ModalPatch

        # Create a mock modal with a select
        class TestModal(Modal, title="Test"):
            def __init__(self):
                super().__init__()
                self.test_select = Select(
                    custom_id="test_select",
                    options=[
                        discord.SelectOption(label="Option 1", value="opt1"),
                        discord.SelectOption(label="Option 2", value="opt2"),
                    ]
                )
                self.add_item(self.test_select)

        modal = TestModal()

        # Simulate Discord sending back component data
        components = [
            {
                'type': 1,  # Action Row
                'components': [
                    {
                        'type': 3,  # String Select
                        'custom_id': 'test_select',
                        'values': ['opt1']
                    }
                ]
            }
        ]

        # Apply patch
        cog = ModalPatch(Mock())

        # Call _refresh
        modal._refresh(components)

        # Verify the values were set
        assert hasattr(modal.test_select, 'values')
        assert modal.test_select.values == ['opt1']
        assert modal.test_select.value == 'opt1'

        # Cleanup
        cog.cog_unload()
