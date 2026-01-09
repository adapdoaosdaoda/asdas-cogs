from redbot.core.bot import Red
from .polling import EventPolling


async def setup(bot: Red) -> None:
    cog = EventPolling(bot)
    await bot.add_cog(cog)
