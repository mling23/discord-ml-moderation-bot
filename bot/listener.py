import os
import json
from datetime import datetime, timezone
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    member = message.author
    guild = message.guild

    if not guild:
        return  # ignore DMs

    # Count messages from this user in the server
    # (temporary: in-memory only)
    if not hasattr(bot, "message_counts"):
        bot.message_counts = {}

    bot.message_counts.setdefault(member.id, 0)
    bot.message_counts[member.id] += 1

    is_early_message = bot.message_counts[member.id] <= 3
    if not is_early_message:
        return

    now = datetime.now(timezone.utc)


    log_entry = {
        "timestamp": now.isoformat(),
        "user_id": member.id,
        "username": str(member),
        "account_age_days": (now - member.created_at).days,
        "join_age_minutes": (now - member.joined_at).total_seconds() / 60
        if member.joined_at else None,
        "message_count": bot.message_counts[member.id],
        "message_length": len(message.content),
        "message_text": message.content
    }

    with open("data/logs.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    await bot.process_commands(message)

bot.run(TOKEN)
