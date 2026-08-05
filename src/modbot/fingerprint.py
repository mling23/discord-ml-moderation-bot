"""Text normalization and content hashing.

A single, stable fingerprint of a message is used in two places:

* the in-memory burst tracker (exact-duplicate detection across channels), and
* the database (deduping identical pasted messages).

Keeping this in one module guarantees both use exactly the same definition of
"the same message".
"""

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lowercase, trim, and collapse internal whitespace runs to one space."""
    return _WHITESPACE.sub(" ", text.strip().lower())


def content_hash(text: str) -> str:
    """Return a stable hex digest of the normalized text.

    This is a fingerprint for duplicate detection, not a security hash.
    """
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()
