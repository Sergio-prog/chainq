#!/usr/bin/env sh
set -eu

REPO_URL="https://github.com/Sergio-prog/chainq"

if [ -t 1 ]; then
  BOLD="$(printf '\033[1m')"
  DIM="$(printf '\033[2m')"
  CYAN="$(printf '\033[36m')"
  RESET="$(printf '\033[0m')"
else
  BOLD=""; DIM=""; CYAN=""; RESET=""
fi

say() { printf '%s\n' "$*"; }

install_with_uv() {
  say "${DIM}==> Installing chainq with uv${RESET}"
  uv tool install -q --force chainq 2>/dev/null \
    || uv tool install -q --force --from "git+${REPO_URL}" chainq
}

install_with_pipx() {
  say "${DIM}==> Installing chainq with pipx${RESET}"
  pipx install --force chainq >/dev/null 2>&1 \
    || pipx install --force "git+${REPO_URL}" >/dev/null
}

bootstrap_uv() {
  say "${DIM}==> Installing uv first (https://astral.sh/uv)${RESET}"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
}

if command -v uv >/dev/null 2>&1; then
  install_with_uv
elif command -v pipx >/dev/null 2>&1; then
  install_with_pipx
else
  bootstrap_uv
  install_with_uv
fi

export PATH="$HOME/.local/bin:$PATH"
VERSION="$(chainq version 2>/dev/null || echo '?')"

say ""
say "${CYAN}       _           _              ${RESET}"
say "${CYAN}  ___ | |__   __ _(_)_ __   __ _  ${RESET}"
say "${CYAN} / __|| '_ \\ / _\` | | '_ \\ / _\` | ${RESET}"
say "${CYAN}| (__ | | | | (_| | | | | | (_| | ${RESET}"
say "${CYAN} \\___||_| |_|\\__,_|_|_| |_|\\__, | ${RESET}"
say "${CYAN}                              |_| ${RESET}"
say ""
say "  ${BOLD}chainq v${VERSION}${RESET} — crypto data CLI for agents and humans"
say ""
say "  Get started:"
say ""
say "    ${BOLD}chainq price eth btc${RESET}              Prices, 24h change, mcap"
say "    ${BOLD}chainq trending${RESET}                   Trending assets right now"
say "    ${BOLD}chainq balance vitalik.eth${RESET}        Wallet balances (ENS ok)"
say "    ${BOLD}chainq gas -n base${RESET}                Gas + transfer cost in USD"
say "    ${BOLD}chainq protocols aave markets${RESET}     Aave v3 supply/borrow APY"
say "    ${BOLD}chainq protocols hl price BTC${RESET}     Hyperliquid perps"
say "    ${BOLD}chainq --help${RESET}                     All commands"
say ""
say "  Add the skill for your agents:"
say ""
say "    ${BOLD}npx skills add Sergio-prog/chainq${RESET}"
say ""
if ! command -v chainq >/dev/null 2>&1; then
  say "  ${DIM}note: restart your shell (or add ~/.local/bin to PATH) before running chainq${RESET}"
fi
