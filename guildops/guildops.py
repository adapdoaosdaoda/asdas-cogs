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
            "member_role": None,
            "left_role": None,
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
                
                # Check if headers are empty or effectively empty (e.g. ["", "", ""])
                is_empty = not headers or not any(h.strip() for h in headers)
                
                if is_empty:
                    ws.update('A1:D1', [required_headers])
                    headers = required_headers
                
                # Map headers to indices (Case Insensitive)
                header_map = {h.lower().strip(): i for i, h in enumerate(headers)}
                
                required_map = {
                    "discord id": "Discord ID",
                    "ign": "IGN",
                    "date accepted": "Date Accepted"
                }
                
                for req_key, display_name in required_map.items():
                    if req_key not in header_map:
                        return False, f"Missing column: {display_name} (Found: {headers})"

                all_values = ws.get_all_values()
                if len(all_values) > 1:
                    data_rows = all_values[1:]
                else:
                    data_rows = []

                # Index by Discord ID
                id_col_idx = header_map["discord id"]
                ign_col_idx = header_map["ign"]
                date_col_idx = header_map["date accepted"]
                status_col_idx = header_map.get("status")
                
                existing_map = {}
                for i, row in enumerate(data_rows):
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
                        new_row = [""] * len(headers)
                        new_row[id_col_idx] = d_id
                        new_row[ign_col_idx] = ign
                        new_row[date_col_idx] = date_acc
                        if status_col_idx is not None:
                            new_row[status_col_idx] = "Active"
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

    async def _process_ocr_result(self, sheet_id: str, ign: str, status: str, guild: discord.Guild):
        """
        Handles OCR result:
        1. Updates sheet (Add if missing).
        2. Handles Role changes for "Left" status.
        """
        gc = await self._get_gc()
        if not gc:
            return False, "Service account file not found."

        def _sheet_work():
            try:
                sh = gc.open_by_key(sheet_id)
                ws = sh.sheet1
                
                headers = ws.row_values(1)
                header_map = {h.lower().strip(): i for i, h in enumerate(headers)}
                
                if "ign" not in header_map or "status" not in header_map:
                    return None, "Sheet missing IGN or Status columns."
                
                ign_col = header_map["ign"] + 1
                status_col = header_map["status"] + 1
                discord_id_col = header_map.get("discord id", -1) + 1
                
                # Find the cell with the IGN
                cell = ws.find(ign, in_column=ign_col, case_sensitive=False)
                
                discord_id = None
                
                if cell:
                    # Update existing
                    ws.update_cell(cell.row, status_col, status)
                    # Fetch Discord ID if available
                    if discord_id_col > 0:
                        row_vals = ws.row_values(cell.row)
                        if len(row_vals) >= discord_id_col:
                            # gspread 1-based index vs list 0-based
                            # discord_id_col is 1-based index. List is 0-based.
                            # So index is discord_id_col - 1
                            val = row_vals[discord_id_col - 1]
                            if val:
                                discord_id = str(val).strip()
                    return discord_id, f"Updated {ign} to {status}."
                else:
                    # Append new row (Missing Discord ID)
                    # Only append if Status is Active (Wait, prompt says "OCR should add new members")
                    # So yes, add them.
                    new_row = [""] * len(headers)
                    new_row[ign_col - 1] = ign
                    new_row[status_col - 1] = status
                    # Date? Not extracted from OCR, leave blank or set today
                    
                    ws.append_row(new_row)
                    return None, f"Added {ign} as {status} (Missing Discord ID)."
                
            except Exception as e:
                return None, str(e)

        # Run sheet update
        discord_id, msg = await self.bot.loop.run_in_executor(None, _sheet_work)
        
        # Handle Roles if Left and Discord ID known
        if status == "Left" and discord_id:
            try:
                member = guild.get_member(int(discord_id))
                if member:
                    member_role_id = await self.config.guild(guild).member_role()
                    left_role_id = await self.config.guild(guild).left_role()
                    
                    if member_role_id:
                        r_mem = guild.get_role(member_role_id)
                        if r_mem:
                            await member.remove_roles(r_mem, reason="GuildOps: Left Guild")
                            
                    if left_role_id:
                        r_left = guild.get_role(left_role_id)
                        if r_left:
                            await member.add_roles(r_left, reason="GuildOps: Left Guild")
                            
                    msg += " (Roles Updated)"
                else:
                    msg += " (Member not found in server)"
            except Exception as e:
                msg += f" (Role Error: {e})"
                
        return True, msg

    def _extract_all_text(self, components: List[Any]) -> str:
        """Recursively extracts all text from a list of components."""
        text = ""
        for comp in components:
            if hasattr(comp, 'label') and comp.label:
                text += f" {comp.label}"
            if hasattr(comp, 'placeholder') and comp.placeholder:
                text += f" {comp.placeholder}"
            if hasattr(comp, 'value') and comp.value:
                text += f" {comp.value}"
            if hasattr(comp, 'options') and comp.options:
                for opt in comp.options:
                    text += f" {opt.label} {opt.value}"

            try:
                d = comp.to_dict() if hasattr(comp, 'to_dict') else comp
                if isinstance(d, dict):
                    if "content" in d:
                        text += f"\n{d['content']}"
                    if "components" in d:
                        text += self._extract_all_text(d["components"])
            except:
                pass

            if hasattr(comp, 'children'):
                text += self._extract_all_text(comp.children)
        return text

    def _parse_forms_message(self, message: discord.Message) -> Tuple[Optional[Dict[str, str]], List[str]]:
        """Parses a forms message and returns (data_dict, failure_reasons)."""
        reasons = []
        
        content_text = message.content or ""
        embed_text = ""
        
        if message.embeds:
            for embed in message.embeds:
                embed_text += f" {embed.title or ''} {embed.description or ''} {embed.footer.text or ''}"
                for field in embed.fields:
                    embed_text += f" {field.name} {field.value}"
                    
        component_text = self._extract_all_text(message.components)
        full_text = content_text + embed_text + component_text
        
        if "Accepted by" not in full_text:
            if "accepted by" not in full_text.lower():
                reasons.append("Status 'Accepted by' not found in text/embeds/components.")
        
        discord_id = None
        match_id = re.search(r'<@!?(\d+)>', full_text)
        if match_id:
            discord_id = match_id.group(1)
        
        if not discord_id:
            reasons.append("Discord User ID not found in content or embeds.")
        
        ign = None
        if message.embeds:
            for embed in message.embeds:
                for field in embed.fields:
                    name_lower = field.name.lower()
                    if "ign" in name_lower or "uid" in name_lower or "in-game" in name_lower:
                        ign = field.value.strip()
                        break
                if ign:
                    break
        
        if not ign:
            pattern = r"(?:###|\*\*)\s*.*?(?:IGN|UID|In-Game).*?[\r\n]+(.+?)(?=\s*(?:###|\*\*)|$)"
            match_ign = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
            if match_ign:
                ign = match_ign.group(1).strip()

        if not ign:
            reasons.append("IGN/UID not found (checked Embed fields and Markdown headers).")
            
        if reasons:
            return None, reasons

        date_acc = message.created_at.strftime("%Y-%m-%d")
        
        return {
            "discord_id": discord_id,
            "ign": ign,
            "date_accepted": date_acc
        }, []

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.id == self.bot.user.id:
            return

        # Check Forms Channel
        forms_channel_id = await self.config.guild(message.guild).forms_channel()
        if forms_channel_id and message.channel.id == forms_channel_id:
             await self._handle_form_message(message)

        # Check OCR Channel
        ocr_channel_id = await self.config.guild(message.guild).ocr_channel()
        if ocr_channel_id and message.channel.id == ocr_channel_id and not message.author.bot:
             await self._handle_ocr_message(message)

    async def _handle_form_message(self, message):
        data, reasons = self._parse_forms_message(message)
        if data:
            sheet_id = await self.config.guild(message.guild).sheet_id()
            if not sheet_id:
                return
            
            success, msg = await self._sync_data_to_sheet(sheet_id, [data])
            if success:
                await message.add_reaction("✅")
            else:
                log.warning(f"Failed to sync form: {msg}")

    async def _handle_ocr_message(self, message):
        if not message.attachments:
            return
            
        sheet_id = await self.config.guild(message.guild).sheet_id()
        if not sheet_id:
            return

        for att in message.attachments:
            if not att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                continue
                
            try:
                if att.size > 8 * 1024 * 1024:
                    continue
                    
                img_data = await att.read()
                
                def _ocr_task():
                    img = Image.open(BytesIO(img_data))
                    return pytesseract.image_to_string(img)
                
                text = await self.bot.loop.run_in_executor(None, _ocr_task)
                
                # Basic parsing: look for lines ending in specific status keywords
                lines = text.split('\n')
                processed_count = 0
                
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    
                    # Regex for "Name Status"
                    # We look for lines that end with a status word
                    match = re.search(r'^(.*?)\s+(Active|Left|Guest|Member|Banned)$', line, re.IGNORECASE)
                    if match:
                        ign = match.group(1).strip()
                        status = match.group(2).capitalize()
                        
                        if len(ign) > 2: # Min length sanity check
                            await self._process_ocr_result(sheet_id, ign, status, message.guild)
                            processed_count += 1
                
                if processed_count > 0:
                    await message.add_reaction("👀")
                    
            except Exception as e:
                log.error("OCR Error", exc_info=e)

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
    async def roles(self, ctx, member_role: discord.Role, left_role: discord.Role):
        """Set the Member and Left/Guest roles for automated role updates."""
        await self.config.guild(ctx.guild).member_role.set(member_role.id)
        await self.config.guild(ctx.guild).left_role.set(left_role.id)
        await ctx.send(f"Roles configured:\nMember: {member_role.mention}\nLeft: {left_role.mention}")

    @opset.command()
    async def creds(self, ctx):
        """Instructions for setting up Google Sheets credentials."""
        msg = (
            f"To enable Google Sheets sync, place your `service_account.json` file here:\n"
            f"`{self.creds_file}`\n\n"
            "1. Go to Google Cloud Console."
            "2. Create a Service Account."
            "3. Download the JSON key."
        )
        await ctx.send(msg)

    @opset.command()
    async def status(self, ctx):
        """Check GuildOps status and configuration."""
        conf = await self.config.guild(ctx.guild).all()
        sheet = conf['sheet_id'] or "Not Set"
        forms = f"<#{conf['forms_channel']}>" if conf['forms_channel'] else "Not Set"
        ocr = f"<#{conf['ocr_channel']}>" if conf['ocr_channel'] else "Not Set"
        m_role = f"<@&{conf['member_role']}>" if conf['member_role'] else "Not Set"
        l_role = f"<@&{conf['left_role']}>" if conf['left_role'] else "Not Set"
        
        embed = discord.Embed(title="GuildOps Settings", color=discord.Color.blue())
        embed.add_field(name="Sheet ID", value=f"`{sheet}`", inline=False)
        embed.add_field(name="Channels", value=f"Forms: {forms}\nOCR: {ocr}", inline=True)
        embed.add_field(name="Roles", value=f"Member: {m_role}\nLeft: {l_role}", inline=True)
        
        if self.creds_file.exists():
            embed.set_footer(text="✅ Service Account File Found")
        else:
            embed.set_footer(text="⚠️ Service Account File Missing (Use [p]opset creds)")
            
        await ctx.send(embed=embed)

    @commands.group(aliases=["ops"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def guildops(self, ctx):
        """GuildOps main commands."""
        pass

    @guildops.command(name="status")
    async def guildops_status(self, ctx):
        """Show GuildOps status (Alias for opset status)."""
        await self.status(ctx)