"""How many tokens a domain pack, a practice skill, and a reference may hold, and how aidd estimates the tokens of a
text. Rendering a pack reads them to place its open choices; the pack budget checks every pack against them.
"""

from __future__ import annotations

import math

# 2,200 since 1.0.0 (from 2,000): a business pack carries its Terms and its Invariants and missed cases, the words and
# rules the domain expert checks a plan against, and payments covers lending and crypto-assets too.
PACK_TOKENS = 2200
# A pack's open choices are kept in it only while it stays within this: they are read on demand, so the higher cap
# above never pulls them back into the text an agent loads.
CHOICES_INLINE_TOKENS = 2000
# 1,600 since 1.0.0: a practice skill that a new project starts from (modular-monolith) holds the walking skeleton too.
PRACTICE_TOKENS = 1600
REFERENCE_TOKENS = 1500


def estimate_tokens(text: str) -> int:
    """Estimated tokens: four characters a token, rounded up."""
    return math.ceil(len(text) / 4)
