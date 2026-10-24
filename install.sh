#!/bin/sh
# aidd installer: installs the aidd CLI (Python 3.11+, no dependencies) from PyPI as a prebuilt wheel,
# with uv, pipx, or a private venv, then prints the next step. uv brings its own Python 3.11+ when the
# system's is older (stock macOS ships 3.9); pipx and the venv need a Python 3.11+ on PATH.
# Usage, until aidd is published on PyPI (PUBLISHED below): a commit to build from, or the wheel you checked:
#   curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh | AIDD_REF=<commit sha> sh
#   curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh | AIDD_SHA256=<wheel sha256> sh
# Once it is published: curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh | sh
#
# Environment:
#   AIDD_REF     the release to install (default below). A vX.Y.Z tag installs aidd==X.Y.Z from PyPI.
#                A full commit SHA installs from source at that commit; that builds on your machine and
#                is for testing unreleased code only. Anything else is refused.
#   AIDD_SHA256  the sha256 of the release wheel (from SHA256SUMS on the GitHub Release). When set, the
#                wheel is downloaded, checked against it, and only then installed. Until aidd is published
#                on PyPI, a tag install needs it: the name alone proves nothing there yet.
#
# Verify the release itself with: gh attestation verify <wheel> --repo thaithienvanid/aidd
#
# No installer at all: each GitHub Release also carries aidd.pyz, the CLI as one zipapp that any Python 3.11+
# runs as `python3 aidd.pyz`. This script does not install it; download it with SHA256SUMS, check it, and verify
# it with `gh attestation verify aidd.pyz --repo thaithienvanid/aidd` (docs/INSTALL.md, "One file: aidd.pyz").
#
# Everything runs inside main, called on the last line, so a truncated download runs nothing.
set -eu

# Empty until the first release is on PyPI; a PR after the first release sets it to yes (RELEASING.md, step 5). While it is empty, a
# release tag installs only with AIDD_SHA256, because anyone could have published a package under the name.
PUBLISHED=""

say() { printf '%s\n' "$*"; }
die() { printf 'aidd install: %s\n' "$*" >&2; exit 1; }

# The path of a Python 3.11 or later on PATH; fails when there is none.
find_python() {
  for c in python3.15 python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

no_python() {
  found="$(python3 --version 2>&1 || true)"
  die "$1 needs Python 3.11 or later (found: ${found:-no python3}). Install uv (https://docs.astral.sh/uv/), which brings its own Python, or Python 3.11+."
}

# A Python 3.11+ for checking the wheel: the system's, or one uv finds or installs.
checker_python() {
  if find_python; then return 0; fi
  command -v uv >/dev/null 2>&1 || return 1
  uv python find '>=3.11' 2>/dev/null && return 0
  uv python install >&2 || return 1
  uv python find '>=3.11'
}

need_pip() {
  "$1" -m pip --version >/dev/null 2>&1 \
    || die "pip is not available for $1: install it (Debian and Ubuntu: apt install python3-pip), or install uv"
}

# The wheel for $1 (X.Y.Z) into directory $2, checked against $3 (sha256), with Python $4. Prints its path.
fetch_wheel() {
  "$4" -m pip download --quiet --disable-pip-version-check --no-deps --only-binary=:all: --dest "$2" "aidd==$1" >&2 \
    || die "could not download aidd $1 from PyPI"
  set -- "$2"/aidd-"$1"-*.whl "$3" "$4"
  [ -f "$1" ] || die "no aidd wheel was downloaded"
  "$3" - "$1" "$2" <<'PY' || die "the wheel's sha256 does not match AIDD_SHA256"
import hashlib, sys
with open(sys.argv[1], "rb") as fh:
    got = hashlib.sha256(fh.read()).hexdigest()
sys.exit(got != sys.argv[2].strip().lower())
PY
  printf '%s\n' "$1"
}

main() {
  ref="${AIDD_REF:-v1.0.0}"
  sha256="${AIDD_SHA256:-}"
  # Before the first release there is nothing to install by default: say what to set, before any download.
  if [ -z "${AIDD_REF:-}" ] && [ -z "$PUBLISHED" ] && [ -z "$sha256" ]; then
    die "aidd is not published on PyPI yet, so there is no default release to install (the default, ${ref}, may not be released yet). Set AIDD_REF to a full commit SHA of https://github.com/thaithienvanid/aidd to build from source, such as the tip of main: git ls-remote https://github.com/thaithienvanid/aidd refs/heads/main. Once a release exists, set AIDD_REF to its tag and AIDD_SHA256 to its wheel's line in SHA256SUMS"
  fi

  case "$ref" in
    *"
"*) die "AIDD_REF must be a vX.Y.Z release tag or a full commit SHA" ;;
  esac
  if printf '%s\n' "$ref" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
    version="${ref#v}"
    spec="aidd==${version}"
    source=""
    if [ -z "$PUBLISHED" ] && [ -z "$sha256" ]; then
      die "aidd is not published on PyPI yet, so installing ${ref} by name could fetch anyone's package. Set AIDD_REF to a full commit SHA of https://github.com/thaithienvanid/aidd to build from source, or AIDD_SHA256 to the wheel's sha256 from SHA256SUMS on the ${ref} GitHub Release"
    fi
  elif printf '%s\n' "$ref" | grep -Eq '^[0-9a-f]{40}$'; then
    [ -z "$sha256" ] || die "AIDD_SHA256 applies to a release wheel, not to a source install"
    say "AIDD_REF is a commit, so aidd is built from source at ${ref}; use a release tag for a verified install"
    spec="git+https://github.com/thaithienvanid/aidd@${ref}"
    source="yes"
  else
    die "AIDD_REF must be a vX.Y.Z release tag or a full commit SHA; got '$ref'"
  fi

  if [ -n "$sha256" ]; then
    checker="$(checker_python)" || no_python "checking AIDD_SHA256"
    need_pip "$checker"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    spec="$(fetch_wheel "$version" "$tmp" "$sha256" "$checker")"
    say "verified $(basename "$spec") against AIDD_SHA256"
  fi

  if command -v uv >/dev/null 2>&1; then
    say "installing aidd ${ref} with uv"
    if [ -n "$source" ]; then
      uv tool install --force --python '>=3.11' "$spec"
    else
      uv tool install --force --python '>=3.11' --no-build "$spec"
    fi
  elif command -v pipx >/dev/null 2>&1; then
    py="$(find_python)" || no_python "pipx"
    say "installing aidd ${ref} with pipx and ${py}"
    if [ -n "$source" ]; then
      pipx install --force --python "$py" "$spec"
    else
      pipx install --force --python "$py" --pip-args=--only-binary=:all: "$spec"
    fi
  else
    # No uv or pipx: a private virtual environment (PEP 668 forbids pip --user on most system Pythons).
    py="$(find_python)" || no_python "installing without uv or pipx"
    "$py" -c 'import ensurepip, venv' >/dev/null 2>&1 \
      || die "the venv module is not available for $py: install it (Debian and Ubuntu: apt install python3-venv), or install uv"
    venv="${XDG_DATA_HOME:-${HOME}/.local/share}/aidd/venv"
    say "installing aidd ${ref} into ${venv} with ${py} (install uv or pipx to manage it as a tool)"
    "$py" -m venv "$venv" || die "could not create a virtual environment at ${venv}"
    need_pip "$venv/bin/python"
    if [ -n "$source" ]; then
      "$venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$spec"
    else
      "$venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade --only-binary=:all: "$spec"
    fi
    mkdir -p "${HOME}/.local/bin"
    ln -sf "$venv/bin/aidd" "${HOME}/.local/bin/aidd"
    case ":${PATH}:" in
      *":${HOME}/.local/bin:"*) ;;
      *) say "add ${HOME}/.local/bin to your PATH to run aidd" ;;
    esac
  fi

  if command -v aidd >/dev/null 2>&1; then
    say "installed: $(aidd --version)"
  else
    say "installed; open a new shell so aidd is on your PATH"
  fi
  say ""
  say "Next, inside your repository:"
  say "  aidd init --profile solo                                  # one person and their agents"
  say "  aidd init --profile team --approvers @org/leads --specialist security=@org/security --test \"npm test\""
  say "aidd init detects your coding agents (Claude Code, Codex, Copilot, Cursor, Antigravity, Kiro, and 20 more) and wires each one."
  say "Add --team for the delivery team. Then: aidd doctor. Docs: https://github.com/thaithienvanid/aidd#get-started"
}

main "$@"
