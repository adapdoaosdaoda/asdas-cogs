"""Option management commands for Trade Commission cog."""
import discord
import logging
from typing import Optional
from redbot.core import commands

log = logging.getLogger("red.tradecommission")


class CommandsOptionsMixin:
    """Mixin containing option management commands for Trade Commission."""

    async def tc_setoption(
        self,
        ctx: commands.Context,
        emoji: str,
        title: str,
        *,
        description: str
    ):
        """
        Configure an option's information (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        If an option with the same title exists, it will be updated.
        Otherwise, a new option will be added.

        **Arguments:**
        - `emoji`: Emoji to use for reactions (unicode emoji or custom server emoji)
        - `title`: Title for this option (used as identifier)
        - `description`: Description/information to show when this option is selected

        **Examples:**
        - `[p]tc setoption 🔥 "Silk Road" This week's trade route is the Silk Road with 20% bonus on silk items.`
        - `[p]tc setoption :custom_emoji: "Tea Trade" Premium tea trading available.`

        **Note:** To use custom server emojis, just type them normally (e.g., :tradeicon:) and Discord will auto-convert them.
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        # Validate emoji by testing if it can be added as a reaction
        # This works for both unicode emojis and custom Discord emojis
        try:
            await ctx.message.add_reaction(emoji)
            await ctx.message.clear_reaction(emoji)
        except discord.HTTPException:
            await ctx.send(
                "❌ Invalid emoji! Make sure the emoji is:\n"
                "• A valid unicode emoji (🔥, 💎, ⚔️)\n"
                "• A custom emoji from this server or a server the bot is in\n"
                "• Properly formatted"
            )
            return

        # Check if option with this title already exists
        async with self.config.trade_options() as trade_options:
            existing_idx = None
            for idx, option in enumerate(trade_options):
                if option["title"].lower() == title.lower():
                    existing_idx = idx
                    break

            new_option = {
                "emoji": emoji,
                "title": title,
                "description": description
            }

            if existing_idx is not None:
                # Update existing option
                trade_options[existing_idx] = new_option
                await ctx.send(
                    f"✅ Option **{title}** updated!\n"
                    f"**Emoji:** {emoji}\n"
                    f"**Description:** {description[:100]}{'...' if len(description) > 100 else ''}"
                )
            else:
                # Add new option
                trade_options.append(new_option)
                await ctx.send(
                    f"✅ New option added: **{title}**\n"
                    f"**Emoji:** {emoji}\n"
                    f"**Description:** {description[:100]}{'...' if len(description) > 100 else ''}\n"
                    f"**Total options:** {len(trade_options)}"
                )

    async def tc_removeoption(self, ctx: commands.Context, *, title: str):
        """
        Remove an option by its title (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Arguments:**
        - `title`: Title of the option to remove

        **Example:**
        - `[p]tc removeoption Silk Road`
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        async with self.config.trade_options() as trade_options:
            # Find the option with matching title
            found_idx = None
            for idx, option in enumerate(trade_options):
                if option["title"].lower() == title.lower():
                    found_idx = idx
                    break

            if found_idx is None:
                await ctx.send(f"❌ No option found with title: **{title}**")
                return

            # Remove the option
            removed = trade_options.pop(found_idx)
            await ctx.send(
                f"✅ Option removed: **{removed['title']}**\n"
                f"**Emoji:** {removed['emoji']}\n"
                f"**Remaining options:** {len(trade_options)}"
            )

    async def tc_listoptions(self, ctx: commands.Context):
        """
        List all configured trade options (Global Setting).

        Shows all available options that can be used across all servers.
        Can be used in DMs by the bot owner.
        """
        trade_options = await self.config.trade_options()

        if not trade_options:
            await ctx.send(
                "❌ No options configured yet!\n\n"
                "Use `[p]tc setoption <emoji> <title> <description>` to add options."
            )
            return

        embed = discord.Embed(
            title="📋 Configured Trade Commission Options",
            description=f"**Total Options:** {len(trade_options)}\n\n"
                       "These options are available across all servers using this cog.",
            color=discord.Color.blue()
        )

        for idx, option in enumerate(trade_options, 1):
            embed.add_field(
                name=f"{idx}. {option['emoji']} {option['title']}",
                value=option['description'][:200] + ('...' if len(option['description']) > 200 else ''),
                inline=False
            )

        await ctx.send(embed=embed)

    async def tc_setimage(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Set the image to display in Trade Commission messages (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Usage:**
        1. Attach an image to your message (no URL needed)
        2. Provide a direct image URL as an argument
        3. Use "none" to remove the current image

        **Examples:**
        - `[p]tc setimage` (with image attached)
        - `[p]tc setimage https://example.com/trade-commission.png`
        - `[p]tc setimage none` (to remove)

        **Note:** The image will be displayed on both the initial post and when options are added.
        """
        # Check if user wants to remove the image
        if image_url and image_url.lower() == "none":
            await self.config.image_url.set(None)
            await ctx.send("✅ Trade Commission image removed.")
            return

        # Check for image attachment first
        final_url = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]

            # Validate that it's an image
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                await ctx.send(
                    "❌ The attached file is not an image!\n"
                    "Please attach a valid image file (PNG, JPG, GIF, or WebP)."
                )
                return

            # Use the attachment URL
            final_url = attachment.url

        # If no attachment, check for URL parameter
        elif image_url:
            # Basic URL validation
            valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

            if not image_url.startswith(('http://', 'https://')):
                await ctx.send("❌ Image URL must start with http:// or https://")
                return

            # Check if URL ends with valid extension (less strict - query params are ok)
            url_lower = image_url.lower().split('?')[0]  # Remove query params for extension check
            if not any(url_lower.endswith(ext) for ext in valid_extensions):
                await ctx.send(
                    f"❌ Invalid image URL! URL should point to an image file.\n"
                    f"Supported formats: {', '.join(valid_extensions)}\n\n"
                    f"**Tip:** You can also attach an image directly to this command instead of using a URL."
                )
                return

            final_url = image_url

        # If neither attachment nor URL provided
        else:
            await ctx.send(
                "❌ No image provided!\n\n"
                "**Usage:**\n"
                "• Attach an image file to your message, or\n"
                "• Provide an image URL as an argument\n\n"
                "**Examples:**\n"
                "• `[p]tc setimage` (with image attached)\n"
                "• `[p]tc setimage https://example.com/image.png`\n"
                "• `[p]tc setimage none` (to remove current image)"
            )
            return

        # Test the URL by trying to set it in an embed
        test_embed = discord.Embed(title="Testing image...")
        try:
            test_embed.set_image(url=final_url)
        except Exception as e:
            await ctx.send(f"❌ Invalid image URL: {e}")
            return

        # Save the image URL
        await self.config.image_url.set(final_url)

        # Show preview
        embed = discord.Embed(
            title="✅ Trade Commission Image Set",
            description=(
                "This image will be displayed in Trade Commission messages.\n\n"
                "**Image will appear:**\n"
                "• In the initial weekly post\n"
                "• When options are added via addinfo"
            ),
            color=discord.Color.green()
        )
        embed.set_image(url=final_url)

        if ctx.message.attachments:
            embed.set_footer(text="⚠️ Warning: Discord attachment URLs may expire. Consider using a permanent image host.")

        await ctx.send(embed=embed)

    async def tc_setgrouptitle(self, ctx: commands.Context, emoji: str, *, title: str):
        """
        Set a custom title for an emoji-grouped option category (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        When options are grouped by their final emoji in the addinfo message,
        this allows you to customize the group name instead of just showing the emoji.

        **Arguments:**
        - `emoji`: The emoji that groups options (e.g., 🔥)
        - `title`: Custom title for this emoji group

        **Examples:**
        - `[p]tc setgrouptitle 🔥 Fire Routes`
        - `[p]tc setgrouptitle 🌊 Water Routes`
        - `[p]tc setgrouptitle ⚔️ Combat Missions`
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        # Validate emoji
        try:
            await ctx.message.add_reaction(emoji)
            await ctx.message.clear_reaction(emoji)
        except discord.HTTPException:
            await ctx.send("❌ Invalid emoji! Make sure it's a valid unicode emoji or custom Discord emoji.")
            return

        async with self.config.emoji_titles() as emoji_titles:
            emoji_titles[emoji] = title

        await ctx.send(f"✅ Set emoji group title: {emoji} → **{title}**")

    async def tc_removegrouptitle(self, ctx: commands.Context, emoji: str):
        """
        Remove a custom title for an emoji-grouped option category (Global Setting).

        This is a global setting that affects all servers using this cog.
        Can be used in DMs by the bot owner.

        **Arguments:**
        - `emoji`: The emoji to remove the custom title from

        **Example:**
        - `[p]tc removegrouptitle 🔥`
        """
        # Check permissions - bot owner only for global config
        if not await ctx.bot.is_owner(ctx.author):
            # If in guild, check for admin permissions
            if ctx.guild:
                if not (ctx.author.guild_permissions.manage_guild or await ctx.bot.is_admin(ctx.author)):
                    await ctx.send("❌ You need Manage Server permission or Admin role to use this command!")
                    return
            else:
                await ctx.send("❌ Only the bot owner can use this command in DMs!")
                return

        async with self.config.emoji_titles() as emoji_titles:
            if emoji not in emoji_titles:
                await ctx.send(f"❌ No custom title set for {emoji}")
                return

            removed_title = emoji_titles.pop(emoji)

        await ctx.send(f"✅ Removed custom title for {emoji} (was: **{removed_title}**)")

    async def tc_listgrouptitles(self, ctx: commands.Context):
        """
        List all custom emoji group titles (Global Setting).

        Shows all configured custom titles for emoji-grouped option categories.
        Can be used in DMs by the bot owner.
        """
        emoji_titles = await self.config.emoji_titles()

        if not emoji_titles:
            await ctx.send(
                "❌ No custom emoji group titles configured.\n\n"
                "Use `[p]tc setgrouptitle <emoji> <title>` to add custom titles."
            )
            return

        embed = discord.Embed(
            title="📋 Emoji Group Titles",
            description=f"**Total:** {len(emoji_titles)}\n\nCustom titles for emoji-grouped options:",
            color=discord.Color.blue()
        )

        for emoji, title in emoji_titles.items():
            embed.add_field(
                name=f"{emoji}",
                value=f"**{title}**",
                inline=True
            )

        await ctx.send(embed=embed)
