from redbot.core.bot import Red
from .monkeymodal import MonkeyModal

async def setup(bot: Red) -> None:
    """Load the MonkeyModal cog"""
    cog = MonkeyModal(bot)
    await bot.add_cog(cog)
