# Discord ML Moderation Bot

> A context-aware Discord moderation bot that detects spam and advertisements using rules, message similarity, and lightweight machine learning.

## 1. Project Motivation

Spam and advertisement accounts on Discord servers often follow predictable behavioral and linguistic patterns:

* They are newly created or newly joined accounts
* They frequently post advertisements as their *first message*
* Messages tend to follow repetitive templates (ticket sales, electronics, crypto, etc.)

This project builds a **context-aware, machine-learning–assisted moderation bot** that detects and mitigates spam while minimizing false positives and moderator overhead.

The key challenge addressed is **data scarcity**: spam events are relatively rare, but highly structured.

---

## 2. Goals

### Core Goals

* Monitor early user activity (until a user becomes "trusted")
* Automatically detect spam and advertisements
* Take low-risk moderation actions (log, escalate to review, delete, timeout)
* Keep a human in the loop for medium-confidence cases

### Non-Goals (Current Version)

* Full conversational moderation
* Toxicity or hate-speech detection
* Automatic permanent bans without review

---

## 3. Design Philosophy


Message hashing uses normalization that strips zero-width/control characters and
normalizes casing/whitespace to make copy-paste evasion harder.

ML is used to *refine decisions*, not replace deterministic signals.

---

defaults (shadow mode on, thresholds, similarity cutoffs, model name).
Required: `DISCORD_TOKEN`, `TARGET_GUILD_ID`, `MOD_CHANNEL_ID`. Everything else
## 4. System Architecture

Template learning uses two dedup guards:
* exact-text hash dedup (`content_hash` unique in `spam_vectors`), and
* near-duplicate cosine guard (`NEAR_DUPLICATE_SIMILARITY`, default `0.98`) to
  avoid storing many almost-identical templates.

### Admin Commands

* `/status` - Show bot health/config summary, including trusted vs pending counts.
* `/db_counts` - Show runtime row counts (trusted/pending users, vectors, logs).
* `/db_spam_vectors limit:<1-25>` - List recent learned spam vectors with row id, time, and preview text.
* `/db_spam_vector vector_id:<id>` - Inspect one learned vector's metadata and first values.
* `/db_top_matched_templates limit:<1-25>` - Show which templates are most often matched by cosine similarity.
* `/reset_database confirm:RESET` - Clear users, learned vectors, logs, and seed
  flags. This intentionally requires the exact string `RESET` to reduce
  accidental use. After reset, the bot reseeds trusted users from the target
  guild on next ready/restart.

```
Discord Gateway
      |
      v
on_message listener (Moderation cog)
      |
      v
Trust check (skip trusted; new joiners graduate by activity)
      |
      v
Scoring pipeline
  |- Burst check: same message across channels (burst_tracker.py) -> immediate
  |- Rule signals + attachment (rules.py / scoring.py)
  |- Fuzzy known-spam match (spam_index.py)
  '- Exact repeat (burst_tracker.py)
      |
      v
Action (log / review / delete / timeout) + audit log
```

The embedding model runs off the event loop (in a thread) so scanning a message
never blocks the gateway.

---

## 5. Signals Used

### User Context Signals

* Trust status (`pending` / `trusted`) — trust is **activity-based**: a new
  joiner graduates to trusted after `GRADUATION_MESSAGE_COUNT` clean messages,
  after which they are no longer tracked. Account age is deliberately **not**
  used (spam accounts vary too widely, and lurkers who wait weeks before
  spamming would otherwise be auto-trusted).

### Message Signals

* URL presence
* Discord invite links
* `@everyone` / `@here` mentions
* Attachments/images (weighted higher when combined with a link or mention)
* Fuzzy similarity to the learned spam database
* **Cross-channel burst** — the same message pasted into multiple channels in a
  short window (the strongest signal; triggers immediate removal)
* Exact repetition of the same message

---

## 6. Moderation Policy

A **cross-channel burst** (the same message in multiple channels within a short
window) short-circuits scoring: every copy seen in the last minute is deleted and
the user is timed out immediately.

Otherwise, actions are driven by a message's spam **score** (configurable
thresholds):

| Score            | Action                                   |
| ---------------- | ---------------------------------------- |
| `< 4`            | Log only                                 |
| `>= 4`           | Send to mod channel for human review     |
| `>= 8`           | Delete message                           |
| `>= 12`          | Delete message **and** timeout the user  |

When `SHADOW_MODE=true` (the default), the bot **logs what it would do** instead
of deleting or timing anyone out — ideal for tuning before enforcement. There are
no automatic permanent bans.

Signal weights: `url` = 2, `attachment` = 2 (**+2** when combined with a link or
mention), `mention_everyone` = 4, `invite_link` = 4, `repeated_message` = 5,
`match_known_spam` = 10.

---

## 7. Human-in-the-loop Learning

Medium-confidence messages (and user reports via the **Report Spam** context
menu) are posted to the mod channel with **Confirm Spam / Ignore** buttons.
Confirming stores the message embedding as a new spam signature, so one labeled
example generalizes to future near-duplicates.

---

## 8. Project Structure

```
src/modbot/
  __main__.py         # entry point: python -m modbot
  config.py           # settings from .env (pydantic-settings)
  logging_config.py   # logging setup
  bot.py              # ModBot: intents, startup, loads cogs
  rules.py            # pure regex signals (unit tested)
  scoring.py          # pure scoring logic (unit tested)
  fingerprint.py      # text normalization + content hashing (unit tested)
  burst_tracker.py    # in-memory cross-channel duplicate detection (unit tested)
  database.py         # async SQLite (aiosqlite), safe numpy vector storage
  embedder.py         # sentence-transformers wrapper (runs off event loop)
  spam_index.py       # in-memory numpy matrix for fuzzy known-spam matching
  views.py            # SpamReviewView (Confirm/Ignore buttons)
  cogs/
    moderation.py     # on_message listener + actions
    learning.py       # "Report Spam" context menu (learns new signatures)
    admin.py          # /status command
tests/                # pytest unit tests for the pure logic
```

---

## 9. Setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # then fill in DISCORD_TOKEN and MOD_CHANNEL_ID
```

Run the bot:

```bash
python -m modbot
```

Run the tests / linter:

```bash
pytest
ruff check .
```

> The unit tests cover the pure logic (rules, scoring, similarity index) and do
> **not** require a Discord connection or the ML model.

---

## 10. Configuration

All settings come from environment variables (see [.env.example](.env.example)).
Required: `DISCORD_TOKEN`, `MOD_CHANNEL_ID`. Everything else has sensible
defaults (shadow mode on, thresholds, similarity cutoffs, model name).

---

## 11. Deployment (VM + Docker)

For 24/7 coverage, run the container on an always-on VM:

```bash
cp .env.example .env   # fill in your values
docker compose up -d --build
```

* `restart: unless-stopped` in [compose.yaml](compose.yaml) auto-restarts the bot
  if it crashes or the VM reboots — this is what provides continuous uptime.
* The Docker image installs **CPU-only PyTorch** and **pre-downloads the model**
  at build time, keeping the image lean (~1 GB) and startup fast/offline-safe.
* The SQLite database is stored on a mounted `./data` volume so it survives
  rebuilds.

For local development you don't need Docker — just `python -m modbot`.

---

## 12. Evaluation

Success is measured by:

* Precision on early-account spam
* Moderator review burden
* False-positive rate on new users

---

## 13. Ethical Considerations

* Conservative enforcement thresholds and a default shadow mode
* Transparent logging of every action
* Human override / review capability
* Avoidance of demographic or identity-based features

---

## 14. Tech Stack

* Python 3.10+
* [discord.py](https://discordpy.readthedocs.io/)
* [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`)
* NumPy
* SQLite (via `aiosqlite`)
* pydantic-settings

---

## 15. Roadmap

* **Done** — Logging, rule-based scoring, similarity detection, human-in-the-loop review, shadow mode
* **Next** — Weakly supervised classifier trained from the collected labels
* **Later** — Active learning from moderator feedback; richer user-context features
