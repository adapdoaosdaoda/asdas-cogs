from .personalbork import PersonalBork

async def setup(bot):
    cog = PersonalBork(bot)
    await bot.add_cog(cog)
