"""Text normalization and content hashing.

A single, stable fingerprint of a message is used in two places:

* the in-memory burst tracker (exact-duplicate detection across channels), and
* the database (deduping identical pasted messages).

Keeping this in one module guarantees both use exactly the same definition of
"the same message".
"""

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")

# Invisible codepoints used to evade naive exact-string checks.
_ZERO_WIDTH = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\ufeff",  # byte-order mark
}


def _strip_invisible_and_controls(text: str) -> str:
    out = []
    for ch in text:
        if ch in _ZERO_WIDTH:
            continue
        category = unicodedata.category(ch)
        # Remove control/format chars but keep common whitespace characters.
        if category.startswith("C") and ch not in "\n\t\r":
            continue
        out.append(ch)
    return "".join(out)


def normalize_text(text: str) -> str:
    """Normalize text for robust duplicate detection.

    Steps:
    1. Unicode NFKC normalize.
    2. Remove zero-width/control formatting chars often used for evasion.
    3. Lowercase, trim, and collapse internal whitespace runs.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _strip_invisible_and_controls(text)
    return _WHITESPACE.sub(" ", text.strip().lower())


def content_hash(text: str) -> str:
    """Return a stable hex digest of the normalized text.

    This is a fingerprint for duplicate detection, not a security hash.
    """
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()
