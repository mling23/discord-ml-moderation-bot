"""Application settings loaded from environment variables / a local .env file.

Using pydantic-settings gives us free validation: if ``DISCORD_TOKEN`` is
missing, the bot fails fast at startup with a clear error instead of crashing
later with a confusing ``NoneType`` message.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # --- Required ---
    discord_token: str
    mod_channel_id: int

    # --- Behaviour ---
    shadow_mode: bool = True
    # A new joiner becomes "trusted" (and stops being tracked) after posting
    # this many clean messages. Trust is activity-based, not time-based, so
    # lurkers who wait weeks before spamming are still evaluated.
    graduation_message_count: int = 5

    # --- Score thresholds ---
    review_threshold: int = 4
    delete_threshold: int = 8
    timeout_threshold: int = 12
    timeout_minutes: int = 10

    # --- Similarity threshold (fuzzy match against the learned spam DB) ---
    known_spam_similarity: float = 0.85

    # --- Burst / duplicate detection (exact-fingerprint, in memory) ---
    burst_channels: int = 3
    burst_window_seconds: int = 60
    tracker_retention_seconds: int = 120
    repeat_count: int = 2

    # --- Infrastructure ---
    db_path: str = "moderation.db"
    embedding_model: str = "all-MiniLM-L6-v2"
    command_prefix: str = "!"


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the environment."""
    return Settings()
