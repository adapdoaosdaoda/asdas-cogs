import discord
import logging
import asyncio
from typing import Optional, Tuple

from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from aiomcrcon import Client, RCONConnectionError, IncorrectPasswordError

log = logging.getLogger("red.asdas-cogs.mcwhitelist")

class MCWhitelist(commands.Cog):
    """
    Whitelist players on a Minecraft server via RCON using /easywhitelist.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8273645190, force_registration=True)

        default_guild = {
            "host": "127.0.0.1",
            "port": 25575,
            "password": "",
        }
        self.config.register_guild(**default_guild)

    async def _send_rcon(self, guild: discord.Guild, command: str) -> Tuple[bool, str]:
        """Sends a command via RCON and returns (success, response)."""
        conf = await self.config.guild(guild).all()
        host = conf["host"]
        port = conf["port"]
        password = conf["password"]

        if not password:
            return False, "RCON password is not set. Use `[p]mcset password` to set it."

        client = Client(host, port, password)
        try:
            await client.connect()
            response, _ = await client.send_cmd(command)
            await client.close()
            return True, response
        except RCONConnectionError:
            return False, f"Could not connect to RCON server at {host}:{port}."
        except IncorrectPasswordError:
            return False, "Incorrect RCON password."
        except Exception as e:
            log.error(f"RCON Error: {e}")
            return False, f"An unexpected error occurred: {e}"

    @commands.group(name="mcwhitelist", aliases=["mcwl"], invoke_without_command=True)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def mcwhitelist(self, ctx, player: Optional[str] = None):
        """
        Add a player to the Minecraft whitelist.
        
        Usage: [p]mcwhitelist <player>
        """
        if ctx.invoked_subcommand is None:
            if player is None:
                await ctx.send_help()
                return

            async with ctx.typing():
                success, response = await self._send_rcon(ctx.guild, f"easywhitelist add {player}")
                if success:
                    await ctx.send(f"✅ Successfully added `{player}` to the whitelist.\n**Server response:** {response}")
                else:
                    await ctx.send(f"❌ Failed to add `{player}` to the whitelist: {response}")

    @mcwhitelist.command(name="remove")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def mcwhitelist_remove(self, ctx, player: str):
        """
        Remove a player from the Minecraft whitelist.
        
        Usage: [p]mcwhitelist remove <player>
        """
        async with ctx.typing():
            success, response = await self._send_rcon(ctx.guild, f"easywhitelist remove {player}")
            if success:
                await ctx.send(f"✅ Successfully removed `{player}` from the whitelist.\n**Server response:** {response}")
            else:
                await ctx.send(f"❌ Failed to remove `{player}` from the whitelist: {response}")

    @commands.group(name="mcset")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def mcset(self, ctx):
        """Configure Minecraft RCON settings."""
        pass

    @mcset.command(name="host")
    async def mcset_host(self, ctx, host: str):
        """Set the RCON server host."""
        await self.config.guild(ctx.guild).host.set(host)
        await ctx.send(f"RCON host set to `{host}`.")

    @mcset.command(name="port")
    async def mcset_port(self, ctx, port: int):
        """Set the RCON server port."""
        if not (1 <= port <= 65535):
            await ctx.send("❌ Port must be between 1 and 65535.")
            return
        await self.config.guild(ctx.guild).port.set(port)
        await ctx.send(f"RCON port set to `{port}`.")

    @mcset.command(name="password")
    async def mcset_password(self, ctx, password: str):
        """Set the RCON server password."""
        await self.config.guild(ctx.guild).password.set(password)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send("RCON password set (and message deleted for security).")

    @mcset.command(name="settings")
    async def mcset_settings(self, ctx):
        """Show current RCON settings."""
        conf = await self.config.guild(ctx.guild).all()
        host = conf["host"]
        port = conf["port"]
        has_password = "Yes" if conf["password"] else "No"
        
        embed = discord.Embed(title="Minecraft RCON Settings", color=discord.Color.blue())
        embed.add_field(name="Host", value=host, inline=True)
        embed.add_field(name="Port", value=port, inline=True)
        embed.add_field(name="Password Set", value=has_password, inline=True)
        
        await ctx.send(embed=embed)
