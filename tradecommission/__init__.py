"""Trade Commission cog for Where Winds Meet."""
from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .tradecommission import TradeCommission

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red) -> None:
    """Load TradeCommission cog."""
    cog = TradeCommission(bot)
    await bot.add_cog(cog)
