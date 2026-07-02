#!/usr/bin/env sh
set -eu

REPO_URL="https://github.com/Sergio-prog/chainq"

say() { printf '%s\n' "$*"; }

install_with_uv() {
  say "installing chainq with uv..."
  uv tool install --force --from "git+${REPO_URL}" chainq
}

install_with_pipx() {
  say "installing chainq with pipx..."
  pipx install --force "git+${REPO_URL}"
}

bootstrap_uv() {
  say "uv not found — installing uv first (https://astral.sh/uv)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
}

main() {
  if command -v uv >/dev/null 2>&1; then
    install_with_uv
  elif command -v pipx >/dev/null 2>&1; then
    install_with_pipx
  else
    bootstrap_uv
    install_with_uv
  fi

  if command -v chainq >/dev/null 2>&1; then
    say ""
    say "chainq $(chainq version) installed. Try:"
    say "  chainq price eth btc"
    say "  chainq gas -n base"
    say "  chainq -h"
  else
    say ""
    say "installed — restart your shell (or add ~/.local/bin to PATH), then run: chainq -h"
  fi
}

main
