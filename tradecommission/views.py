"""Interactive views for Trade Commission cog."""
import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tradecommission import TradeCommission


class TradeCommissionView(discord.ui.View):
    """View for selecting Trade Commission options."""

    def __init__(self, cog: "TradeCommission", guild: discord.Guild, target_message: discord.Message):
        super().__init__(timeout=3600 * 12)  # 12 hour timeout
        self.cog = cog
        self.guild = guild
        self.target_message = target_message
        self._message: discord.Message = None

    async def on_timeout(self):
        """Disable all buttons when view times out."""
        for item in self.children:
            item.disabled = True

        if self._message:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to interact."""
        # Only guild admins can modify
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need 'Manage Server' permission to modify Trade Commission information!",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Option 1", emoji="1️⃣", style=discord.ButtonStyle.primary, custom_id="tc_option1")
    async def option1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle option 1."""
        await self._toggle_option(interaction, "option1")

    @discord.ui.button(label="Option 2", emoji="2️⃣", style=discord.ButtonStyle.primary, custom_id="tc_option2")
    async def option2_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle option 2."""
        await self._toggle_option(interaction, "option2")

    @discord.ui.button(label="Option 3", emoji="3️⃣", style=discord.ButtonStyle.primary, custom_id="tc_option3")
    async def option3_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle option 3."""
        await self._toggle_option(interaction, "option3")

    @discord.ui.button(label="Close", emoji="✖️", style=discord.ButtonStyle.danger, custom_id="tc_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the view."""
        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.set_footer(text="This panel has been closed.")

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def _toggle_option(self, interaction: discord.Interaction, option_key: str):
        """Toggle an option on or off."""
        config = self.cog.config.guild(self.guild)

        async with config.active_options() as active_options:
            if option_key in active_options:
                # Remove option
                active_options.remove(option_key)
                action = "removed from"
            else:
                # Check if we've reached the limit
                if len(active_options) >= 3:
                    await interaction.response.send_message(
                        "❌ Maximum of 3 options can be selected! Please deselect an option first.",
                        ephemeral=True
                    )
                    return

                # Add option
                active_options.append(option_key)
                action = "added to"

        # Update the Trade Commission message
        await self.cog.update_commission_message(self.guild)

        # Get updated info for response
        trade_info = await config.trade_info()
        active_options = await config.active_options()
        option_info = trade_info[option_key]

        # Update the control panel embed
        embed = interaction.message.embeds[0]

        # Update options display
        options_text = []
        for key, info in trade_info.items():
            status = "✅" if key in active_options else "⬜"
            options_text.append(f"{status} {info['emoji']} **{info['title']}**")

        embed.set_field_at(
            0,
            name="Available Options",
            value="\n".join(options_text),
            inline=False
        )
        embed.set_footer(text=f"Selected: {len(active_options)}/3")

        # Update button styles
        await self._update_button_styles(active_options)

        await interaction.response.edit_message(embed=embed, view=self)

        # Send confirmation
        await interaction.followup.send(
            f"✅ **{option_info['title']}** has been {action} the Trade Commission message!",
            ephemeral=True
        )

    async def _update_button_styles(self, active_options: list):
        """Update button styles based on active options."""
        button_map = {
            "tc_option1": ("option1", self.option1_button),
            "tc_option2": ("option2", self.option2_button),
            "tc_option3": ("option3", self.option3_button),
        }

        for custom_id, (option_key, button) in button_map.items():
            if option_key in active_options:
                button.style = discord.ButtonStyle.success
            else:
                button.style = discord.ButtonStyle.primary
