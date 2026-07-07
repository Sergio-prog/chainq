#!/usr/bin/env sh
set -eu

REPO_URL="https://github.com/Sergio-prog/chainq"
UV_INSTALLER="https://astral.sh/uv/install.sh"
PS_ONELINER='powershell -c "irm https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.ps1 | iex"'

if [ -t 1 ]; then
  BOLD="$(printf '\033[1m')"
  DIM="$(printf '\033[2m')"
  CYAN="$(printf '\033[36m')"
  RESET="$(printf '\033[0m')"
else
  BOLD=""; DIM=""; CYAN=""; RESET=""
fi

say() { printf '%s\n' "$*"; }
fail() { say "error: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

check_platform() {
  case "$(uname -s 2>/dev/null || echo unknown)" in
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
      say "This looks like Windows. Use the PowerShell installer instead:"
      say ""
      say "  ${BOLD}${PS_ONELINER}${RESET}"
      exit 1
      ;;
  esac
}

fetch() {
  if have curl; then
    curl -LsSf "$1"
  elif have wget; then
    wget -qO- "$1"
  else
    fail "need curl or wget to download uv (or install uv/pipx yourself and rerun)"
  fi
}

bootstrap_uv() {
  if have python3 || have python; then
    say "${DIM}==> Python found; installing uv to manage the chainq install (https://astral.sh/uv)${RESET}"
  else
    say "${DIM}==> Installing uv; it will also provision Python 3.12+ for chainq (https://astral.sh/uv)${RESET}"
  fi
  fetch "$UV_INSTALLER" | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
  have uv || fail "uv installed but not on PATH; restart your shell and rerun this script"
}

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

banner() {
  say ""
  say "${CYAN}       _           _              ${RESET}"
  say "${CYAN}  ___ | |__   __ _(_)_ __   __ _  ${RESET}"
  say "${CYAN} / __|| '_ \\ / _\` | | '_ \\ / _\` | ${RESET}"
  say "${CYAN}| (__ | | | | (_| | | | | | (_| | ${RESET}"
  say "${CYAN} \\___||_| |_|\\__,_|_|_| |_|\\__, | ${RESET}"
  say "${CYAN}                              |_| ${RESET}"
  say ""
  say "  ${BOLD}chainq v$1${RESET} — crypto data CLI for agents and humans"
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
}

main() {
  check_platform
  if have uv; then
    install_with_uv
  elif have pipx; then
    install_with_pipx
  else
    bootstrap_uv
    install_with_uv
  fi
  export PATH="$HOME/.local/bin:$PATH"
  banner "$(chainq version 2>/dev/null || echo '?')"
  if ! have chainq; then
    say "  ${DIM}note: restart your shell (or add ~/.local/bin to PATH) before running chainq${RESET}"
  fi
}

main
