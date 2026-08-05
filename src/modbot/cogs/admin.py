"""Administrative / introspection commands."""

import discord
from discord import app_commands
from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="Show moderation bot status.")
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction) -> None:
        settings = self.bot.settings
        embed = discord.Embed(
            title="Moderation Bot Status", color=discord.Color.blurple()
        )
        embed.add_field(name="Shadow mode", value=str(settings.shadow_mode))
        embed.add_field(name="Spam signatures", value=str(len(self.bot.spam_index)))
        embed.add_field(
            name="ML model",
            value="loaded" if self.bot.embedder is not None else "disabled",
        )
        embed.add_field(
            name="Thresholds",
            value=(
                f"review \u2265 {settings.review_threshold}, "
                f"delete \u2265 {settings.delete_threshold}, "
                f"timeout \u2265 {settings.timeout_threshold}"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(Admin(bot))
