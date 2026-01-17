from redbot.core.bot import Red
from .modalpatch import ModalPatch

async def setup(bot: Red) -> None:
    cog = ModalPatch(bot)
    await bot.add_cog(cog)
