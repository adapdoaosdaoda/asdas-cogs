"""Shared pytest fixtures for Red-Discord Bot cog testing."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from redbot.core import Config
from redbot.core.bot import Red


@pytest.fixture
def bot():
    """Mock Red bot instance."""
    bot = MagicMock(spec=Red)
    bot.user = MagicMock(spec=discord.ClientUser)
    bot.user.id = 123456789
    bot.user.name = "TestBot"
    bot.user.mention = "<@123456789>"
    return bot


@pytest.fixture
def guild():
    """Mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 987654321
    guild.name = "Test Guild"
    guild.me = MagicMock(spec=discord.Member)
    guild.me.id = 123456789
    guild.default_role = MagicMock(spec=discord.Role)
    guild.default_role.id = 987654321
    guild.get_role = MagicMock(return_value=None)
    return guild


@pytest.fixture
def channel():
    """Mock Discord text channel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111222333
    channel.name = "test-channel"
    channel.guild = MagicMock(spec=discord.Guild)
    channel.guild.id = 987654321
    channel.send = AsyncMock()
    return channel


@pytest.fixture
def member():
    """Mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 555666777
    member.name = "TestUser"
    member.display_name = "TestUser"
    member.mention = "<@555666777>"
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = 987654321
    return member


@pytest.fixture
def role():
    """Mock Discord role."""
    role = MagicMock(spec=discord.Role)
    role.id = 444555666
    role.name = "Test Role"
    role.mention = "<@&444555666>"
    return role


@pytest.fixture
def ctx(bot, guild, channel, member):
    """Mock command context."""
    ctx = MagicMock()
    ctx.bot = bot
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = member
    ctx.send = AsyncMock()
    ctx.tick = AsyncMock()
    return ctx


@pytest.fixture
def config():
    """Mock Config instance."""
    # Create a mock that behaves like Red's Config
    config = MagicMock(spec=Config)

    # Mock guild config
    guild_config = MagicMock()
    guild_config.all = AsyncMock(return_value={})
    guild_config.get_raw = AsyncMock(return_value=None)
    guild_config.set_raw = AsyncMock()
    guild_config.clear = AsyncMock()
    config.guild.return_value = guild_config

    # Mock member config
    member_config = MagicMock()
    member_config.all = AsyncMock(return_value={})
    member_config.get_raw = AsyncMock(return_value=None)
    member_config.set_raw = AsyncMock()
    member_config.clear = AsyncMock()
    config.member.return_value = member_config

    # Mock user config
    user_config = MagicMock()
    user_config.all = AsyncMock(return_value={})
    user_config.get_raw = AsyncMock(return_value=None)
    user_config.set_raw = AsyncMock()
    user_config.clear = AsyncMock()
    config.user.return_value = user_config

    # Mock channel config
    channel_config = MagicMock()
    channel_config.all = AsyncMock(return_value={})
    channel_config.get_raw = AsyncMock(return_value=None)
    channel_config.set_raw = AsyncMock()
    channel_config.clear = AsyncMock()
    config.channel.return_value = channel_config

    return config
