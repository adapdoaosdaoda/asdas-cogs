"""BorkedSince cog for tracking bot uptime streaks."""
from .borkedsince import BorkedSince


async def setup(bot):
    """Load BorkedSince cog."""
    await bot.add_cog(BorkedSince(bot))
