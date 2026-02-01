"""Tests for GuildOps cog."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import discord
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guildops.guildops import GuildOps


@pytest.mark.asyncio
class TestGuildOps:
    """Test suite for GuildOps cog."""

    @pytest.fixture
    async def cog(self, bot):
        """Create a GuildOps cog instance with mocked config."""
        with patch('guildops.guildops.Config'):
            cog = GuildOps(bot)
            yield cog

    async def test_cog_loads(self, cog):
        """Test that the cog initializes correctly."""
        assert cog is not None
        assert hasattr(cog, 'bot')
        assert hasattr(cog, 'config')

    async def test_parse_ocr_text_mixed(self, cog):
        """Test OCR parsing for various patterns including acceptance."""
        text = """
Player1 Active
Player2 Left
Player3 has left the guild.
[Members]Luojing has removed Po
LIAR from the guild.
® [Members]Songbird has Idago
approved izzue's application to
join the guild. The guild
flourishes!
"""
        parsed = cog._parse_ocr_text(text)
        
        expected = [
            ("Player1", "Active"),
            ("Player2", "Left"),
            ("Player3", "Left"),
            ("Po LIAR", "Left"),
            ("izzue", "Active")
        ]
        
        assert len(parsed) == 5
        for item in expected:
            assert item in parsed

    async def test_sync_data_retroactive(self, cog):
        """Test that sync_data updates retroactive rows by IGN."""
        
        # Mock Google Sheets
        mock_gc = MagicMock()
        mock_sh = MagicMock()
        mock_ws = MagicMock()
        
        mock_gc.open_by_key.return_value = mock_sh
        mock_sh.sheet1 = mock_ws
        
        # Headers: Discord ID, IGN, Date, Status, Import
        mock_ws.row_values.return_value = ["Discord ID", "IGN", "Date Added", "Status", "Import"]
        
        # Existing data: One row added by OCR (No Discord ID, Import=OCR)
        # Row 2 (Index 0 in data)
        mock_ws.get_all_values.return_value = [
            ["Discord ID", "IGN", "Date Added", "Status", "Import"],
            ["", "TestUser", "", "Active", "OCR"] 
        ]
        
        # Mock executor to run _do_work immediately
        async def mock_executor(executor, func):
            return func()
        cog.bot.loop.run_in_executor = mock_executor
        
        # Patch _get_gc
        with patch.object(cog, '_get_gc', return_value=mock_gc):
            new_data = [{
                "discord_id": "12345",
                "ign": "TestUser",
                "date_accepted": "2024-01-01"
            }]
            
            success, msg = await cog._sync_data_to_sheet("sheet_id", new_data)
            
            assert success is True
            # Verification:
            # Should call batch_update with updates for Row 2 (cols for IGN, Date, ID, Import)
            # We specifically look for the Discord ID update on the existing row
            assert mock_ws.batch_update.called
            updates = mock_ws.batch_update.call_args[0][0]
            
            # Check if we are updating the Discord ID (Col 1 -> A)
            found_id_update = False
            found_import_update = False
            
            for update in updates:
                # Row 2 is index 2 in A1 notation? rowcol_to_a1(2, 1) -> A2
                # Our mock setup logic: row_idx = i + 2 = 0 + 2 = 2.
                if 'A2' in update['range'] and update['values'] == [['12345']]:
                    found_id_update = True
                if 'E2' in update['range'] and update['values'] == [['Form']]: # Col 5 is Import
                    found_import_update = True
                    
            assert found_id_update, "Did not update Discord ID on existing row"
            assert found_import_update, "Did not update Import source to Form"

    async def test_synchistory_forms(self, cog):
        """Test synchistory command for forms."""
        ctx = MagicMock()
        ctx.guild.id = 123
        ctx.typing.return_value.__aenter__.return_value = None
        
        # Mock Config
        cog.config.guild.return_value.forms_channel.return_value = 999
        cog.config.guild.return_value.sheet_id.return_value = "SHEET_ID"
        
        # Mock Channel History
        mock_channel = MagicMock()
        ctx.guild.get_channel.return_value = mock_channel
        
        # Mock Messages
        msg1 = MagicMock()
        msg1.author.bot = False
        msg2 = MagicMock()
        msg2.author.bot = False
        
        # Async Iterator for history
        async def mock_history(limit=50):
            yield msg1
            yield msg2
        
        mock_channel.history = mock_history
        
        # Mock _parse_forms_message to return data for msg1, None for msg2
        cog._parse_forms_message = MagicMock(side_effect=[
            ({"discord_id": "1", "ign": "A", "date_accepted": "2024-01-01"}, []),
            (None, ["Reason"])
        ])
        
        # Mock _sync_data_to_sheet
        cog._sync_data_to_sheet = AsyncMock(return_value=(True, "Synced 1"))
        
        await cog.guildops_sync_history(ctx, "forms", limit=10)
        
        # Verify
        assert cog._sync_data_to_sheet.called
        call_args = cog._sync_data_to_sheet.call_args
        assert call_args[0][0] == "SHEET_ID"
        assert len(call_args[0][1]) == 1 # Only one valid form
        assert call_args[0][1][0]['ign'] == "A"