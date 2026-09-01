"""The Discord bot object and startup wiring."""

import logging

import discord
from discord.ext import commands

from .burst_tracker import BurstTracker
from .config import Settings
from .database import DatabaseManager
from .spam_index import SpamIndex

log = logging.getLogger(__name__)

INITIAL_EXTENSIONS = (
    "modbot.cogs.moderation",
    "modbot.cogs.learning",
    "modbot.cogs.admin",
)


class ModBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=settings.command_prefix, intents=intents)

        self.settings = settings
        self.db = DatabaseManager(settings.db_path)
        self.spam_index = SpamIndex()
        self.embedder = None  # populated in setup_hook
        self.burst_tracker = BurstTracker(
            retention_seconds=settings.tracker_retention_seconds,
            burst_window_seconds=settings.burst_window_seconds,
            burst_channels=settings.burst_channels,
            repeat_count=settings.repeat_count,
        )

    async def setup_hook(self) -> None:
        await self.db.init_db()
        records = await self.db.load_vector_records()
        self.spam_index = SpamIndex(
            [r["vector"] for r in records],
            vector_ids=[r["id"] for r in records],
            template_texts=[r["text"] for r in records],
        )
        log.info("Loaded %d spam signatures from DB.", len(self.spam_index))

        # The ML model is a core feature, but we degrade gracefully so the bot
        # still runs (rules-only) if the model fails to load.
        try:
            from .embedder import Embedder

            self.embedder = Embedder(self.settings.embedding_model)
            log.info("Embedding model '%s' loaded.", self.settings.embedding_model)
        except Exception:
            log.exception("Failed to load embedding model; ML checks disabled.")
            self.embedder = None

        for extension in INITIAL_EXTENSIONS:
            await self.load_extension(extension)

        synced = await self.tree.sync()
        log.info("Synced %d application command(s).", len(synced))

    async def on_ready(self) -> None:
        target_guild = self.get_guild(self.settings.target_guild_id)
        mod_channel = self.get_channel(self.settings.mod_channel_id)
        seeded = await self.db.is_seeded()
        log.info(
            "Logged in as %s (shadow_mode=%s)",
            self.user,
            self.settings.shadow_mode,
        )
        log.info(
            "Diagnostics | target_guild=%s | mod_channel=%s | seeded=%s | "
            "burst_channels=%s | burst_window=%ss | review=%s delete=%s timeout=%s",
            (
                f"{target_guild.name}({target_guild.id})"
                if target_guild is not None
                else f"missing({self.settings.target_guild_id})"
            ),
            (
                f"#{mod_channel.name}({mod_channel.id})"
                if mod_channel is not None
                else f"missing({self.settings.mod_channel_id})"
            ),
            seeded,
            self.settings.burst_channels,
            self.settings.burst_window_seconds,
            self.settings.review_threshold,
            self.settings.delete_threshold,
            self.settings.timeout_threshold,
        )
        # One-time: mark everyone already in the server as trusted, so only new
        # joiners are ever evaluated. Guarded by a flag so reconnects don't
        # re-trust members who joined (and are being monitored) after launch.
        if not seeded:
            await self._seed_trusted_members()
            await self.db.mark_seeded()

    async def _seed_trusted_members(self) -> None:
        guild = self.get_guild(self.settings.target_guild_id)
        if guild is None:
            log.warning(
                "Target guild %s is not available; skipping seed.",
                self.settings.target_guild_id,
            )
            return
        member_ids = {member.id for member in guild.members if not member.bot}
        await self.db.trust_members(member_ids)
        log.info(
            "Seeded %d existing members as trusted in guild %s.",
            len(member_ids),
            self.settings.target_guild_id,
        )
