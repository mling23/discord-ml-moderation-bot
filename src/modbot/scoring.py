"""Combine rule signals and (optional) contextual signals into a score.

``score_message`` is intentionally pure: the ML similarity result, attachment
presence, and repeat status are passed in as plain booleans. This lets us unit
test the full scoring logic without loading a model or connecting to Discord.
"""

from dataclasses import dataclass, field

from .rules import WEIGHTS, rule_signals


@dataclass
class ScoreResult:
    score: int
    triggers: list[str] = field(default_factory=list)


def score_message(
    content: str,
    *,
    matched_known_spam: bool = False,
    has_attachment: bool = False,
    repeated: bool = False,
) -> ScoreResult:
    triggers = rule_signals(content)
    if has_attachment:
        triggers.append("attachment")
        # An image on its own is weak, but an image *with* a link or mass mention
        # is the classic "buy my product" advert.
        if any(t in triggers for t in ("url", "invite_link", "mention_everyone")):
            triggers.append("attachment_combo")
    if matched_known_spam:
        triggers.append("match_known_spam")
    if repeated:
        triggers.append("repeated_message")
    score = sum(WEIGHTS[trigger] for trigger in triggers)
    return ScoreResult(score=score, triggers=triggers)
