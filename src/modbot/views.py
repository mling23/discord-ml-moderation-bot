"""Shared UI components used by more than one cog."""

import logging

import discord

from .fingerprint import content_hash

log = logging.getLogger(__name__)


class SpamReviewView(discord.ui.View):
    """A moderator-facing card with "Confirm Spam" / "Ignore" buttons.

    Confirming teaches the bot a new spam signature (adds the message vector to
    both the database and the in-memory index).
    """

    def __init__(self, bot, text_content: str):
        super().__init__(timeout=None)  # persist until acted upon
        self.bot = bot
        self.text_content = text_content

    @discord.ui.button(
        label="Confirm Spam (Add to DB)",
        style=discord.ButtonStyle.danger,
        emoji="\u26a0\ufe0f",
    )
    async def confirm_spam(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.bot.embedder is None:
            await interaction.response.send_message(
                "ML model not loaded!", ephemeral=True
            )
            return

        vector = await self.bot.embedder.encode(self.text_content)
        added = await self.bot.db.add_spam_vector(
            vector, self.text_content, content_hash(self.text_content)
        )
        if added:
            self.bot.spam_index.add(vector)

        button.label = "Spam Confirmed"
        button.disabled = True
        self.ignore_spam.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"\u2705 Learned new spam pattern. (Total: {len(self.bot.spam_index)})",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Ignore / False Positive", style=discord.ButtonStyle.secondary
    )
    async def ignore_spam(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        button.label = "Ignored"
        button.disabled = True
        self.confirm_spam.disabled = True
        await interaction.response.edit_message(view=self)
