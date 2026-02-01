from .guildops import GuildOps

async def setup(bot):
    await bot.add_cog(GuildOps(bot))
