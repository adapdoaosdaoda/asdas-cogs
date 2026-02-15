from .mcwhitelist import MCWhitelist

async def setup(bot):
    await bot.add_cog(MCWhitelist(bot))
