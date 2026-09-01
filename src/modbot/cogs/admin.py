"""Administrative / introspection commands."""

import discord
from discord import app_commands
from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reset_database",
        description="Reset moderation DB (users, vectors, logs). Admin only.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_database(
        self, interaction: discord.Interaction, confirm: str
    ) -> None:
        if confirm != "RESET":
            await interaction.response.send_message(
                "Reset cancelled. To proceed, run `/reset_database confirm:RESET`.",
                ephemeral=True,
            )
            return

        summary = await self.bot.db.reset_data()
        # Keep in-memory state aligned with the now-empty database.
        self.bot.spam_index = type(self.bot.spam_index)()
        self.bot.burst_tracker = type(self.bot.burst_tracker)(
            retention_seconds=self.bot.settings.tracker_retention_seconds,
            burst_window_seconds=self.bot.settings.burst_window_seconds,
            burst_channels=self.bot.settings.burst_channels,
            repeat_count=self.bot.settings.repeat_count,
        )

        embed = discord.Embed(
            title="Database Reset Complete",
            color=discord.Color.red(),
            description=(
                "All moderation runtime data has been cleared. The bot will reseed "
                "trusted users from the target guild on next ready/restart."
            ),
        )
        embed.add_field(name="Users removed", value=str(summary["users"]))
        embed.add_field(
            name="Spam vectors removed", value=str(summary["spam_vectors"])
        )
        embed.add_field(name="Log rows removed", value=str(summary["logs"]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Show moderation bot status.")
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction) -> None:
        settings = self.bot.settings
        trusted_count, pending_count = await self.bot.db.get_user_status_counts()
        seeded = await self.bot.db.is_seeded()
        target_guild = self.bot.get_guild(settings.target_guild_id)
        mod_channel = self.bot.get_channel(settings.mod_channel_id)
        embed = discord.Embed(
            title="Moderation Bot Status", color=discord.Color.blurple()
        )
        embed.add_field(name="Shadow mode", value=str(settings.shadow_mode))
        embed.add_field(name="Spam signatures", value=str(len(self.bot.spam_index)))
        embed.add_field(name="Trusted users", value=str(trusted_count))
        embed.add_field(name="Pending users", value=str(pending_count))
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
        embed.add_field(
            name="Target guild",
            value=(
                f"{target_guild.name} ({target_guild.id})"
                if target_guild is not None
                else f"missing ({settings.target_guild_id})"
            ),
            inline=False,
        )
        embed.add_field(
            name="Mod channel",
            value=(
                f"#{mod_channel.name} ({mod_channel.id})"
                if mod_channel is not None
                else f"missing ({settings.mod_channel_id})"
            ),
        )
        embed.add_field(name="Seeded", value=str(seeded))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="db_counts",
        description="Show row counts for users, vectors, and logs.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def db_counts(self, interaction: discord.Interaction) -> None:
        counts = await self.bot.db.get_runtime_counts()
        embed = discord.Embed(
            title="Database Counts", color=discord.Color.dark_teal()
        )
        embed.add_field(name="Trusted users", value=str(counts["trusted"]))
        embed.add_field(name="Pending users", value=str(counts["pending"]))
        embed.add_field(name="Spam vectors", value=str(counts["spam_vectors"]))
        embed.add_field(name="Log rows", value=str(counts["logs"]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="db_spam_vectors",
        description="Show recent learned spam vectors.",
    )
    @app_commands.describe(limit="How many rows to show (1-25).")
    @app_commands.checks.has_permissions(administrator=True)
    async def db_spam_vectors(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 25] = 5
    ) -> None:
        rows = await self.bot.db.list_spam_vector_previews(limit=limit)
        if not rows:
            await interaction.response.send_message(
                "No spam vectors learned yet.", ephemeral=True
            )
            return

        lines = []
        for row in rows:
            lines.append(
                f"`#{row['id']}` at {row['added_at']}\n"
                f"{row['text_preview']}"
            )
        embed = discord.Embed(
            title=f"Recent Spam Vectors ({len(rows)})",
            description="\n\n".join(lines),
            color=discord.Color.dark_gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="db_spam_vector",
        description="Inspect one learned spam vector by row id.",
    )
    @app_commands.describe(vector_id="Row id from /db_spam_vectors.")
    @app_commands.checks.has_permissions(administrator=True)
    async def db_spam_vector(
        self, interaction: discord.Interaction, vector_id: int
    ) -> None:
        row = await self.bot.db.get_spam_vector_details(vector_id)
        if row is None:
            await interaction.response.send_message(
                f"No spam vector with id {vector_id}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Spam Vector #{row['id']}", color=discord.Color.orange()
        )
        embed.add_field(name="Added at", value=row["added_at"], inline=False)
        embed.add_field(name="Dimension", value=str(row["dimension"]))
        embed.add_field(name="Norm", value=f"{row['norm']:.4f}")
        embed.add_field(
            name="Values (first 8)",
            value=row["values_preview"] or "(no values)",
            inline=False,
        )
        embed.add_field(
            name="Original text",
            value=(row["text"][:1000] if row["text"] else "(empty)"),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="db_top_matched_templates",
        description="Show templates most often matched by cosine similarity.",
    )
    @app_commands.describe(limit="How many templates to show (1-25).")
    @app_commands.checks.has_permissions(administrator=True)
    async def db_top_matched_templates(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 25] = 10
    ) -> None:
        rows = await self.bot.db.top_spam_vector_hits(limit=limit)
        if not rows:
            await interaction.response.send_message(
                "No cosine-match hits recorded yet.", ephemeral=True
            )
            return

        lines = []
        for row in rows:
            lines.append(
                f"`#{row['vector_id']}` hits `{row['hit_count']}` "
                f"last_sim `{row['last_similarity']:.4f}` at {row['last_hit_at']}\n"
                f"{row['template_text']}"
            )
        embed = discord.Embed(
            title=f"Top Matched Templates ({len(rows)})",
            description="\n\n".join(lines),
            color=discord.Color.purple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(Admin(bot))
