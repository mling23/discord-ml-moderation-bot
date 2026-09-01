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

        moderation_cog = self.bot.get_cog("Moderation")
        if moderation_cog is None:
            await interaction.response.send_message(
                "Moderation system unavailable.", ephemeral=True
            )
            return

        result = await moderation_cog.maybe_add_spam_template(
            self.text_content,
            chash=content_hash(self.text_content),
        )

        button.label = "Spam Confirmed"
        button.disabled = True
        self.ignore_spam.disabled = True
        await interaction.response.edit_message(view=self)
        if result.added:
            message = (
                f"\u2705 Learned new spam pattern. "
                f"(Total: {len(self.bot.spam_index)})"
            )
        elif result.reason == "near_duplicate":
            message = (
                f"\u2139\ufe0f Near-duplicate of existing template "
                f"#{result.matched_vector_id} (sim={result.similarity:.4f}); "
                "skipped insert."
            )
        elif result.reason == "hash_duplicate":
            message = "\u2139\ufe0f Exact duplicate template already exists; skipped insert."
        else:
            message = "\u2139\ufe0f Template insert skipped."

        await interaction.followup.send(message, ephemeral=True)

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
