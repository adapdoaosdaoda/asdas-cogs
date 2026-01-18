from .modalpatch import ModalPatch

async def setup(bot):
    cog = ModalPatch(bot)
    await bot.add_cog(cog)
