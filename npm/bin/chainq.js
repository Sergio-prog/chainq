#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const { version } = require("../package.json");

function tryRun(cmd, args) {
  const result = spawnSync(cmd, args, { stdio: "inherit" });
  if (result.error && result.error.code === "ENOENT") return false;
  process.exit(result.status ?? 1);
}

const args = process.argv.slice(2);
tryRun("uvx", [`chainq@${version}`, ...args]);
tryRun("pipx", ["run", "--spec", `chainq==${version}`, "chainq", ...args]);
console.error("chainq is a Python CLI; this launcher needs uv (or pipx) on your PATH.");
console.error("  install uv:      curl -LsSf https://astral.sh/uv/install.sh | sh");
console.error("  or chainq itself: curl -fsSL https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh");
process.exit(1);
