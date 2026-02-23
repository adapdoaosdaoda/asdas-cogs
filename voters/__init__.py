from .voters import Voters

async def setup(bot):
    await bot.add_cog(Voters(bot))
