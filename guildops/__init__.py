from redbot.core.bot import Red
from .guildops import GuildOps

async def setup(bot: Red) -> None:
    await bot.add_cog(GuildOps(bot))
