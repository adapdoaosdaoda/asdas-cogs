import asyncio
from datetime import datetime, timedelta, timezone
import logging

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.eventchannels")


class EventChannels(commands.Cog):
    """Creates text & voice channels from Discord Scheduled Events and cleans them up."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817263540)
        self.config.register_guild(
            event_channels={},
            category_id=None,
            timezone="UTC",  # Default timezone
            role_format="{name} {day_abbrev} {day}. {month_abbrev} {time}",  # Default role format
            deletion_hours=4,  # Default deletion time in hours
        )
        self.active_tasks = {}  # Store tasks by event_id for cancellation
        self.bot.loop.create_task(self._startup_scan())

    # ---------- Setup Commands ----------

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventcategory(self, ctx, category: discord.CategoryChannel):
        """Set the category where event channels will be created."""
        await self.config.guild(ctx.guild).category_id.set(category.id)
        await ctx.send(f"✅ Event channels will be created in **{category.name}**.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventtimezone(self, ctx, tz: str):
        """Set the timezone for event role matching (e.g., Europe/Amsterdam, America/New_York)."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        
        try:
            # Validate the timezone
            ZoneInfo(tz)
            await self.config.guild(ctx.guild).timezone.set(tz)
            await ctx.send(f"✅ Event timezone set to **{tz}**.")
        except ZoneInfoNotFoundError:
            await ctx.send(f"❌ Invalid timezone: **{tz}**. Use a timezone like `Europe/Amsterdam` or `America/New_York`.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventdeletion(self, ctx, hours: int):
        """Set how many hours after event start channels are deleted (default: 4)."""
        if hours < 0:
            await ctx.send("❌ Hours must be a positive number.")
            return
        await self.config.guild(ctx.guild).deletion_hours.set(hours)
        await ctx.send(f"✅ Event channels will be deleted **{hours} hours** after event start.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def seteventroleformat(self, ctx, *, format_string: str):
        """Set the role name format pattern.
        
        Available placeholders:
        - {name} - Event name
        - {day_abbrev} - Day abbreviation (Mon, Tue, etc.)
        - {day} - Day number (1-31)
        - {month_abbrev} - Month abbreviation (Jan, Feb, etc.)
        - {time} - Time in HH:MM format
        
        Example: `{name} {day_abbrev} {day}. {month_abbrev} {time}`
        """
        # Validate the format string has valid placeholders
        valid_placeholders = {'{name}', '{day_abbrev}', '{day}', '{month_abbrev}', '{time}'}
        
        # Check if format contains at least one valid placeholder
        has_valid = any(placeholder in format_string for placeholder in valid_placeholders)
        if not has_valid:
            await ctx.send(f"❌ Format must contain at least one valid placeholder: {', '.join(valid_placeholders)}")
            return
        
        await self.config.guild(ctx.guild).role_format.set(format_string)
        await ctx.send(f"✅ Event role format set to: `{format_string}`")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def vieweventsettings(self, ctx):
        """View current event channel settings."""
        category_id = await self.config.guild(ctx.guild).category_id()
        timezone = await self.config.guild(ctx.guild).timezone()
        deletion_hours = await self.config.guild(ctx.guild).deletion_hours()
        role_format = await self.config.guild(ctx.guild).role_format()
        
        category = ctx.guild.get_channel(category_id) if category_id else None
        category_name = category.name if category else "Not set"
        
        embed = discord.Embed(title="Event Channels Settings", color=discord.Color.blue())
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="Timezone", value=timezone, inline=False)
        embed.add_field(name="Deletion Time", value=f"{deletion_hours} hours after start", inline=False)
        embed.add_field(name="Role Format", value=f"`{role_format}`", inline=False)
        
        await ctx.send(embed=embed)

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def listeventchannels(self, ctx):
        """Show currently active event channels."""
        stored = await self.config.guild(ctx.guild).event_channels()
        
        if not stored:
            await ctx.send("No active event channels.")
            return
        
        embed = discord.Embed(title="Active Event Channels", color=discord.Color.green())
        
        for event_id, data in stored.items():
            text_channel = ctx.guild.get_channel(data.get("text"))
            voice_channel = ctx.guild.get_channel(data.get("voice"))
            role = ctx.guild.get_role(data.get("role"))
            
            text_mention = text_channel.mention if text_channel else "❌ Deleted"
            voice_mention = voice_channel.mention if voice_channel else "❌ Deleted"
            role_mention = role.mention if role else "❌ Deleted"
            
            embed.add_field(
                name=f"Event ID: {event_id}",
                value=f"**Text:** {text_mention}\n**Voice:** {voice_mention}\n**Role:** {role_mention}",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def cleanupevent(self, ctx, event_id: str):
        """Manually trigger cleanup for a specific event by event ID."""
        stored = await self.config.guild(ctx.guild).event_channels()
        
        data = stored.get(event_id)
        if not data:
            await ctx.send(f"❌ No active channels found for event ID: `{event_id}`")
            return
        
        # Cancel any active task
        task = self.active_tasks.get(int(event_id))
        if task and not task.done():
            task.cancel()
        
        deleted_items = []
        
        # Delete channels
        for channel_type, channel_id in [("text", data.get("text")), ("voice", data.get("voice"))]:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete(reason=f"Manual cleanup by {ctx.author}")
                    deleted_items.append(f"✅ {channel_type} channel")
                except discord.Forbidden:
                    deleted_items.append(f"❌ {channel_type} channel (no permission)")
                except discord.NotFound:
                    deleted_items.append(f"⚠️ {channel_type} channel (already deleted)")
        
        # Delete role
        role = ctx.guild.get_role(data.get("role"))
        if role:
            try:
                await role.delete(reason=f"Manual cleanup by {ctx.author}")
                deleted_items.append("✅ role")
            except discord.Forbidden:
                deleted_items.append("❌ role (no permission)")
        
        # Remove from config
        stored.pop(event_id, None)
        await self.config.guild(ctx.guild).event_channels.set(stored)
        
        result = "\n".join(deleted_items)
        await ctx.send(f"**Cleanup for event {event_id}:**\n{result}")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def testeventrole(self, ctx, event_id: str):
        """Test what role name would be generated for a Discord scheduled event.
        
        Use the event ID from Discord (right-click event → Copy ID with Developer Mode enabled).
        """
        try:
            events = await ctx.guild.fetch_scheduled_events()
            event = discord.utils.get(events, id=int(event_id))
            
            if not event:
                await ctx.send(f"❌ No scheduled event found with ID: `{event_id}`")
                return
            
            if not event.start_time:
                await ctx.send(f"❌ Event `{event.name}` has no start time.")
                return
            
            # Get server timezone and convert event time
            from zoneinfo import ZoneInfo
            tz_name = await self.config.guild(ctx.guild).timezone()
            server_tz = ZoneInfo(tz_name)
            event_local_time = event.start_time.astimezone(server_tz)
            
            # Build the expected role name using the configured format
            role_format = await self.config.guild(ctx.guild).role_format()
            
            day_abbrev = event_local_time.strftime("%a")
            day = event_local_time.strftime("%d").lstrip("0")
            month_abbrev = event_local_time.strftime("%b")
            time_str = event_local_time.strftime("%H:%M")
            
            expected_role_name = role_format.format(
                name=event.name,
                day_abbrev=day_abbrev,
                day=day,
                month_abbrev=month_abbrev,
                time=time_str
            )
            
            # Check if role exists
            role = discord.utils.get(ctx.guild.roles, name=expected_role_name)
            
            embed = discord.Embed(title="Event Role Name Test", color=discord.Color.blue())
            embed.add_field(name="Event Name", value=event.name, inline=False)
            embed.add_field(name="Start Time (UTC)", value=event.start_time.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            embed.add_field(name=f"Start Time ({tz_name})", value=event_local_time.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            embed.add_field(name="Expected Role Name", value=f"`{expected_role_name}`", inline=False)
            embed.add_field(name="Role Exists?", value="✅ Yes" if role else "❌ No", inline=False)
            
            if role:
                embed.add_field(name="Role Mention", value=role.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except ValueError:
            await ctx.send(f"❌ Invalid event ID format: `{event_id}`. Must be a number.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to fetch scheduled events.")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

    # ---------- Startup ----------

    async def _startup_scan(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._schedule_existing_events(guild)

    async def _schedule_existing_events(self, guild: discord.Guild):
        try:
            events = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            return

        for event in events:
            if event.start_time and event.status == discord.EventStatus.scheduled:
                task = self.bot.loop.create_task(self._handle_event(guild, event))
                self.active_tasks[event.id] = task

    # ---------- Core Logic ----------

    async def _handle_event(self, guild: discord.Guild, event: discord.ScheduledEvent):
        try:
            start_time = event.start_time.astimezone(timezone.utc)
            create_time = start_time - timedelta(minutes=15)
            deletion_hours = await self.config.guild(guild).deletion_hours()
            delete_time = start_time + timedelta(hours=deletion_hours)
            now = datetime.now(timezone.utc)

            # If event starts in less than 15 minutes, create channels immediately
            if now >= create_time:
                # Already past the create time, do it now
                pass
            else:
                # Wait until 15 minutes before start
                await asyncio.sleep((create_time - now).total_seconds())

            stored = await self.config.guild(guild).event_channels()
            if str(event.id) in stored:
                return

            category_id = await self.config.guild(guild).category_id()
            category = guild.get_channel(category_id) if category_id else None

            # Get server timezone and convert event time
            from zoneinfo import ZoneInfo
            tz_name = await self.config.guild(guild).timezone()
            server_tz = ZoneInfo(tz_name)
            event_local_time = event.start_time.astimezone(server_tz)
            
            # Build the expected role name using the configured format
            role_format = await self.config.guild(guild).role_format()
            
            day_abbrev = event_local_time.strftime("%a")  # Sun, Mon, etc.
            day = event_local_time.strftime("%d").lstrip("0")  # 28 (no leading zero)
            month_abbrev = event_local_time.strftime("%b")  # Dec, Jan, etc.
            time_str = event_local_time.strftime("%H:%M")  # 21:00
            
            expected_role_name = role_format.format(
                name=event.name,
                day_abbrev=day_abbrev,
                day=day,
                month_abbrev=month_abbrev,
                time=time_str
            )
            
            # Check for role with exponential backoff
            role = discord.utils.get(guild.roles, name=expected_role_name)
            if not role:
                # Try with exponential backoff: 5s, 10s, 20s, 40s... up to 60s total
                delay = 5
                total_waited = 0
                while not role and total_waited < 60:
                    await asyncio.sleep(delay)
                    total_waited += delay
                    role = discord.utils.get(guild.roles, name=expected_role_name)
                    if not role:
                        delay *= 2  # Double the delay each time
                
                # If still no role and event is starting soon/now, wait up to 1 minute after start time
                if not role:
                    now = datetime.now(timezone.utc)
                    time_until_start = (start_time - now).total_seconds()
                    
                    # If event starts within 15 seconds or already started (up to 1 min ago)
                    if -60 <= time_until_start <= 15:
                        log.info(f"Event '{event.name}' is starting imminently. Waiting up to 1 minute after start for role...")
                        
                        # Wait until 1 minute after event start using exponential backoff
                        one_min_after_start = start_time + timedelta(minutes=1)
                        deadline = one_min_after_start.timestamp()
                        
                        delay = 5
                        total_waited = 0
                        while not role and datetime.now(timezone.utc).timestamp() < deadline:
                            remaining_time = deadline - datetime.now(timezone.utc).timestamp()
                            sleep_time = min(delay, remaining_time)
                            
                            if sleep_time > 0:
                                await asyncio.sleep(sleep_time)
                                total_waited += sleep_time
                                role = discord.utils.get(guild.roles, name=expected_role_name)
                                if not role:
                                    delay *= 2  # Double the delay each time
                
                if not role:
                    log.warning(f"No matching role found for event '{event.name}'. Expected role: '{expected_role_name}'")
                    return  # Still no matching role → no channels created
            
            log.info(f"Found matching role '{expected_role_name}' for event '{event.name}'")

            # Check bot permissions
            bot_perms = guild.me.guild_permissions
            log.info(f"Bot permissions - manage_channels: {bot_perms.manage_channels}, administrator: {bot_perms.administrator}")
            
            if category:
                cat_perms = category.permissions_for(guild.me)
                log.info(f"Bot permissions in category '{category.name}' - manage_channels: {cat_perms.manage_channels}, manage_permissions: {cat_perms.manage_permissions}")

            # Check if bot's role is higher than the event role
            bot_top_role = guild.me.top_role
            log.info(f"Bot's top role: {bot_top_role.name} (position: {bot_top_role.position}), Event role: {role.name} (position: {role.position})")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                ),
                role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                ),
            }

            base_name = event.name.lower().replace(" ", "-")

            try:
                # Try creating without overwrites first to isolate the issue
                text_channel = await guild.create_text_channel(
                    name=f"{base_name}-text",
                    category=category,
                    reason="Scheduled event starting soon",
                )
                log.info(f"Created text channel without overwrites: {text_channel.name}")

                voice_channel = await guild.create_voice_channel(
                    name=f"{base_name}-voice",
                    category=category,
                    reason="Scheduled event starting soon",
                )
                log.info(f"Created voice channel without overwrites: {voice_channel.name}")
                
                # Now try to apply the overwrites
                try:
                    await text_channel.edit(overwrites=overwrites)
                    await voice_channel.edit(overwrites=overwrites)
                    log.info(f"Successfully applied permissions to channels for event '{event.name}'")
                except discord.Forbidden as e:
                    log.error(f"Could not apply permissions, but channels created: {e}")
                
                log.info(f"Created channels for event '{event.name}': {text_channel.name}, {voice_channel.name}")
            except discord.Forbidden as e:
                log.error(f"Missing permissions to create channels for event '{event.name}': {e}")
                return
            except Exception as e:
                log.error(f"Failed to create channels for event '{event.name}': {e}")
                return

            stored[str(event.id)] = {
                "text": text_channel.id,
                "voice": voice_channel.id,
                "role": role.id,
            }
            await self.config.guild(guild).event_channels.set(stored)

            # ---------- Cleanup ----------

            await asyncio.sleep(max(0, (delete_time - datetime.now(timezone.utc)).total_seconds()))

            data = stored.get(str(event.id))
            if not data:
                return

            for channel_id in (data["text"], data["voice"]):
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="Scheduled event ended")
                    except discord.NotFound:
                        pass

            role = guild.get_role(data["role"])
            if role:
                try:
                    await role.delete(reason="Scheduled event ended")
                except discord.Forbidden:
                    pass

            stored.pop(str(event.id), None)
            await self.config.guild(guild).event_channels.set(stored)
        except asyncio.CancelledError:
            # Task was cancelled - clean up if channels were created
            stored = await self.config.guild(guild).event_channels()
            data = stored.get(str(event.id))
            if data:
                for channel_id in (data["text"], data["voice"]):
                    channel = guild.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.delete(reason="Scheduled event cancelled")
                        except (discord.NotFound, discord.Forbidden):
                            pass
                stored.pop(str(event.id), None)
                await self.config.guild(guild).event_channels.set(stored)
            raise 
        finally:
            # Clean up task reference
            self.active_tasks.pop(event.id, None)

    # ---------- Event Listeners ----------

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        if event.guild and event.status == discord.EventStatus.scheduled:
            task = self.bot.loop.create_task(self._handle_event(event.guild, event))
            self.active_tasks[event.id] = task

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        """Cancel task and clean up channels when event is deleted."""
        task = self.active_tasks.get(event.id)
        if task and not task.done():
            task.cancel()

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        """Cancel task and clean up if event is cancelled or start time changes significantly."""
        if after.status == discord.EventStatus.cancelled:
            task = self.active_tasks.get(after.id)
            if task and not task.done():
                task.cancel()
        elif before.start_time != after.start_time and after.status == discord.EventStatus.scheduled:
            # Start time changed - cancel old task and create new one
            task = self.active_tasks.get(after.id)
            if task and not task.done():
                task.cancel()
            # Give a moment for cancellation to complete
            await asyncio.sleep(0.1)
            new_task = self.bot.loop.create_task(self._handle_event(after.guild, after))
            self.active_tasks[after.id] = new_task
    
    def cog_unload(self):
        """Cancel all active tasks when cog is unloaded."""
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()