"""Moderator tools for reporting spam and teaching the bot new patterns.

New spam signatures are learned through the "Report Spam" context menu and the
"Confirm Spam" button on the review card (see :mod:`modbot.views`).
"""

import logging

import discord
from discord.ext import commands

from ..views import SpamReviewView

log = logging.getLogger(__name__)


class Learning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def _is_pending(bot, user_id: int) -> bool:
    """Return True if a user is still subject to spam checks (not trusted)."""
    user = await bot.db.get_user(user_id)
    if user is None:
        return True
    status, _count = user
    return status != "trusted"


async def setup(bot) -> None:
    await bot.add_cog(Learning(bot))

    @bot.tree.context_menu(name="Report Spam")
    async def report_spam(
        interaction: discord.Interaction, message: discord.Message
    ) -> None:
        if interaction.guild_id != bot.settings.target_guild_id:
            await interaction.response.send_message(
                "This moderation workflow is only enabled in the configured server.",
                ephemeral=True,
            )
            return
        if not await _is_pending(bot, message.author.id):
            await interaction.response.send_message(
                "\u274c This user is a trusted community member and cannot be "
                "reported for spam.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "\u2705 Thanks for the report! Moderators have been alerted.",
            ephemeral=True,
        )

        channel = bot.get_channel(bot.settings.mod_channel_id)
        if channel is None:
            log.warning(
                "Mod channel %s not found; report not delivered.",
                bot.settings.mod_channel_id,
            )
            return

        embed = discord.Embed(
            title="\U0001f6a8 User Report: Suspected Spam",
            description=message.content,
            color=discord.Color.orange(),
        )
        embed.set_author(
            name=f"Reported by {interaction.user}",
            icon_url=interaction.user.display_avatar,
        )
        embed.add_field(name="Author", value=f"{message.author}")
        view = SpamReviewView(bot, message.content)
        await channel.send(embed=embed, view=view)
