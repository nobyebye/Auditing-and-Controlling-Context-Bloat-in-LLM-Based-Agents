"""Token counting helpers.

The thesis artifact uses a deterministic regex token proxy by default. This is
not a provider billing tokenizer, but it is stable and reproducible for
cross-condition comparisons.
"""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(TOKEN_RE.findall(text))
