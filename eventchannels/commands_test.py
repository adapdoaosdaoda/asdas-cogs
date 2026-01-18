import asyncio
from datetime import datetime, timedelta, timezone
import logging

import discord
from redbot.core import commands

log = logging.getLogger("red.eventchannels")


class CommandsTestMixin:
    """Mixin class containing test commands for EventChannels cog."""

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def testchannellock(self, ctx):
        """Test the channel locking mechanism to verify bot permissions."""
        guild = ctx.guild
        category_id = await self.config.guild(guild).category_id()
        category = guild.get_channel(category_id) if category_id else None

        if not category:
            await ctx.send(f"❌ No event category configured. Use `{ctx.clean_prefix}eventchannels setcategory` first.")
            return

        await ctx.send("🔄 Starting channel lock test...")

        test_role = None
        test_text_channel = None
        test_voice_channel = None

        try:
            # Create a test role
            test_role = await guild.create_role(
                name="🧪 Test Event Role",
                reason="Testing channel lock mechanism"
            )
            await ctx.send(f"✅ Created test role: {test_role.mention}")

            # Create test channels with permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                ),
                test_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                ),
            }

            # Create text channel without overwrites first
            test_text_channel = await guild.create_text_channel(
                name="🧪-test-event-text",
                category=category,
                reason="Testing channel lock mechanism"
            )
            await ctx.send(f"✅ Created test text channel: {test_text_channel.mention}")

            # Create voice channel without overwrites first
            test_voice_channel = await guild.create_voice_channel(
                name="🧪 Test Event Voice",
                category=category,
                reason="Testing channel lock mechanism"
            )
            await ctx.send(f"✅ Created test voice channel: `{test_voice_channel.name}`")

            # Now apply permission overwrites
            await test_text_channel.edit(overwrites=overwrites)
            await test_voice_channel.edit(overwrites=overwrites)
            await ctx.send(f"✅ Applied permission overwrites to channels")

            # Now attempt to lock the channels using the same logic as the actual deletion process
            await ctx.send("🔒 Attempting to lock channels...")

            locked_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                ),
                test_role: discord.PermissionOverwrite(
                    send_messages=False,  # Locked
                    speak=False,  # Locked in voice
                ),
            }

            await test_text_channel.edit(overwrites=locked_overwrites, reason="Testing channel lock")
            await test_voice_channel.edit(overwrites=locked_overwrites, reason="Testing channel lock")

            await ctx.send("✅ **SUCCESS**: Channels locked successfully!")
            await ctx.send("✅ Bot has correct permissions to lock channels before deletion.")

        except discord.Forbidden as e:
            await ctx.send(f"❌ **FAILED**: Missing permissions to lock channels.\n```{e}```")
        except Exception as e:
            await ctx.send(f"❌ **ERROR**: {type(e).__name__}: {e}")
        finally:
            # Cleanup
            await ctx.send("🧹 Cleaning up test channels and role...")
            if test_text_channel:
                try:
                    await test_text_channel.delete(reason="Channel lock test completed")
                except:
                    pass
            if test_voice_channel:
                try:
                    await test_voice_channel.delete(reason="Channel lock test completed")
                except:
                    pass
            if test_role:
                try:
                    await test_role.delete(reason="Channel lock test completed")
                except:
                    pass
            await ctx.send("✅ Test complete and cleanup finished.")

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def testeventroles(self, ctx, role: discord.Role = None):
        """Test command to see how many users have a given role for current events.

        If no role is specified, shows member counts for all scheduled event roles.
        If a role is specified, shows the count for that specific role.
        """
        from zoneinfo import ZoneInfo

        guild = ctx.guild

        # Fetch all scheduled events
        try:
            events = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            await ctx.send("❌ Bot lacks permission to fetch scheduled events.")
            return

        # Filter to only scheduled events
        scheduled_events = [e for e in events if e.status == discord.EventStatus.scheduled]

        if not scheduled_events:
            await ctx.send("❌ No scheduled events found.")
            return

        # Get timezone and role format settings
        tz_name = await self.config.guild(guild).timezone()
        role_format = await self.config.guild(guild).role_format()
        server_tz = ZoneInfo(tz_name)

        # Build mapping of event -> expected role name -> actual role
        event_role_map = {}
        for event in scheduled_events:
            event_local_time = event.start_time.astimezone(server_tz)

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

            # Find the role with this name
            event_role = discord.utils.get(guild.roles, name=expected_role_name)
            event_role_map[event] = (expected_role_name, event_role)

        if role:
            # Find which event(s) this role belongs to
            matching_events = []
            for event, (expected_name, event_role) in event_role_map.items():
                if event_role and event_role.id == role.id:
                    matching_events.append(event)

            if not matching_events:
                await ctx.send(f"❌ Role {role.mention} does not match any scheduled event roles.")
                return

            # Show member count for this role
            member_count, is_reliable = await self._get_role_member_count(guild, role)

            embed = discord.Embed(
                title=f"Event Role Member Count: {role.name}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Member Count",
                value=f"{member_count} members",
                inline=False
            )

            if not is_reliable:
                embed.add_field(
                    name="⚠️ Warning",
                    value="Member count may be incomplete. Enable GUILD_MEMBERS intent for accurate counts.",
                    inline=False
                )

            # List associated events
            embed.add_field(
                name="Associated Events",
                value="\n".join(f"• {event.name}" for event in matching_events),
                inline=False
            )

            await ctx.send(embed=embed)

        else:
            # Show all event roles and their member counts
            embed = discord.Embed(
                title="Event Role Member Counts",
                description="Member counts for all scheduled event roles",
                color=discord.Color.blue()
            )

            total_events = 0
            unreliable_counts = 0

            for event, (expected_name, event_role) in event_role_map.items():
                if not event_role:
                    embed.add_field(
                        name=f"⚠️ {event.name}",
                        value=f"Expected role `{expected_name}` not found",
                        inline=False
                    )
                    total_events += 1
                    continue

                member_count, is_reliable = await self._get_role_member_count(guild, event_role, event.name)

                status_emoji = "⚠️" if not is_reliable else "✅"
                reliability_note = " (may be incomplete)" if not is_reliable else ""

                embed.add_field(
                    name=f"{status_emoji} {event.name}",
                    value=f"Role: {event_role.mention}\nMembers: **{member_count}**{reliability_note}",
                    inline=False
                )

                total_events += 1
                if not is_reliable:
                    unreliable_counts += 1

            if unreliable_counts > 0:
                embed.set_footer(
                    text=f"⚠️ {unreliable_counts} count(s) may be incomplete. Enable GUILD_MEMBERS intent for accuracy."
                )

            await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def stresstest(self, ctx):
        """Comprehensive stress test of all EventChannels features including end-to-end event automation."""
        guild = ctx.guild
        category_id = await self.config.guild(guild).category_id()
        category = guild.get_channel(category_id) if category_id else None

        if not category:
            await ctx.send(f"❌ No event category configured. Use `{ctx.clean_prefix}eventchannels setcategory` first.")
            return

        await ctx.send("🚀 **Starting comprehensive EventChannels stress test...**")
        await ctx.send("This will test: channel creation, permissions, voice multipliers, divider, locking, event automation, and cleanup.")

        # Track all created resources for cleanup
        test_roles = []
        test_channels = []
        test_events = []
        original_divider_roles = await self.config.guild(guild).divider_roles()
        test_results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }

        async def report_success(test_name: str):
            test_results["passed"] += 1
            await ctx.send(f"✅ **{test_name}**: PASSED")

        async def report_failure(test_name: str, error: str):
            test_results["failed"] += 1
            test_results["errors"].append(f"{test_name}: {error}")
            await ctx.send(f"❌ **{test_name}**: FAILED - {error}")

        try:
            # ========== TEST 1: End-to-End Event Creation ==========
            await ctx.send("\n**TEST 1: End-to-End Event Creation with Matching Role**")
            try:
                from zoneinfo import ZoneInfo

                # Get the server's configured timezone and role format
                tz_name = await self.config.guild(guild).timezone()
                server_tz = ZoneInfo(tz_name)
                role_format = await self.config.guild(guild).role_format()

                # Create a scheduled event that starts in 2 minutes
                event_start = datetime.now(timezone.utc) + timedelta(minutes=2)
                event_local_time = event_start.astimezone(server_tz)

                # Format the expected role name
                day_abbrev = event_local_time.strftime("%a")
                day = event_local_time.strftime("%d").lstrip("0")
                month_abbrev = event_local_time.strftime("%b")
                time_str = event_local_time.strftime("%H:%M")

                event_name = "🧪 E2E Test Event"
                expected_role_name = role_format.format(
                    name=event_name,
                    day_abbrev=day_abbrev,
                    day=day,
                    month_abbrev=month_abbrev,
                    time=time_str
                )

                # Create the matching role BEFORE creating the event
                e2e_role = await guild.create_role(
                    name=expected_role_name,
                    reason="E2E stress test - matching role for scheduled event"
                )
                test_roles.append(e2e_role)
                await ctx.send(f"✅ Created matching role: `{expected_role_name}`")

                # Create a voice channel for the event (required for voice entity type)
                e2e_voice_channel = await guild.create_voice_channel(
                    name="🧪 E2E Test Voice",
                    category=category,
                    reason="E2E stress test - voice channel for event"
                )
                test_channels.append(e2e_voice_channel)
                await ctx.send(f"✅ Created voice channel for event: `{e2e_voice_channel.name}`")

                # Create the scheduled event
                test_event = await guild.create_scheduled_event(
                    name=event_name,
                    start_time=event_start,
                    entity_type=discord.EntityType.voice,
                    privacy_level=discord.PrivacyLevel.guild_only,
                    channel=e2e_voice_channel,
                    reason="E2E stress test"
                )
                test_events.append(test_event)
                await ctx.send(f"✅ Created scheduled event: `{event_name}` (starts in 2 minutes)")

                # Wait for the bot to process the event (should create channels in 2 mins - 15 mins = immediately)
                creation_minutes = await self.config.guild(guild).creation_minutes()
                if creation_minutes >= 2:
                    # Channels should be created immediately
                    await ctx.send(f"⏳ Waiting for bot to process event (creation time: {creation_minutes} mins before start)...")
                    await asyncio.sleep(10)  # Wait 10 seconds for bot to create channels

                    # Check if channels were created
                    stored = await self.config.guild(guild).event_channels()
                    event_data = stored.get(str(test_event.id))

                    if event_data:
                        text_ch = guild.get_channel(event_data.get("text"))
                        voice_ch_ids = event_data.get("voice", [])
                        if isinstance(voice_ch_ids, int):
                            voice_ch_ids = [voice_ch_ids]

                        if text_ch and voice_ch_ids:
                            await ctx.send(f"✅ Bot automatically created channels: {text_ch.mention}")
                            # Track channels for cleanup
                            test_channels.append(text_ch)
                            for vc_id in voice_ch_ids:
                                vc = guild.get_channel(vc_id)
                                if vc:
                                    test_channels.append(vc)
                            await report_success("End-to-End Event Creation")
                        else:
                            await report_failure("End-to-End Event Creation", "Channels not found after creation")
                    else:
                        await report_failure("End-to-End Event Creation", "Event data not stored in config")
                else:
                    await ctx.send(f"⏭️ Skipping channel verification (creation time is {creation_minutes} mins, event starts in 2 mins)")
                    await report_success("End-to-End Event Creation (event created, channels scheduled)")

            except Exception as e:
                await report_failure("End-to-End Event Creation", str(e))

            # ========== TEST 2: Basic Channel Creation ==========
            await ctx.send("\n**TEST 2: Basic Channel Creation**")
            try:
                role1 = await guild.create_role(name="🧪 Stress Test Role 1", reason="Stress testing")
                test_roles.append(role1)

                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                    role1: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        connect=True,
                        speak=True,
                    ),
                }

                # Create channels without overwrites first
                text_ch1 = await guild.create_text_channel(
                    name="🧪-stress-test-1",
                    category=category,
                    reason="Stress testing"
                )
                test_channels.append(text_ch1)

                voice_ch1 = await guild.create_voice_channel(
                    name="🧪 Stress Test Voice 1",
                    category=category,
                    reason="Stress testing"
                )
                test_channels.append(voice_ch1)

                # Now apply permission overwrites
                await text_ch1.edit(overwrites=overwrites)
                await voice_ch1.edit(overwrites=overwrites)

                await report_success("Basic Channel Creation")
            except Exception as e:
                await report_failure("Basic Channel Creation", str(e))

            # ========== TEST 3: Permission Verification ==========
            await ctx.send("\n**TEST 3: Permission Verification**")
            try:
                # Verify bot can see and manage channels
                if text_ch1.permissions_for(guild.me).view_channel and \
                   text_ch1.permissions_for(guild.me).manage_channels and \
                   text_ch1.permissions_for(guild.me).send_messages:
                    await report_success("Bot Permission Verification")
                else:
                    await report_failure("Bot Permission Verification", "Bot missing expected permissions")

                # Verify role can see channels
                if text_ch1.permissions_for(role1).view_channel and \
                   text_ch1.permissions_for(role1).send_messages:
                    await report_success("Role Permission Verification")
                else:
                    await report_failure("Role Permission Verification", "Role missing expected permissions")

                # Verify default role cannot see
                if not text_ch1.permissions_for(guild.default_role).view_channel:
                    await report_success("Default Role Hidden Verification")
                else:
                    await report_failure("Default Role Hidden Verification", "Default role can see channel")
            except Exception as e:
                await report_failure("Permission Verification", str(e))

            # ========== TEST 4: Multiple Voice Channels (Voice Multiplier Simulation) ==========
            await ctx.send("\n**TEST 4: Multiple Voice Channels**")
            try:
                role2 = await guild.create_role(name="🧪 Stress Test Role 2", reason="Stress testing")
                test_roles.append(role2)

                # Create 3 voice channels to simulate voice multiplier
                for i in range(3):
                    voice_ch = await guild.create_voice_channel(
                        name=f"🧪 Multi Voice {i+1}",
                        category=category,
                        user_limit=5,
                        reason="Stress testing voice multiplier"
                    )
                    test_channels.append(voice_ch)

                await report_success("Multiple Voice Channels Creation")
            except Exception as e:
                await report_failure("Multiple Voice Channels Creation", str(e))

            # ========== TEST 5: Divider Channel Updates ==========
            await ctx.send("\n**TEST 5: Divider Channel Updates**")
            try:
                # Check if divider is configured first
                divider_channel_id = await self.config.guild(guild).divider_channel_id()
                if not divider_channel_id:
                    await ctx.send("⏭️ Skipping Divider Channel test (no divider configured)")
                    await report_success("Divider Channel Updates (skipped - not configured)")
                else:
                    # Test adding roles to divider
                    await self._update_divider_permissions(guild, role1, add=True)
                    await asyncio.sleep(0.5)  # Brief delay for operation
                    await self._update_divider_permissions(guild, role2, add=True)
                    await asyncio.sleep(0.5)

                    divider = guild.get_channel(divider_channel_id)
                    if divider:
                        # Verify roles have access
                        if divider.permissions_for(role1).view_channel and \
                           divider.permissions_for(role2).view_channel:
                            await report_success("Divider Role Permissions")
                        else:
                            await report_failure("Divider Role Permissions", "Roles don't have view access")
                    else:
                        await report_failure("Divider Channel Updates", "Divider channel not found")
            except Exception as e:
                await report_failure("Divider Channel Updates", str(e))

            # ========== TEST 6: Message Sending ==========
            await ctx.send("\n**TEST 6: Message Sending**")
            try:
                test_msg = await text_ch1.send("🧪 Stress test message")
                await asyncio.sleep(0.5)
                await test_msg.delete()
                await report_success("Message Sending and Deletion")
            except Exception as e:
                await report_failure("Message Sending", str(e))

            # ========== TEST 7: Channel Locking ==========
            await ctx.send("\n**TEST 7: Channel Locking Mechanism**")
            try:
                locked_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                    role1: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        connect=True,
                        speak=False,
                    ),
                }

                await text_ch1.edit(overwrites=locked_overwrites, reason="Stress test lock")
                await voice_ch1.edit(overwrites=locked_overwrites, reason="Stress test lock")

                # Verify lock worked
                if not text_ch1.permissions_for(role1).send_messages and \
                   not voice_ch1.permissions_for(role1).speak:
                    await report_success("Channel Locking")
                else:
                    await report_failure("Channel Locking", "Permissions not properly locked")
            except Exception as e:
                await report_failure("Channel Locking", str(e))

            # ========== TEST 8: Concurrent Operations ==========
            await ctx.send("\n**TEST 8: Concurrent Channel Operations**")
            try:
                # Create multiple channels concurrently
                role3 = await guild.create_role(name="🧪 Concurrent Test Role", reason="Stress testing")
                test_roles.append(role3)

                tasks = []
                for i in range(3):
                    task = guild.create_text_channel(
                        name=f"🧪-concurrent-{i}",
                        category=category,
                        reason="Concurrent stress test"
                    )
                    tasks.append(task)

                concurrent_channels = await asyncio.gather(*tasks)
                test_channels.extend(concurrent_channels)

                if len(concurrent_channels) == 3:
                    await report_success("Concurrent Channel Creation")
                else:
                    await report_failure("Concurrent Channel Creation", f"Expected 3 channels, got {len(concurrent_channels)}")
            except Exception as e:
                await report_failure("Concurrent Channel Creation", str(e))

            # ========== TEST 9: Channel Name Formatting ==========
            await ctx.send("\n**TEST 9: Channel Name Formatting**")
            try:
                space_replacer = await self.config.guild(guild).space_replacer()
                test_name = "Test Event Name"
                formatted_name = test_name.lower().replace(" ", space_replacer)

                format_test_ch = await guild.create_text_channel(
                    name=f"🧪-{formatted_name}",
                    category=category,
                    reason="Testing name formatting"
                )
                test_channels.append(format_test_ch)

                if space_replacer in format_test_ch.name:
                    await report_success("Channel Name Formatting")
                else:
                    await report_failure("Channel Name Formatting", "Space replacer not applied correctly")
            except Exception as e:
                await report_failure("Channel Name Formatting", str(e))

            # ========== TEST 10: Rapid Create/Delete Cycle ==========
            await ctx.send("\n**TEST 10: Rapid Create/Delete Cycle**")
            try:
                temp_channels = []
                # Create 5 channels
                for i in range(5):
                    temp_ch = await guild.create_text_channel(
                        name=f"🧪-temp-{i}",
                        category=category,
                        reason="Rapid cycle test"
                    )
                    temp_channels.append(temp_ch)

                await asyncio.sleep(1)

                # Delete them all
                for ch in temp_channels:
                    await ch.delete(reason="Rapid cycle test cleanup")

                await report_success("Rapid Create/Delete Cycle")
            except Exception as e:
                await report_failure("Rapid Create/Delete Cycle", str(e))

            # ========== TEST 11: Permission Overwrite Updates ==========
            await ctx.send("\n**TEST 11: Permission Overwrite Updates**")
            try:
                # Update permissions on existing channel
                new_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                    role3: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    ),
                }

                await concurrent_channels[0].edit(overwrites=new_overwrites, reason="Permission update test")

                if concurrent_channels[0].permissions_for(role3).view_channel:
                    await report_success("Permission Overwrite Updates")
                else:
                    await report_failure("Permission Overwrite Updates", "Updated permissions not applied")
            except Exception as e:
                await report_failure("Permission Overwrite Updates", str(e))

        except Exception as e:
            await ctx.send(f"💥 **CRITICAL ERROR**: {type(e).__name__}: {e}")
            test_results["errors"].append(f"Critical: {e}")

        finally:
            # ========== CLEANUP ==========
            await ctx.send("\n**🧹 CLEANUP: Removing all test resources...**")

            # Remove test roles from divider
            try:
                for role in test_roles:
                    await self._update_divider_permissions(guild, role, add=False)
            except Exception as e:
                await ctx.send(f"⚠️ Warning during divider cleanup: {e}")

            # Delete all test channels
            deleted_channels = 0
            for channel in test_channels:
                try:
                    await channel.delete(reason="Stress test cleanup")
                    deleted_channels += 1
                except:
                    pass

            # Delete all test roles
            deleted_roles = 0
            for role in test_roles:
                try:
                    await role.delete(reason="Stress test cleanup")
                    deleted_roles += 1
                except:
                    pass

            # Delete all test events
            deleted_events = 0
            for event in test_events:
                try:
                    await event.delete(reason="Stress test cleanup")
                    deleted_events += 1
                except:
                    pass

            if deleted_events > 0:
                await ctx.send(f"✅ Cleanup complete: {deleted_channels} channels, {deleted_roles} roles, {deleted_events} events removed")
            else:
                await ctx.send(f"✅ Cleanup complete: {deleted_channels} channels, {deleted_roles} roles removed")

            # ========== FINAL REPORT ==========
            await ctx.send("\n" + "="*50)
            await ctx.send("**📊 STRESS TEST RESULTS**")
            await ctx.send("="*50)

            total_tests = test_results["passed"] + test_results["failed"]
            pass_rate = (test_results["passed"] / total_tests * 100) if total_tests > 0 else 0

            embed = discord.Embed(
                title="EventChannels Stress Test Results",
                color=discord.Color.green() if test_results["failed"] == 0 else discord.Color.orange()
            )
            embed.add_field(name="Total Tests", value=str(total_tests), inline=True)
            embed.add_field(name="Passed ✅", value=str(test_results["passed"]), inline=True)
            embed.add_field(name="Failed ❌", value=str(test_results["failed"]), inline=True)
            embed.add_field(name="Pass Rate", value=f"{pass_rate:.1f}%", inline=False)

            if test_results["errors"]:
                error_text = "\n".join([f"• {err}" for err in test_results["errors"][:10]])  # Limit to 10 errors
                embed.add_field(name="Errors", value=error_text, inline=False)

            try:
                await ctx.send(embed=embed)
            except:
                # Fallback to text
                await ctx.send(
                    f"**Total Tests**: {total_tests}\n"
                    f"**Passed**: {test_results['passed']} ✅\n"
                    f"**Failed**: {test_results['failed']} ❌\n"
                    f"**Pass Rate**: {pass_rate:.1f}%"
                )

            if test_results["failed"] == 0:
                await ctx.send("🎉 **ALL TESTS PASSED!** EventChannels cog is functioning correctly.")
            else:
                await ctx.send("⚠️ **SOME TESTS FAILED** - Review errors above for details.")
