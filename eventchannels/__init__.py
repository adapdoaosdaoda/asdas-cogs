from .eventchannels import EventChannels

async def setup(bot):
    await bot.add_cog(EventChannels(bot))
