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

    def _parse_forms_message(self, message: discord.Message) -> Tuple[Optional[Dict[str, str]], List[str]]:
        """Parses a forms message and returns (data_dict, failure_reasons)."""
        reasons = []
        
        # 1. Check for "Accepted by" status
        content_text = message.content or ""
        embed_text = ""
        component_text = ""
        
        if message.embeds:
            for embed in message.embeds:
                embed_text += f" {embed.title or ''} {embed.description or ''} {embed.footer.text or ''}"
                for field in embed.fields:
                    embed_text += f" {field.name} {field.value}"
                    
        if message.components:
            for component in message.components:
                if hasattr(component, 'children'):
                    for child in component.children:
                        if hasattr(child, 'label') and child.label:
                            component_text += f" {child.label}"
                        if hasattr(child, 'placeholder') and child.placeholder:
                            component_text += f" {child.placeholder}"
                        if hasattr(child, 'value') and child.value:
                            component_text += f" {child.value}"
                        if hasattr(child, 'options') and child.options:
                            for option in child.options:
                                component_text += f" {option.label} {option.value} {option.description or ''}"
        
        full_text = content_text + embed_text + component_text
        
        if "Accepted by" not in full_text:
            if "accepted by" not in full_text.lower():
                reasons.append("Status 'Accepted by' not found in text/embeds/components.")
        
        # 2. Extract Discord ID
        discord_id = None
        match_id = re.search(r'<@!?(\d+)>', content_text)
        if match_id:
            discord_id = match_id.group(1)
        else:
            if message.embeds:
                for embed in message.embeds:
                    for field in embed.fields:
                        if any(x in field.name.lower() for x in ["user", "applicant", "member"]):
                            match_field = re.search(r'<@!?(\d+)>', field.value)
                            if match_field:
                                discord_id = match_field.group(1)
                                break
                    if discord_id: break
                
                if not discord_id:
                     match_embed = re.search(r'<@!?(\d+)>', embed_text)
                     if match_embed:
                         discord_id = match_embed.group(1)

        if not discord_id:
            reasons.append("Discord User ID not found in content or embeds.")
        
        # 3. Extract IGN
        ign = None
        
        # Strategy A: Check Embeds
        if message.embeds:
            for embed in message.embeds:
                for field in embed.fields:
                    name_lower = field.name.lower()
                    if "ign" in name_lower or "uid" in name_lower or "in-game" in name_lower:
                        ign = field.value.strip()
                        break
                if ign:
                    break
        
        # Strategy B: Check Message Content (Markdown Headers)
        if not ign and content_text:
            pattern = r"(?:###|\*\*)\s*.*?(?:IGN|UID|In-Game).*?[\r\n]+(.+?)(?=\s*(?:###|\*\*)|$)"
            match_ign = re.search(pattern, content_text, re.IGNORECASE | re.DOTALL)
            if match_ign:
                ign = match_ign.group(1).strip()

        if not ign:
            reasons.append("IGN/UID not found (checked Embed fields and Markdown headers).")
            
        # Return success only if we have everything (and no fatal reasons)
        # Note: We check all 3 to report all missing parts.
        if reasons:
            return None, reasons

        # Date Accepted
        date_acc = message.created_at.strftime("%Y-%m-%d")
        
        return {
            "discord_id": discord_id,
            "ign": ign,
            "date_accepted": date_acc
        }, []

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
    async def create_sheet(self, ctx, title: str, share_email: str):
        """Creates a new Google Sheet and shares it with the specified email."""
        gc = await self._get_gc()
        if not gc:
            return await ctx.send("Service account file not found. Please setup credentials first.")

        def _create_and_share():
            try:
                # Create spreadsheet
                sh = gc.create(title)
                # Share with user
                sh.share(share_email, perm_type='user', role='writer')
                return sh.id, sh.url
            except Exception as e:
                return None, str(e)

        async with ctx.typing():
            sheet_id, result = await self.bot.loop.run_in_executor(None, _create_and_share)
            
            if not sheet_id:
                return await ctx.send(f"Failed to create sheet: {result}")
            
            # Auto-configure
            await self.config.guild(ctx.guild).sheet_id.set(sheet_id)
            await ctx.send(f"✅ Sheet **{title}** created and shared with `{share_email}`.\nURL: {result}\nID: `{sheet_id}`\n\nI have automatically set this as your active sheet.")

    @ops.command()
    async def debug_msg(self, ctx, message_link: str):
        """Analyzes a specific message to debug why it's not being parsed."""
        try:
            # Parse link: https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
            parts = message_link.split('/')
            if len(parts) < 3:
                return await ctx.send("Invalid message link.")
            
            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                return await ctx.send(f"Could not find channel with ID {channel_id}.")
                
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                return await ctx.send(f"Could not find message with ID {message_id} in {channel.mention}.")
            except discord.Forbidden:
                return await ctx.send(f"I don't have permission to read messages in {channel.mention}.")

            # --- Debug Report ---
            report = [f"**Analysis of Message {message_id}**"]
            
            # 1. Content
            report.append(f"**Content:**\n`{message.content}`")
            if not message.content:
                report.append("⚠️ **Warning: Message content is empty.** Ensure 'Message Content Intent' is enabled in the Discord Developer Portal.")
            
            # 2. Raw attributes for deep debug
            report.append(f"**Raw Flags:** `{message.flags.value}`")
            report.append(f"**Author Bot:** `{message.author.bot}`")
            
            # 2. Embeds
            report.append(f"**Embeds found:** {len(message.embeds)}")
            for i, embed in enumerate(message.embeds):
                report.append(f"  -- Embed {i+1} --")
                if embed.title: report.append(f"  Title: {embed.title}")
                if embed.description: report.append(f"  Desc: {embed.description}")
                if embed.footer and embed.footer.text: report.append(f"  Footer: {embed.footer.text}")
                for field in embed.fields:
                    report.append(f"  Field: Name='{field.name}' Value='{field.value}'")
            
            # 3. Components
            report.append(f"**Components found:** {len(message.components)}")
            for i, comp in enumerate(message.components):
                report.append(f"  -- Component Row {i+1} --")
                if hasattr(comp, 'children'):
                    for child in comp.children:
                        c_type = getattr(child, 'type', 'Unknown')
                        label = getattr(child, 'label', 'None')
                        custom_id = getattr(child, 'custom_id', 'None')
                        value = getattr(child, 'value', 'None')
                        placeholder = getattr(child, 'placeholder', 'None')
                        
                        report.append(f"    Type: {c_type}, Label: '{label}', ID: '{custom_id}', Value: '{value}', Placeholder: '{placeholder}'")
                        
                        if hasattr(child, 'options') and child.options:
                            for opt in child.options:
                                report.append(f"      Option: Label='{opt.label}' Value='{opt.value}'")

            # 4. Parsing Result
            result, reasons = self._parse_forms_message(message)
            if result:
                report.append("\n**✅ PARSING SUCCESS**")
                report.append(f"Discord ID: `{result['discord_id']}`")
                report.append(f"IGN: `{result['ign']}`")
                report.append(f"Date: `{result['date_accepted']}`")
            else:
                report.append("\n**❌ PARSING FAILED**")
                for r in reasons:
                    report.append(f"  - {r}")

            # Chunk and Send
            full_text = "\n".join(report)
            if len(full_text) > 1900:
                # Naive chunking
                await ctx.send(full_text[:1900])
                await ctx.send(full_text[1900:])
            else:
                await ctx.send(full_text)

        except ValueError:
            await ctx.send("Invalid message link format.")
        except Exception as e:
            log.exception("Debug command failed")
            await ctx.send(f"An error occurred: {str(e)}")

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
            
            async for message in channel.history(limit=None):
                entry, _ = self._parse_forms_message(message)
                if entry:
                    data_to_sync.append(entry)
                
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
            
        # --- Forms Channel Logic ---
        forms_channel_id = await self.config.guild(message.guild).forms_channel()
        if forms_channel_id and message.channel.id == forms_channel_id:
            entry, _ = self._parse_forms_message(message)
            if entry:
                sheet_id = await self.config.guild(message.guild).sheet_id()
                if sheet_id:
                    await self._sync_data_to_sheet(sheet_id, [entry])
            return # Don't process as OCR if it's a form message (though likely mutually exclusive channels)

        # --- OCR Channel Logic ---
        ocr_channel_id = await self.config.guild(message.guild).ocr_channel()
        if message.channel.id != ocr_channel_id:
            return

        if not message.attachments:
            return

        # Check for image
        att = message.attachments[0]
        if not att.content_type or not att.content_type.startswith("image/"):
            return

        sheet_id = await self.config.guild(message.guild).sheet_id()
        if not sheet_id:
            return 

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
            clean_text = re.sub(r'\s+', ' ', text).strip()
            
            status = None
            ign = None
            
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