from .activitylogger import ActivityLogger

async def setup(bot):
    await bot.add_cog(ActivityLogger(bot))
