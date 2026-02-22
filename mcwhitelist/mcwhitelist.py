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
    Whitelist players on a Minecraft server via RCON.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8273645190, force_registration=True)

        default_global = {
            "host": "127.0.0.1",
            "port": 25575,
            "password": "",
            "java_prefix": "",
            "bedrock_prefix": ".",
        }
        self.config.register_global(**default_global)

    async def _send_rcon(self, command: str) -> Tuple[bool, str]:
        """Sends a command via RCON and returns (success, response)."""
        conf = await self.config.all()
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

            prefix = await self.config.java_prefix()
            player_name = f"{prefix}{player}"
            async with ctx.typing():
                success, response = await self._send_rcon(f'whitelist add {player_name}')
                if success:
                    await ctx.send(f"✅ Successfully added `{player_name}` to the whitelist.\n**Server response:** {response}")
                else:
                    await ctx.send(f"❌ Failed to add `{player_name}` to the whitelist: {response}")

    @mcwhitelist.command(name="remove", aliases=["rm"])
    @checks.admin_or_permissions(manage_guild=True)
    async def mcwhitelist_remove(self, ctx, player: str):
        """
        Remove a player from the Minecraft whitelist.
        
        Usage: [p]mcwhitelist remove <player>
        """
        prefix = await self.config.java_prefix()
        player_name = f"{prefix}{player}"
        async with ctx.typing():
            success, response = await self._send_rcon(f'whitelist remove {player_name}')
            if success:
                await ctx.send(f"✅ Successfully removed `{player_name}` from the whitelist.\n**Server response:** {response}")
            else:
                await ctx.send(f"❌ Failed to remove `{player_name}` from the whitelist: {response}")

    @mcwhitelist.command(name="bedrock")
    @checks.admin_or_permissions(manage_guild=True)
    async def mcwhitelist_bedrock(self, ctx, player: str):
        """
        Add a Bedrock player to the Minecraft whitelist.
        
        Usage: [p]mcwhitelist bedrock <player>
        """
        async with ctx.typing():
            success, response = await self._send_rcon(f'fwhitelist add {player}')
            if success:
                await ctx.send(f"✅ Successfully added Bedrock player `{player}` to the whitelist.\n**Server response:** {response}")
            else:
                await ctx.send(f"❌ Failed to add `{player}` to the whitelist: {response}")

    @mcwhitelist.command(name="removebedrock", aliases=["rmbedrock", "bedrockremove"])
    @checks.admin_or_permissions(manage_guild=True)
    async def mcwhitelist_remove_bedrock(self, ctx, player: str):
        """
        Remove a Bedrock player from the Minecraft whitelist.
        
        Usage: [p]mcwhitelist removebedrock <player>
        """
        async with ctx.typing():
            success, response = await self._send_rcon(f'fwhitelist remove {player}')
            if success:
                await ctx.send(f"✅ Successfully removed Bedrock player `{player}` from the whitelist.\n**Server response:** {response}")
            else:
                await ctx.send(f"❌ Failed to remove `{player}` from the whitelist: {response}")

    @mcwhitelist.command(name="list")
    @checks.admin_or_permissions(manage_guild=True)
    async def mcwhitelist_list(self, ctx):
        """
        List all whitelisted players.
        """
        async with ctx.typing():
            success, response = await self._send_rcon("whitelist list")
            if not success:
                await ctx.send(f"❌ Failed to fetch whitelist: {response}")
                return

            # Typical response: "There are 3 whitelisted players: player1, player2, player3"
            # Or: "There are no whitelisted players"
            if "players: " not in response:
                await ctx.send("There are no whitelisted players.")
                return

            players_str = response.split("players: ")[1]
            players = [p.strip() for p in players_str.split(", ")]

            b_prefix = await self.config.bedrock_prefix()
            j_prefix = await self.config.java_prefix()

            java_players = []
            bedrock_players = []
            unknown_players = []

            for player in players:
                if b_prefix and player.startswith(b_prefix):
                    bedrock_players.append(player)
                elif j_prefix and player.startswith(j_prefix):
                    java_players.append(player)
                elif not j_prefix: # If java prefix is empty, assume others are java
                     java_players.append(player)
                else:
                    unknown_players.append(player)

            embed = discord.Embed(title="Whitelisted Players", color=discord.Color.green())
            if java_players:
                embed.add_field(name="☕ Java Players", value="\n".join(java_players), inline=False)
            if bedrock_players:
                embed.add_field(name="📱 Bedrock Players", value="\n".join(bedrock_players), inline=False)
            if unknown_players:
                embed.add_field(name="❓ Unknown Players", value="\n".join(unknown_players), inline=False)
            
            if not java_players and not bedrock_players and not unknown_players:
                embed.description = "No players found in the whitelist response."

            await ctx.send(embed=embed)

    @commands.group(name="mcset")
    @checks.is_owner()
    async def mcset(self, ctx):
        """Configure Minecraft RCON settings."""
        pass

    @mcset.command(name="host")
    async def mcset_host(self, ctx, host: str):
        """Set the RCON server host."""
        await self.config.host.set(host)
        await ctx.send(f"RCON host set to `{host}`.")

    @mcset.command(name="port")
    async def mcset_port(self, ctx, port: int):
        """Set the RCON server port."""
        if not (1 <= port <= 65535):
            await ctx.send("❌ Port must be between 1 and 65535.")
            return
        await self.config.port.set(port)
        await ctx.send(f"RCON port set to `{port}`.")

    @mcset.command(name="password")
    async def mcset_password(self, ctx, password: str):
        """Set the RCON server password."""
        await self.config.password.set(password)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send("RCON password set (and message deleted for security).")

    @mcset.command(name="javaprefix")
    async def mcset_java_prefix(self, ctx, prefix: str = ""):
        """Set the prefix for Java players."""
        await self.config.java_prefix.set(prefix)
        await ctx.send(f"Java prefix set to `{prefix}`.")

    @mcset.command(name="bedrockprefix")
    async def mcset_bedrock_prefix(self, ctx, prefix: str = ""):
        """Set the prefix for Bedrock players."""
        await self.config.bedrock_prefix.set(prefix)
        await ctx.send(f"Bedrock prefix set to `{prefix}`.")

    @mcset.command(name="settings")
    async def mcset_settings(self, ctx):
        """Show current RCON settings."""
        conf = await self.config.all()
        host = conf["host"]
        port = conf["port"]
        has_password = "Yes" if conf["password"] else "No"
        j_prefix = conf.get("java_prefix", "")
        b_prefix = conf.get("bedrock_prefix", ".")
        
        embed = discord.Embed(title="Minecraft RCON Settings", color=discord.Color.blue())
        embed.add_field(name="Host", value=host, inline=True)
        embed.add_field(name="Port", value=port, inline=True)
        embed.add_field(name="Password Set", value=has_password, inline=True)
        embed.add_field(name="Java Prefix", value=f"`{j_prefix}`" if j_prefix else "None", inline=True)
        embed.add_field(name="Bedrock Prefix", value=f"`{b_prefix}`" if b_prefix else "None", inline=True)
        
        await ctx.send(embed=embed)
