"""What `aidd` accepts: one module per group of `aidd --help`, each registering its commands, arguments, and flags."""

from __future__ import annotations

from aidd.cli.grammar import author, autopilot, check, decide, maintain, operate, setup, understand

# In the order of `aidd --help`, which is also the order the parser holds the commands in.
GROUPS = (setup, understand, author, decide, autopilot, check, operate, maintain)
