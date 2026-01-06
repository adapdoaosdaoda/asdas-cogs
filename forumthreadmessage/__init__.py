from .forumthreadmessage import ForumThreadMessage


async def setup(bot):
    """Load ForumThreadMessage cog."""
    await bot.add_cog(ForumThreadMessage(bot))
