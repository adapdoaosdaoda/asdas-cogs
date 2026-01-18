from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement
from redbot.core.errors import CogLoadError
import logging

from .polling import EventPolling

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

log = logging.getLogger("red.asdas-cogs.polling")


async def setup(bot: Red) -> None:
    # Check if ModalPatch cog is loaded (optional dependency)
    modalpatch_loaded = bot.get_cog("ModalPatch") is not None

    if not modalpatch_loaded:
        log.warning(
            "ModalPatch cog is not loaded. The polling cog will work with reduced functionality. "
            "To enable rich modal features, install and load the modalpatch cog: "
            "[p]load modalpatch"
        )

    cog = EventPolling(bot)
    await bot.add_cog(cog)
