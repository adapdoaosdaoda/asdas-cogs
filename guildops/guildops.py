import discord
import logging
import re
import gspread
import pytesseract
import asyncio
import aiohttp
from datetime import datetime
from io import BytesIO
from PIL import Image
from typing import Optional, List, Dict, Any, Tuple

from redbot.core import commands, Config, data_manager, checks
from redbot.core.bot import Red

log = logging.getLogger("red.asdas-cogs.guildops")

class GuildOps(commands.Cog):
    """
    Synchronize guild membership using Discord Embeds and OCR.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        
        default_guild = {
            "sheet_id": None,
            "forms_channel": None,
            "ocr_channel": None,
        }
        self.config.register_guild(**default_guild)
        
        self.data_path = data_manager.cog_data_path(self)
        self.creds_file = self.data_path / "service_account.json"
        self._ocr_lock = asyncio.Lock()

    async def _get_gc(self):
        """
        Returns a gspread client, running in an executor to avoid blocking.
        """
        if not self.creds_file.exists():
            return None
        
        def _connect():
            return gspread.service_account(filename=str(self.creds_file))
        
        return await self.bot.loop.run_in_executor(None, _connect)

    async def _sync_data_to_sheet(self, sheet_id: str, new_data: List[Dict[str, str]]):
        """
        Syncs a list of user data to the sheet.
        new_data: List of dicts with keys 'discord_id', 'ign', 'date_accepted'
        """
        gc = await self._get_gc()
        if not gc:
            return False, "Service account file not found."

        def _do_work():
            try:
                sh = gc.open_by_key(sheet_id)
                ws = sh.sheet1
                
                # ensure headers
                headers = ws.row_values(1)
                required_headers = ["Discord ID", "IGN", "Date Accepted", "Status"]
                if not headers:
                    ws.append_row(required_headers)
                    headers = required_headers
                
                # Map headers to indices
                header_map = {h: i for i, h in enumerate(headers)}
                
                # Verify we have the columns we need
                for req in ["Discord ID", "IGN", "Date Accepted"]:
                    if req not in header_map:
                        return False, f"Missing column: {req}"

                # Read all data
                all_values = ws.get_all_values()
                if len(all_values) > 1:
                    data_rows = all_values[1:]
                else:
                    data_rows = []

                # Index by Discord ID
                id_col_idx = header_map["Discord ID"]
                ign_col_idx = header_map["IGN"]
                date_col_idx = header_map["Date Accepted"]
                
                # existing_map: Discord ID -> Row Index (1-based)
                existing_map = {}
                for i, row in enumerate(data_rows):
                    # Row index in sheet is i + 2 (1 for header, 1 for 0-index)
                    if len(row) > id_col_idx:
                        d_id = str(row[id_col_idx]).strip()
                        if d_id:
                            existing_map[d_id] = i + 2

                updates = []
                appends = []

                for entry in new_data:
                    d_id = str(entry['discord_id'])
                    ign = entry['ign']
                    date_acc = entry['date_accepted']
                    
                    if d_id in existing_map:
                        # Update existing row
                        row_idx = existing_map[d_id]
                        updates.append({
                            'range': f"{gspread.utils.rowcol_to_a1(row_idx, ign_col_idx + 1)}",
                            'values': [[ign]]
                        })
                        updates.append({
                            'range': f"{gspread.utils.rowcol_to_a1(row_idx, date_col_idx + 1)}",
                            'values': [[date_acc]]
                        })
                    else:
                        # Append new row
                        # Prepare a row with empty values for unknown columns
                        new_row = [""] * len(headers)
                        new_row[id_col_idx] = d_id
                        new_row[ign_col_idx] = ign
                        new_row[date_col_idx] = date_acc
                        # Default status to Active? prompt doesn't say, but implies "Added"
                        if "Status" in header_map:
                            new_row[header_map["Status"]] = "Active"
                        appends.append(new_row)
                
                if appends:
                    ws.append_rows(appends)
                
                if updates:
                    ws.batch_update(updates)
                    
                return True, f"Synced {len(appends)} new and {len(updates)//2} updated records."

            except Exception as e:
                return False, str(e)

        success, msg = await self.bot.loop.run_in_executor(None, _do_work)
        return success, msg

    async def _update_status_by_ign(self, sheet_id: str, ign: str, status: str):
        """
        Updates the status of a user by IGN.
        """
        gc = await self._get_gc()
        if not gc:
            return False, "Service account file not found."

        def _do_work():
            try:
                sh = gc.open_by_key(sheet_id)
                ws = sh.sheet1
                
                headers = ws.row_values(1)
                if "IGN" not in headers or "Status" not in headers:
                    return False, "Sheet missing IGN or Status columns."
                
                ign_col = headers.index("IGN") + 1
                status_col = headers.index("Status") + 1
                
                # Find the cell with the IGN
                cell = ws.find(ign, in_column=ign_col, case_sensitive=False)
                if not cell:
                    return False, f"IGN '{ign}' not found in sheet."
                
                # Update status
                ws.update_cell(cell.row, status_col, status)
                return True, f"Updated {ign} to {status}."
                
            except Exception as e:
                return False, str(e)

        return await self.bot.loop.run_in_executor(None, _do_work)

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def opset(self, ctx):
        """Configuration for GuildOps."""
        pass

    @opset.command()
    async def sheet(self, ctx, sheet_id: str):
        """Set the Google Sheet ID."""
        await self.config.guild(ctx.guild).sheet_id.set(sheet_id)
        await ctx.send(f"Sheet ID set to `{sheet_id}`.")

    @opset.command()
    async def forms(self, ctx, channel: discord.TextChannel):
        """Set the channel to scan for application forms."""
        await self.config.guild(ctx.guild).forms_channel.set(channel.id)
        await ctx.send(f"Forms channel set to {channel.mention}.")

    @opset.command()
    async def ocr(self, ctx, channel: discord.TextChannel):
        """Set the channel to listen for screenshots."""
        await self.config.guild(ctx.guild).ocr_channel.set(channel.id)
        await ctx.send(f"OCR channel set to {channel.mention}.")

    @opset.command()
    async def creds(self, ctx):
        """Instructions for setting up Google Sheets credentials."""
        msg = (
            f"To enable Google Sheets sync, place your `service_account.json` file here:\n"
            f"`{self.creds_file}`\n\n"
            "1. Go to Google Cloud Console.\n"
            "2. Create a Service Account.\n"
            "3. Download the JSON key.\n"
            "4. Rename it to `service_account.json` and upload it to the path above.\n"
            "5. **Share the Google Sheet** with the email inside the JSON file."
        )
        await ctx.send(msg)

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def ops(self, ctx):
        """Guild Operations commands."""
        pass

    @ops.command()
    async def sync_history(self, ctx):
        """Syncs historical application forms to the sheet."""
        sheet_id = await self.config.guild(ctx.guild).sheet_id()
        channel_id = await self.config.guild(ctx.guild).forms_channel()
        
        if not sheet_id:
            return await ctx.send("Please set the sheet ID first with `[p]opset sheet`.")
        if not channel_id:
            return await ctx.send("Please set the forms channel first with `[p]opset forms`.")
            
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.send("Forms channel not found.")
            
        async with ctx.typing():
            data_to_sync = []
            count = 0
            
            async for message in channel.history(limit=None):
                # Filter: "Accepted by" in content (ignore case just in case, but prompt implied specific text)
                if "Accepted by" not in message.content:
                    continue
                
                # Extract Discord ID
                # Look for user mention <@123> or <@!123>
                match_id = re.search(r'<@!?(\d+)>', message.content)
                if not match_id:
                    continue
                discord_id = match_id.group(1)
                
                # Extract IGN from Embed
                ign = None
                if message.embeds:
                    for embed in message.embeds:
                        for field in embed.fields:
                            if "What's your IGN/UID ?" in field.name:
                                ign = field.value.strip()
                                break
                        if ign:
                            break
                
                if not ign:
                    continue
                    
                # Date Accepted - Using message creation time
                date_acc = message.created_at.strftime("%Y-%m-%d")
                
                data_to_sync.append({
                    "discord_id": discord_id,
                    "ign": ign,
                    "date_accepted": date_acc
                })
                count += 1
                
            if not data_to_sync:
                return await ctx.send("No valid application forms found in history.")
                
            success, msg = await self._sync_data_to_sheet(sheet_id, data_to_sync)
            if success:
                await ctx.send(f"Sync complete: {msg}")
            else:
                await ctx.send(f"Sync failed: {msg}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
            
        ocr_channel_id = await self.config.guild(message.guild).ocr_channel()
        if message.channel.id != ocr_channel_id:
            return

        if not message.attachments:
            return

        # Check for image
        att = message.attachments[0]
        if not att.content_type or not att.content_type.startswith("image/"):
            return

        # Acquire lock to prevent spamming OCR logic? 
        # Or just let it run. Let's use a lock per guild if possible, but global is fine for now to save resources.
        # Actually, let's just proceed.
        
        sheet_id = await self.config.guild(message.guild).sheet_id()
        if not sheet_id:
            return # Silent fail if not configured

        try:
            # Download
            async with aiohttp.ClientSession() as session:
                async with session.get(att.url) as resp:
                    if resp.status != 200:
                        return
                    image_data = await resp.read()

            # Process Image (CPU bound)
            def _process_ocr(data):
                try:
                    img = Image.open(BytesIO(data))
                    img = img.convert('L') # Grayscale
                    text = pytesseract.image_to_string(img)
                    return text
                except Exception as e:
                    log.error("OCR Failed", exc_info=e)
                    return None

            text = await self.bot.loop.run_in_executor(None, _process_ocr, image_data)
            if not text:
                return

            # Regex Matching
            # Normalize text for easier matching (strip extra whitespace)
            clean_text = re.sub(r'\s+', ' ', text).strip()
            
            # Join Pattern: approved (.*?) application to join
            # Leave Pattern: (?:end\.?|Members\])\s*(.*?)\s+has\s+left\s+the\s+guild
            
            status = None
            ign = None
            
            # Case insensitive search
            join_match = re.search(r'approved\s+(.*?)(?:\'s)?\s+application\s+to\s+join', clean_text, re.IGNORECASE)
            leave_match = re.search(r'(?:end\.?|Members\])\s*(.*?)\s+has\s+left\s+the\s+guild', clean_text, re.IGNORECASE)

            if join_match:
                status = "Active"
                ign = join_match.group(1).strip()
            elif leave_match:
                status = "Left"
                ign = leave_match.group(1).strip()
            
            if ign and status:
                success, msg = await self._update_status_by_ign(sheet_id, ign, status)
                if success:
                    await message.reply(f"✅ Parsed **{ign}** as **{status}**.")
                else:
                    await message.reply(f"⚠️ Parsed **{ign}** as **{status}**, but sheet update failed: {msg}")

        except Exception as e:
            log.exception("Error in OCR listener")