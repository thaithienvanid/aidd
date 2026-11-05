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
# 1,700 since 1.0.0 (from 1,600, itself raised so modular-monolith holds the walking skeleton): prototyping holds the
# design tools and the work sized to the ask, and the owner keeps facts over trims that cut them.
PRACTICE_TOKENS = 1700
# 1,600 since 1.0.0 (from 1,500): the screenshot loop holds its sideways-scroll check beside the names it explains.
REFERENCE_TOKENS = 1600
# A practice skill's open choices are kept in it only while it stays within this, the cap before 1,700: the higher cap
# never pulls them back into the text an agent loads.
PRACTICE_CHOICES_INLINE_TOKENS = 1600


def estimate_tokens(text: str) -> int:
    """Estimated tokens: four characters a token, rounded up."""
    return math.ceil(len(text) / 4)
