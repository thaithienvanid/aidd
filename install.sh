#!/bin/sh
# aidd installer: installs the aidd CLI (Python 3.11+, no dependencies) from a GitHub Release's prebuilt wheel,
# with uv, pipx, or a private venv, then prints the next step. uv brings its own Python 3.11+ when the
# system's is older (stock macOS ships 3.9); pipx and the venv need a Python 3.11+ on PATH.
# aidd is not on PyPI, and a package named aidd there is not this project.
# Usage: curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh | sh
# Before the first release, a commit to build from:
#   curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh | AIDD_REF=<commit sha> sh
#
# Environment:
#   AIDD_REF          the release to install (default below). A vX.Y.Z tag installs the wheel from that GitHub
#                     Release, after checking it against the release's SHA256SUMS. A full commit SHA installs
#                     from source at that commit; that builds on your machine and is for testing unreleased
#                     code only. Anything else is refused.
#   AIDD_SHA256       the sha256 you expect for the release wheel, from a source you trust. When set, the
#                     wheel must also match it.
#   AIDD_RELEASE_URL  where the release files come from, for a mirror of the GitHub Releases (default:
#                     https://github.com/thaithienvanid/aidd/releases/download), over https:// or file://.
#                     A mirror serves the wheel and its SHA256SUMS both, so it needs AIDD_SHA256, or gh on
#                     PATH, to prove where the wheel came from.
#
# With gh on PATH, the installer also verifies the wheel's build provenance (gh attestation verify) before it
# installs anything.
#
# No installer at all: each GitHub Release also carries aidd.pyz, the CLI as one zipapp that any Python 3.11+
# runs as `python3 aidd.pyz`. This script does not install it; download it with SHA256SUMS, check it, and verify
# it with `gh attestation verify aidd.pyz --repo thaithienvanid/aidd` (docs/INSTALL.md, "One file: aidd.pyz").
#
# Everything runs inside main, called on the last line, so a truncated download runs nothing.
set -eu

say() { printf '%s\n' "$*"; }
die() { printf 'aidd install: %s\n' "$*" >&2; exit 1; }

# The path of a Python 3.11 or later on PATH; fails when there is none.
find_python() {
  for c in python3.15 python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
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

# A Python 3.11+ for downloading and checking the wheel: the system's, or one uv finds or installs.
checker_python() {
  if find_python; then return 0; fi
  command -v uv >/dev/null 2>&1 || return 1
  uv python find '>=3.11' 2>/dev/null && return 0
  uv python install >&2 || return 1
  uv python find '>=3.11'
}

need_pip() {
  "$1" -I -m pip --version >/dev/null 2>&1 \
    || die "pip is not available for $1: install it (Debian and Ubuntu: apt install python3-pip), or install uv"
}

# The wheel of release $1 (X.Y.Z) from $2 (the releases' base URL) into directory $3, with Python $5. It must match the
# release's SHA256SUMS, and $4 (AIDD_SHA256) when set. Prints its path; says why and installs nothing otherwise.
fetch_wheel() {
  "$5" -I - "$1" "$2" "$3" "$4" <<'PY' || exit 1
import hashlib, ssl, sys, urllib.error, urllib.request

version, base, dest, pinned = sys.argv[1:5]
tag, name = f"v{version}", f"aidd-{version}-py3-none-any.whl"


def get(url, most):
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(most + 1)
    if len(data) > most:
        raise ValueError(f"{url} is larger than {most} bytes")
    return data


MISSING = (
    f"aidd install: the {tag} release has no {name} or SHA256SUMS at {base}. Before the first release, set AIDD_REF to a "
    "full commit SHA of https://github.com/thaithienvanid/aidd to build from source, such as the tip of main: "
    "git ls-remote https://github.com/thaithienvanid/aidd refs/heads/main"
)
try:
    sums = get(f"{base}/{tag}/SHA256SUMS", 256 * 1024).decode("utf-8", "replace")
    wheel = get(f"{base}/{tag}/{name}", 32 * 1024 * 1024)
except urllib.error.HTTPError as exc:  # before URLError, which it extends
    sys.exit(MISSING if exc.code == 404 else f"aidd install: {base} answered {exc.code} for the {tag} release: try again later")
except urllib.error.URLError as exc:
    if isinstance(exc.reason, FileNotFoundError):
        sys.exit(MISSING)
    if isinstance(exc.reason, ssl.SSLError):
        sys.exit(
            f"aidd install: this Python could not verify the server's certificate ({exc.reason}). With the python.org Python "
            "on macOS, run its Install Certificates.command; or install uv, which brings a Python that can"
        )
    sys.exit(f"aidd install: could not reach {base} ({exc.reason}): check the network, or set HTTPS_PROXY behind a proxy")
except (OSError, ValueError) as exc:
    sys.exit(f"aidd install: could not download {name} and SHA256SUMS from the {tag} release ({exc})")
listed = [p[0].lower() for p in (line.split() for line in sums.splitlines()) if len(p) == 2 and p[1].lstrip("*") == name]
got = hashlib.sha256(wheel).hexdigest()
if not listed:
    sys.exit(f"aidd install: the {tag} release's SHA256SUMS does not list {name}, so nothing was installed")
if got != listed[0]:
    sys.exit(f"aidd install: {name} does not match the {tag} release's SHA256SUMS, so nothing was installed")
if pinned and got != pinned.strip().lower():
    sys.exit(f"aidd install: {name} does not match AIDD_SHA256, so nothing was installed")
path = f"{dest}/{name}"
with open(path, "wb") as fh:
    fh.write(wheel)
print(path)
PY
}

main() {
  ref="${AIDD_REF:-v1.0.0}"
  sha256="${AIDD_SHA256:-}"
  releases="${AIDD_RELEASE_URL:-https://github.com/thaithienvanid/aidd/releases/download}"
  case "$releases" in
    https://*|file://*) ;;
    *) die "AIDD_RELEASE_URL must start with https://, or file:// for a copy on this machine; got '$releases'" ;;
  esac

  case "$ref" in
    *"
"*) die "AIDD_REF must be a vX.Y.Z release tag or a full commit SHA" ;;
  esac
  if printf '%s\n' "$ref" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
    # A mirror serves the wheel and its SHA256SUMS both, so the two prove nothing about where the wheel came from.
    if [ -n "${AIDD_RELEASE_URL:-}" ] && [ -z "$sha256" ] && ! command -v gh >/dev/null 2>&1; then
      die "a mirror's SHA256SUMS can't prove where its wheel came from: set AIDD_SHA256 to the wheel's line in SHA256SUMS on https://github.com/thaithienvanid/aidd/releases/tag/${ref}, or put gh on PATH to verify its build provenance"
    fi
    checker="$(checker_python)" || no_python "checking the release wheel"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    spec="$(fetch_wheel "${ref#v}" "${releases%/}" "$tmp" "$sha256" "$checker")"
    checked="the ${ref} release's SHA256SUMS"
    [ -z "$sha256" ] || checked="${checked} and AIDD_SHA256"
    say "verified $(basename "$spec") against ${checked}"
    if command -v gh >/dev/null 2>&1; then
      # Only the release workflow's attestation counts, never one another workflow of the repository made.
      if ! gh attestation verify "$spec" --repo thaithienvanid/aidd --signer-workflow thaithienvanid/aidd/.github/workflows/release.yml >&2; then
        gh attestation --help >/dev/null 2>&1 \
          || die "this gh has no attestation command, so it can't verify the wheel: update gh (https://cli.github.com), then run the installer again"
        gh auth status >/dev/null 2>&1 \
          || die "gh could not verify the wheel, and it is not signed in: run gh auth login, then the installer again"
        die "gh attestation verify refused $(basename "$spec"), so nothing was installed"
      fi
      say "gh verified its build provenance"
    fi
    source=""
  elif printf '%s\n' "$ref" | grep -Eq '^[0-9a-f]{40}$'; then
    [ -z "$sha256" ] || die "AIDD_SHA256 applies to a release wheel, not to a source install"
    say "AIDD_REF is a commit, so aidd is built from source at ${ref}; use a release tag for a verified install"
    spec="git+https://github.com/thaithienvanid/aidd@${ref}"
    source="yes"
  else
    die "AIDD_REF must be a vX.Y.Z release tag or a full commit SHA; got '$ref'"
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
    "$py" -I -c 'import ensurepip, venv' >/dev/null 2>&1 \
      || die "the venv module is not available for $py: install it (Debian and Ubuntu: apt install python3-venv), or install uv"
    venv="${XDG_DATA_HOME:-${HOME}/.local/share}/aidd/venv"
    say "installing aidd ${ref} into ${venv} with ${py} (install uv or pipx to manage it as a tool)"
    "$py" -I -m venv "$venv" || die "could not create a virtual environment at ${venv}"
    need_pip "$venv/bin/python"
    if [ -n "$source" ]; then
      "$venv/bin/python" -I -m pip install --quiet --disable-pip-version-check --upgrade "$spec"
    else
      "$venv/bin/python" -I -m pip install --quiet --disable-pip-version-check --upgrade --only-binary=:all: "$spec"
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
