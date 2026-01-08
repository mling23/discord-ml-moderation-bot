import os
import json
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv

import logging
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # raw JSON, no prefixes
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("moderation-bot")
# Regex helpers
URL_REGEX = re.compile(r"https?://|www\.", re.IGNORECASE)
INVITE_REGEX = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.IGNORECASE)

def count_urls(text: str) -> int:
    return len(URL_REGEX.findall(text))

def has_invite(text: str) -> bool:
    return bool(INVITE_REGEX.search(text))

# Similarity Helpers
def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def jaccard_similarity(a: str, b: str) -> float:
    A, B = set(a.split()), set(b.split())
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

# Setup
load_dotenv()
SHADOW_MODE = os.getenv("SHADOW_MODE", "true").lower() == "true"

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.message_counts = {}  # in-memory, per-process
bot.recent_messages = {}

# Events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    
    if message.author.bot or message.guild is None:
        return

    member = message.author
    # if member.guild_permissions.manage_messages:
    #     return
    now = datetime.now(timezone.utc)

    # Message count tracking
    bot.message_counts.setdefault(member.id, 0)
    bot.message_counts[member.id] += 1

    message_count = bot.message_counts[member.id]
    
    # Normalize message
    normalized_text = normalize(message.content)
    if not normalized_text:
        return

    # Init recent message buffer
    bot.recent_messages.setdefault(member.id, [])
    history = bot.recent_messages[member.id]

    # Keep only last 5 minutes
    history = [
        m for m in history
        if (now - m["timestamp"]).total_seconds() < 300
    ]
    
    # Detect multi-channel repeats
    repeated_across_channels = False
    similarity_score = 0.0

    matched_messages = []

    for prev in history:
        if prev["channel_id"] != message.channel.id:
            sim = jaccard_similarity(prev["text"], normalized_text)
            if sim >= 0.85:
                repeated_across_channels = True
                similarity_score = sim
                matched_messages.append(prev)

    # Feature extraction
    num_urls = count_urls(message.content)
    is_first = message_count == 1
    is_new_join = (
        member.joined_at
        and (now - member.joined_at).total_seconds() < 600
    )

    # Spam scoring
    spam_score = 0
    triggers = []

    if is_first:
        spam_score += 2
        triggers.append("first_message")

    if num_urls > 0:
        spam_score += 3
        triggers.append("url")

    if has_invite(message.content):
        spam_score += 3
        triggers.append("invite")

    if repeated_across_channels:
        spam_score += 5
        triggers.append("multi_channel_repeat")


    # Take action
    action = "logged_only"

    action = "logged_only"

    ENFORCEMENT_THRESHOLD = 8  # higher threshold for safety

    if spam_score >= ENFORCEMENT_THRESHOLD:
        action = "spam_detected_shadow"

        if not SHADOW_MODE:
            await message.delete()
            action = "deleted_spam"

            # Retroactively delete previous matching messages
            for prev in matched_messages:
                try:
                    channel = message.guild.get_channel(prev["channel_id"])
                    if not channel:
                        continue

                    old_msg = await channel.fetch_message(prev["message_id"])
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

    # Log event
    log_entry = {
        "timestamp": now.isoformat(),
        "user_id": member.id,
        "username": str(member),
        "account_age_days": (now - member.created_at).days,
        "join_age_minutes": (
            (now - member.joined_at).total_seconds() / 60
            if member.joined_at else None
        ),
        "message_count": message_count,
        "message_length": len(message.content),
        "num_urls": num_urls,
        "spam_score": spam_score,
        "triggers": triggers,
        "similarity_score": similarity_score,
        "channel_id": message.channel.id,
        "action": action,
        "message_text": message.content,
        "log_shadow_mode": SHADOW_MODE,
    }
    
    log_entry["deleted_message_ids"] = [
    prev["message_id"] for prev in matched_messages
]

    # with open("data/logs.jsonl", "a") as f:
    #     f.write(json.dumps(log_entry) + "\n")
    logger.info(json.dumps(log_entry))

  
    # Update history AFTER checks
    history.append({
        "message_id": message.id,
        "channel_id": message.channel.id,
        "timestamp": now,
        "text": normalized_text
    })
    bot.recent_messages[member.id] = history
    #print(history)

    await bot.process_commands(message)

# Run
bot.run(TOKEN)