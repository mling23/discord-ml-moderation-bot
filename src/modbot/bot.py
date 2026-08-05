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
        self.spam_index = SpamIndex(await self.db.load_vectors())
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
        log.info(
            "Logged in as %s (shadow_mode=%s)",
            self.user,
            self.settings.shadow_mode,
        )
        # One-time: mark everyone already in the server as trusted, so only new
        # joiners are ever evaluated. Guarded by a flag so reconnects don't
        # re-trust members who joined (and are being monitored) after launch.
        if not await self.db.is_seeded():
            await self._seed_trusted_members()
            await self.db.mark_seeded()

    async def _seed_trusted_members(self) -> None:
        member_ids = {
            member.id
            for guild in self.guilds
            for member in guild.members
            if not member.bot
        }
        await self.db.trust_members(member_ids)
        log.info("Seeded %d existing members as trusted.", len(member_ids))
