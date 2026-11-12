#!/usr/bin/env bash
set -euo pipefail
# A small text helper in Python, in a repository that uses aidd under the solo profile. It turns a title into a slug, and its
# one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd src tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > src/slug.py <<'PY'
def slugify(title):
    """A lower-case slug of a title: words joined by one hyphen."""
    return "-".join(title.lower().split())
PY
cat > tests/test_slug.py <<'PY'
from src.slug import slugify


def test_words_are_joined_by_a_hyphen():
    assert slugify("Hello World") == "hello-world"
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: slugify"
