"""How many tokens a domain pack, a practice skill, and a reference may hold, and how aidd estimates the tokens of a
text. Rendering a pack reads them to place its open choices; the pack budget checks every pack against them.

Each limit is for a class of file that loads on a signal, never for one file. No harness limits such a file: the Agent Skills
page says there is "no practical limit on bundled content" (platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).
So a limit here is a readability bound that tracks what one load costs, and a file near it is split by topic, never reworded.
"""

from __future__ import annotations

import math

# A pack loads when the code a change touches matches it, and a change loads one or two. 3,000 tokens is 1.5% of a 200,000-token
# window. A business pack carries its Terms, its Invariants and missed cases, its standards, and its tests, which
# `schemas/packs.json` generates, and payments covers lending and crypto-assets too. The largest pack is at 73% of the limit.
PACK_TOKENS = 3000
# A pack's open choices are kept in it only while it stays within this: they are read on demand, so the higher cap
# above never pulls them back into the text an agent loads.
CHOICES_INLINE_TOKENS = 2000
# A practice skill loads on a signal, and a role may load four: 10,000 tokens, about 5% of a 200K window.
# The cap was 1,700, the size of the largest one that day, so a true sentence had no room and trims lost facts.
PRACTICE_TOKENS = 2500
# A skill's reference loads when the skill points at it, and a change loads one or two: 3,000 tokens is 1.5% of a 200,000-token
# window, the share of the window one pack takes (PACK_TOKENS). A reference holds the checks of one topic, so a topic with several
# checks, each stated so that a person or a test can observe it, needs room for them.
REFERENCE_TOKENS = 3000
# A practice skill's open choices are kept in it only while it stays within this: the higher cap
# never pulls them back into the text an agent loads.
PRACTICE_CHOICES_INLINE_TOKENS = 1600


def estimate_tokens(text: str) -> int:
    """Estimated tokens: four characters a token, rounded up."""
    return math.ceil(len(text) / 4)
