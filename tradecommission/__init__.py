"""Trade Commission cog for Where Winds Meet."""
from redbot.core.bot import Red

from .tradecommission import TradeCommission


async def setup(bot: Red) -> None:
    """Load TradeCommission cog."""
    cog = TradeCommission(bot)
    await bot.add_cog(cog)
