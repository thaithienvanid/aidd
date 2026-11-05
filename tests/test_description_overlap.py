"""No two skill or command descriptions read alike: an agent loads a skill by its description, so two that share most of
their telling words fire on the same prompt. TF-IDF over the descriptions, with the standard library and no model, the
way agent-skills' evals rank one (R338); R330's trigger evals spend quota, this runs free on every change."""

import collections
import math
import re
import unittest

from helpers import ROOT

from aidd.kernel import documents

# The most two descriptions may share, as the cosine of their TF-IDF vectors. Set on 2026-11-05, when the closest pair
# (the review and specify commands) scored 0.46; past it, rewrite one so each says what only it does.
MAX_OVERLAP = 0.6


def descriptions() -> dict[str, str]:
    files = [*sorted(ROOT.glob("plugins/*/skills/*/SKILL.md")), *sorted(ROOT.glob("plugins/*/commands/*.md")), ROOT / ".agents/skills/aidd/SKILL.md"]
    out = {}
    for path in files:
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        if data.get("description"):
            out[path.relative_to(ROOT).as_posix()] = str(data["description"])
    return out


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9-]+", text.lower()) if len(w) > 2]


def overlaps(texts: dict[str, str]) -> list[tuple[float, str, str]]:
    """Each pair's cosine of TF-IDF vectors, highest first. A word every description uses weighs nothing."""
    df = collections.Counter(w for t in texts.values() for w in set(_words(t)))
    n = len(texts)

    def vector(text: str) -> dict[str, float]:
        v = {w: c * math.log(n / df[w]) for w, c in collections.Counter(_words(text)).items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    vectors = {k: vector(t) for k, t in texts.items()}
    names = sorted(vectors)
    pairs = [(sum(vectors[a].get(w, 0.0) * x for w, x in vectors[b].items()), a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
    return sorted(pairs, reverse=True)


class DescriptionOverlapTests(unittest.TestCase):
    def test_no_two_descriptions_read_alike(self):
        texts = descriptions()
        self.assertGreater(len(texts), 75)  # every skill and command (78 since the lean team cut four commands), so a broken glob never passes quietly
        close = [f"{a} and {b}: {score:.2f}" for score, a, b in overlaps(texts) if score > MAX_OVERLAP]
        self.assertEqual(close, [], "rewrite one of each pair so it says what only it does")

    def test_a_copied_description_is_caught(self):
        texts = descriptions()
        name, text = next(iter(texts.items()))
        top = overlaps({**texts, "copy": text})[0]
        self.assertGreater(top[0], MAX_OVERLAP)
        self.assertEqual({top[1], top[2]}, {name, "copy"})


if __name__ == "__main__":
    unittest.main()
