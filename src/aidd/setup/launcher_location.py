"""Where this user's launcher sits, for the watched state aidd keeps at a person's decision (guard/watched_state.py): every
repository's hooks start it, so a change to it is one the person sees at their next decision.
"""

from __future__ import annotations

from pathlib import Path

from aidd.setup import hook_wiring


def user_launcher() -> Path:
    """This user's launcher, which the hooks of every repository on the machine start (hook_wiring.USER_LAUNCHER)."""
    return hook_wiring.user_launcher_path()
