"""BorkedSince cog for tracking bot uptime streaks."""
from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .borkedsince import BorkedSince

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red) -> None:
    """Load BorkedSince cog."""
    await bot.add_cog(BorkedSince(bot))
