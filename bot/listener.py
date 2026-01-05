import os
import json
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv


# Regex helpers
URL_REGEX = re.compile(r"https?://|www\.", re.IGNORECASE)
INVITE_REGEX = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.IGNORECASE)

def count_urls(text: str) -> int:
    return len(URL_REGEX.findall(text))

def has_invite(text: str) -> bool:
    return bool(INVITE_REGEX.search(text))

# Setup
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.message_counts = {}  # in-memory, per-process


# Events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    member = message.author
    now = datetime.now(timezone.utc)

    # Message count tracking
    bot.message_counts.setdefault(member.id, 0)
    bot.message_counts[member.id] += 1

    message_count = bot.message_counts[member.id]

    # Only monitor first 3 messages
    if message_count > 3:
        return


    # Feature extraction
    join_age_minutes = (
        (now - member.joined_at).total_seconds() / 60
        if member.joined_at
        else None
    )

    num_urls = count_urls(message.content)

    log_entry = {
        "timestamp": now.isoformat(),
        "user_id": member.id,
        "username": str(member),
        "account_age_days": (now - member.created_at).days,
        "join_age_minutes": join_age_minutes,
        "message_count": message_count,
        "message_length": len(message.content),
        "num_urls": num_urls,
        "message_text": message.content,
        "action": "logged_only",
    }

   
    # Spam rule
    is_first = message_count == 1
    is_new_join = join_age_minutes is not None and join_age_minutes < 10
    has_link = num_urls > 0 or has_invite(message.content)

    if is_first and is_new_join and has_link:
        try:
            await message.delete()
            log_entry["action"] = "deleted_first_message_link_new_join"
        except discord.Forbidden:
            log_entry["action"] = "delete_failed_missing_permissions"


    # Logging
    with open("data/logs.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    await bot.process_commands(message)


# Run
bot.run(TOKEN)