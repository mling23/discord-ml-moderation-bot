"""Deterministic, regex-based spam signals.

These are pure functions with no Discord or ML dependencies, which makes them
trivial to unit test.
"""

import re

URL_REGEX = re.compile(r"https?://|www\.", re.IGNORECASE)
INVITE_REGEX = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.IGNORECASE)
EVERYONE_REGEX = re.compile(r"@everyone|@here", re.IGNORECASE)

# How much each trigger contributes to a message's spam score.
# Note: a cross-channel burst is handled separately as an immediate action
# (see modbot.burst_tracker), not as an additive weight here.
WEIGHTS: dict[str, int] = {
    "url": 2,
    "invite_link": 4,
    "mention_everyone": 4,
    "attachment": 2,
    "attachment_combo": 2,
    "match_known_spam": 10,
    "repeated_message": 5,
}


def rule_signals(content: str) -> list[str]:
    """Return the list of rule-based triggers found in ``content``."""
    triggers: list[str] = []
    if URL_REGEX.search(content):
        triggers.append("url")
    if INVITE_REGEX.search(content):
        triggers.append("invite_link")
    if EVERYONE_REGEX.search(content):
        triggers.append("mention_everyone")
    return triggers
