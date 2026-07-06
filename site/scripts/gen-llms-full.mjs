import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const skill = readFileSync(join(here, "../../skills/chainq/SKILL.md"), "utf8");
const body = skill.slice(skill.indexOf("## Output rules"));

const preamble = `# chainq — full reference

> Agent-first CLI for onchain and crypto market data. No API keys or setup needed for any command below; curated public RPC endpoints with automatic fallback are built in. This file contains the complete command reference with usage guidance for agents.

## Install

- One-liner: \`curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh\`
- Homebrew: \`brew install sergio-prog/tap/chainq\`
- uv: \`uv tool install chainq\` / pipx: \`pipx install chainq\`
- Requires Python 3.12+ (the install script bootstraps uv). Update with \`chainq update\`.
- Teach an agent: \`npx skills add Sergio-prog/chainq\` installs the chainq skill.

`;

writeFileSync(join(here, "../public/llms-full.txt"), preamble + body);
