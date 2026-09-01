"""The core message-scanning listener.

Pipeline for each message from an *unvetted* (pending) user:

1. Fingerprint the text and record it in the in-memory burst tracker.
2. If the same message hit multiple channels in a burst -> immediate removal.
3. Otherwise score it (rules + attachment + fuzzy known-spam + exact repeat).
4. Act on the score (log / review / delete / timeout).
5. If the message was clean, count it toward the user's "graduation" to trusted.

Trusted users (including everyone seeded at first launch) are skipped entirely,
so their messages are never scored or stored.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

import discord
from discord.ext import commands

from ..fingerprint import content_hash
from ..scoring import ScoreResult, score_message
from ..views import SpamReviewView

log = logging.getLogger(__name__)

MIN_ML_LENGTH = 5


@dataclass
class KnownSpamMatch:
    matched: bool
    similarity: float = 0.0
    vector_id: int | None = None
    template_text: str = ""


@dataclass
class InsertResult:
    added: bool
    reason: str
    matched_vector_id: int | None = None
    similarity: float = 0.0


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_target_guild(self, guild_id: int | None) -> bool:
        return guild_id == self.bot.settings.target_guild_id

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self._is_target_guild(member.guild.id):
            return
        await self.bot.db.add_pending_user(member.id, member.joined_at)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not self._is_target_guild(message.guild.id):
            return
        # Commands are handled by the built-in processor; don't spam-score them.
        if message.content.startswith(self.bot.command_prefix):
            return

        user = await self.bot.db.get_user(message.author.id)
        if user is None:
            await self.bot.db.add_pending_user(
                message.author.id, message.author.joined_at
            )
        elif user[0] == "trusted":
            return

        # Fingerprint + burst tracking (text messages only).
        chash = content_hash(message.content) if message.content.strip() else None
        repeated = False
        if chash is not None:
            self.bot.burst_tracker.record(
                message.author.id, chash, message.channel.id, message.id
            )
            if self.bot.burst_tracker.is_burst(message.author.id, chash):
                await self._handle_burst(message, chash)
                return
            repeated = self.bot.burst_tracker.is_repeat(message.author.id, chash)

        known_match = await self._known_spam_match(message)
        result = score_message(
            message.content,
            matched_known_spam=known_match.matched,
            has_attachment=bool(message.attachments),
            repeated=repeated,
        )

        if known_match.matched and known_match.vector_id is not None:
            await self.bot.db.increment_spam_vector_hit(
                known_match.vector_id,
                known_match.similarity,
                message.content,
            )
            log.info(
                "Known-spam hit | vector_id=%s | similarity=%.4f | template_preview=%s",
                known_match.vector_id,
                known_match.similarity,
                known_match.template_text[:120].replace("\n", " "),
            )

        action = await self._apply_action(message, result)

        # Graduation: only genuinely clean messages count toward becoming trusted.
        if action == "none" and result.score < self.bot.settings.review_threshold:
            new_count = await self.bot.db.increment_message_count(message.author.id)
            if new_count >= self.bot.settings.graduation_message_count:
                await self.bot.db.set_trusted(message.author.id)

        if result.score > 0:
            await self.bot.db.log_action(
                message.author.id, message.content, chash, result.score, action
            )

    async def _known_spam_match(self, message: discord.Message) -> KnownSpamMatch:
        """Fuzzy-match the message against the learned spam database."""
        content = message.content
        if self.bot.embedder is None or len(content) <= MIN_ML_LENGTH:
            return KnownSpamMatch(matched=False)
        vector = await self.bot.embedder.encode(content)
        match = self.bot.spam_index.best_match(vector)
        is_match = match.similarity > self.bot.settings.known_spam_similarity
        return KnownSpamMatch(
            matched=is_match,
            similarity=match.similarity,
            vector_id=match.vector_id,
            template_text=match.template_text,
        )

    async def _apply_action(
        self, message: discord.Message, result: ScoreResult
    ) -> str:
        settings = self.bot.settings
        score = result.score

        if score >= settings.delete_threshold:
            if settings.shadow_mode:
                log.info(
                    "[SHADOW] would delete message from %s (score=%d): %s",
                    message.author,
                    score,
                    message.content,
                )
                return "shadow_flagged"
            try:
                await message.delete()
                action = "deleted"
                if score >= settings.timeout_threshold:
                    await message.author.timeout(
                        timedelta(minutes=settings.timeout_minutes),
                        reason="Spam detection",
                    )
                    action = "deleted_timeout"
                return action
            except discord.Forbidden:
                return "failed_perms"

        if score >= settings.review_threshold:
            await self._send_for_review(message, result)
            return "flagged_for_review"

        return "none"

    async def _handle_burst(self, message: discord.Message, chash: str) -> None:
        """Same message across multiple channels: remove every copy + timeout."""
        settings = self.bot.settings
        author = message.author
        occurrences = self.bot.burst_tracker.occurrences(author.id, chash)

        if settings.shadow_mode:
            log.info(
                "[SHADOW] burst spam from %s: would remove %d copies + timeout: %s",
                author,
                len(occurrences),
                message.content,
            )
            await self.bot.db.log_action(
                author.id, message.content, chash,
                settings.timeout_threshold, "shadow_burst",
            )
            self.bot.burst_tracker.clear(author.id, chash)
            return

        deleted = 0
        for occurrence in occurrences:
            channel = self.bot.get_channel(occurrence.channel_id)
            if channel is None:
                continue
            try:
                await channel.get_partial_message(occurrence.message_id).delete()
                deleted += 1
            except (discord.Forbidden, discord.NotFound):
                pass

        try:
            await author.timeout(
                timedelta(minutes=settings.timeout_minutes), reason="Spam burst"
            )
        except discord.Forbidden:
            pass

        await self._learn_signature(message.content, chash)
        await self.bot.db.log_action(
            author.id, message.content, chash,
            settings.timeout_threshold, f"burst_removed({deleted})",
        )
        self.bot.burst_tracker.clear(author.id, chash)

    async def _learn_signature(self, text: str, chash: str) -> None:
        """Auto-add a confirmed burst message to the known-spam database."""
        result = await self.maybe_add_spam_template(text, chash=chash)
        if not result.added:
            log.info(
                "Skipped template insert (%s) vector_id=%s similarity=%.4f",
                result.reason,
                result.matched_vector_id,
                result.similarity,
            )

    async def maybe_add_spam_template(self, text: str, *, chash: str) -> InsertResult:
        """Add a learned spam template unless it is near-duplicate to existing.

        Returns an :class:`InsertResult` explaining whether insertion happened.
        """
        if self.bot.embedder is None:
            return InsertResult(added=False, reason="embedder_disabled")

        vector = await self.bot.embedder.encode(text)
        if len(self.bot.spam_index) > 0:
            best = self.bot.spam_index.best_match(vector)
            if best.similarity >= self.bot.settings.near_duplicate_similarity:
                return InsertResult(
                    added=False,
                    reason="near_duplicate",
                    matched_vector_id=best.vector_id,
                    similarity=best.similarity,
                )

        added = await self.bot.db.add_spam_vector(vector, text, chash)
        if not added:
            return InsertResult(added=False, reason="hash_duplicate")

        records = await self.bot.db.load_vector_records()
        if records:
            newest = records[-1]
            self.bot.spam_index.add(
                vector,
                vector_id=newest["id"],
                template_text=newest["text"],
            )
            return InsertResult(
                added=True,
                reason="inserted",
                matched_vector_id=newest["id"],
            )

        return InsertResult(added=True, reason="inserted")

    async def _send_for_review(
        self, message: discord.Message, result: ScoreResult
    ) -> None:
        channel = self.bot.get_channel(self.bot.settings.mod_channel_id)
        if channel is None:
            log.warning(
                "Mod channel %s not found; cannot request review.",
                self.bot.settings.mod_channel_id,
            )
            return

        embed = discord.Embed(
            title="\u26a0\ufe0f Suspicious Message Detected",
            description=f"**Score: {result.score}**\n{message.content}",
            color=discord.Color.yellow(),
        )
        embed.set_footer(text=f"Triggers: {', '.join(result.triggers)}")
        view = SpamReviewView(self.bot, message.content)
        await channel.send(embed=embed, view=view)


async def setup(bot) -> None:
    await bot.add_cog(Moderation(bot))
