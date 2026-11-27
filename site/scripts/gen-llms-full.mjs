import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const skillDir = join(here, "../../skills/chainq");
const slug = (title) => title.toLowerCase().replace(/[^a-z0-9 -]/g, "").trim().replace(/ +/g, "-");

const references = readdirSync(join(skillDir, "references"))
  .filter((name) => name.endsWith(".md"))
  .sort()
  .map((name) => {
    const text = readFileSync(join(skillDir, "references", name), "utf8");
    return { name, anchor: slug(text.match(/^# (.+)$/m)[1]), text };
  });

const relink = (text) =>
  references.reduce(
    (out, ref) => out.replaceAll(`](references/${ref.name})`, `](#${ref.anchor})`).replaceAll(`](${ref.name})`, `](#${ref.anchor})`),
    text,
  );

const skill = readFileSync(join(skillDir, "SKILL.md"), "utf8");
const core = relink(skill.slice(skill.indexOf("## Output")));
const bodies = references.map((ref) => relink(ref.text.replace(/^## /gm, "### ").replace(/^# /m, "## ")));

const preamble = `# chainq: full reference

> Agent-first CLI for onchain and crypto market data. Public RPC endpoints with automatic fallback are built in; only \`nft top\` and long-tail NFT slugs need an API key. This file is the agent skill plus every per-domain reference in one page.

## Install

- One-liner: \`curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh\`
- Homebrew: \`brew install sergio-prog/tap/chainq\`
- uv: \`uv tool install chainq\` / pipx: \`pipx install chainq\`
- Requires Python 3.12+ (the install script bootstraps uv). Update with \`chainq update\`.
- Teach an agent: \`npx skills add Sergio-prog/chainq\` installs the chainq skill.

`;

writeFileSync(join(here, "../public/llms-full.txt"), [preamble + core, ...bodies].join("\n"));
