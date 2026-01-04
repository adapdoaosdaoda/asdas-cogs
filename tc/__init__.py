from .tc import TC

async def setup(bot):
    """Load the TC cog."""
    await bot.add_cog(TC(bot))
