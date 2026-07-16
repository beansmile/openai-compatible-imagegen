#!/usr/bin/env bash
# Installer for the openai-compatible-imagegen agent skill.
#
#   curl -fsSL https://raw.githubusercontent.com/beansmile/openai-compatible-imagegen/main/install.sh | bash
#
# With no flags, installs into every detected harness (Claude Code and/or
# Codex CLI). Flags pick targets explicitly and can be combined:
#   --claude    ~/.claude/skills/                    (Claude Code, personal)
#   --codex     ${CODEX_HOME:-~/.codex}/skills/      (Codex CLI)
#   --project   ./.claude/skills/                    (current project only)
set -euo pipefail

REPO="beansmile/openai-compatible-imagegen"
REPO_URL="https://github.com/${REPO}.git"
TARBALL_URL="https://github.com/${REPO}/archive/refs/heads/main.tar.gz"
SKILL_NAME="openai-compatible-imagegen"

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; }

targets=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --claude)  targets+=("$HOME/.claude/skills/$SKILL_NAME") ;;
    --codex)   targets+=("${CODEX_HOME:-$HOME/.codex}/skills/$SKILL_NAME") ;;
    --project) targets+=("$PWD/.claude/skills/$SKILL_NAME") ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
  shift
done

if [[ ${#targets[@]} -eq 0 ]]; then
  [[ -d "$HOME/.claude" ]] && targets+=("$HOME/.claude/skills/$SKILL_NAME")
  [[ -d "${CODEX_HOME:-$HOME/.codex}" ]] && targets+=("${CODEX_HOME:-$HOME/.codex}/skills/$SKILL_NAME")
  # No harness detected: default to Claude Code's personal skills directory.
  [[ ${#targets[@]} -eq 0 ]] && targets+=("$HOME/.claude/skills/$SKILL_NAME")
fi

install_into() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  if command -v git >/dev/null 2>&1; then
    if [[ -d "$dest/.git" ]]; then
      git -C "$dest" pull --ff-only --quiet
      echo "updated:   $dest"
    elif [[ -e "$dest" ]]; then
      echo "error: $dest exists but is not a git checkout; remove it and rerun." >&2
      return 1
    else
      git clone --depth 1 --quiet "$REPO_URL" "$dest"
      echo "installed: $dest"
    fi
  else
    mkdir -p "$dest"
    curl -fsSL "$TARBALL_URL" | tar -xz --strip-components=1 -C "$dest"
    echo "installed: $dest (tarball; install git to enable updates)"
  fi
}

for dest in "${targets[@]}"; do
  install_into "$dest"
done

echo
if [[ -n "${OPENAI_BASE_URL:-}" && -n "${OPENAI_API_KEY:-}" ]]; then
  echo "Credentials detected (OPENAI_BASE_URL and OPENAI_API_KEY are set)."
  echo "You're ready — ask your agent to generate an image."
else
  echo "Almost done — set your credentials (values are never printed):"
  echo '  export OPENAI_BASE_URL="https://your-provider.example/v1"'
  echo '  export OPENAI_API_KEY="<your key>"'
  echo "Add the exports to your shell profile (e.g. ~/.zshrc), then restart"
  echo "your agent session so it inherits them."
fi
