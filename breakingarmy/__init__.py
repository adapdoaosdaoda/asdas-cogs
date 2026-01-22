from .breakingarmy import BreakingArmy

async def setup(bot):
    await bot.add_cog(BreakingArmy(bot))
