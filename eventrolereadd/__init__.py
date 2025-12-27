from .rolereadd import EventRoleReadd

async def setup(bot):
    await bot.add_cog(EventRoleReadd(bot))
