$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/Sergio-prog/chainq"
$UvInstaller = "https://astral.sh/uv/install.ps1"

function Have($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $env:Path = "$env:USERPROFILE\.local\bin;" +
        [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
        [Environment]::GetEnvironmentVariable("Path", "Machine")
}

if (Have "uv") {
    Write-Host "==> Installing chainq with uv" -ForegroundColor DarkGray
} elseif (Have "pipx") {
    Write-Host "==> Installing chainq with pipx" -ForegroundColor DarkGray
    pipx install --force chainq
    if ($LASTEXITCODE -ne 0) { pipx install --force "git+$RepoUrl" }
} else {
    if (Have "python") {
        Write-Host "==> Python found; installing uv to manage the chainq install (https://astral.sh/uv)" -ForegroundColor DarkGray
    } else {
        Write-Host "==> Installing uv; it will also provision Python 3.12+ for chainq (https://astral.sh/uv)" -ForegroundColor DarkGray
    }
    Invoke-RestMethod $UvInstaller | Invoke-Expression
    Refresh-Path
    if (-not (Have "uv")) {
        throw "uv installed but not on PATH; open a new terminal and rerun this script"
    }
}

if (Have "uv") {
    uv tool install -q --force chainq
    if ($LASTEXITCODE -ne 0) { uv tool install -q --force --from "git+$RepoUrl" chainq }
}

Refresh-Path
$version = "?"
if (Have "chainq") { $version = (chainq version) }

Write-Host ""
Write-Host "       _           _              " -ForegroundColor Cyan
Write-Host "  ___ | |__   __ _(_)_ __   __ _  " -ForegroundColor Cyan
Write-Host " / __|| '_ \ / _`` | | '_ \ / _`` | " -ForegroundColor Cyan
Write-Host "| (__ | | | | (_| | | | | | (_| | " -ForegroundColor Cyan
Write-Host " \___||_| |_|\__,_|_|_| |_|\__, | " -ForegroundColor Cyan
Write-Host "                              |_| " -ForegroundColor Cyan
Write-Host ""
Write-Host "  chainq v$version - crypto data CLI for agents and humans"
Write-Host ""
Write-Host "  Get started:"
Write-Host ""
Write-Host "    chainq price eth btc              Prices, 24h change, mcap"
Write-Host "    chainq trending                   Trending assets right now"
Write-Host "    chainq balance vitalik.eth        Wallet balances (ENS ok)"
Write-Host "    chainq gas -n base                Gas + transfer cost in USD"
Write-Host "    chainq protocols aave markets     Aave v3 supply/borrow APY"
Write-Host "    chainq protocols hl price BTC     Hyperliquid perps"
Write-Host "    chainq --help                     All commands"
Write-Host ""
Write-Host "  Add the skill for your agents:"
Write-Host ""
Write-Host "    npx skills add Sergio-prog/chainq"
Write-Host ""
if (-not (Have "chainq")) {
    Write-Host "  note: open a new terminal before running chainq (PATH was just updated)" -ForegroundColor DarkGray
}
