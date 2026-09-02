const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const colorize = (line: string) =>
  esc(line)
    .replace(/([+]\d[\d.,]*%(?:\/h)?)/g, '<span class="up">$1</span>')
    .replace(/([-]\d[\d.,]*%(?:\/h)?)/g, '<span class="down">$1</span>')
    .replace(/(\$[\d.,]+[KMBT]?)/g, '<span class="num">$1</span>');

type Session = { cmd: string; out: string[] }[];

const sessions: Session[] = [
  [
    {
      cmd: "chainq evm sig 'transfer(address,uint256)'",
      out: ["transfer(address,uint256): 0xa9059cbb"],
    },
    {
      cmd: "chainq evm block-number -n base",
      out: ["Base latest block: 32,884,219"],
    },
    {
      cmd: "chainq evm to-wei 1.5 ether",
      out: ["1.5 ether: 1500000000000000000"],
    },
  ],
  [
    {
      cmd: "chainq price eth btc hype",
      out: [
        "ETH (Ethereum): $1,788.78  24h +0.57%  mcap $215.92B",
        "BTC (Bitcoin): $63,644.00  24h +1.66%  mcap $1.28T",
        "HYPE (Hyperliquid): $71.15  24h +2.84%  mcap $15.83B",
      ],
    },
    {
      cmd: "chainq balance vitalik.eth",
      out: ["vitalik.eth (0xd8dA…6045) on Ethereum: 6.6177 ETH (~$11,837.59)"],
    },
    {
      cmd: "chainq gas -n base",
      out: ["Base gas: 0.006 gwei (base 0.005 gwei, priority p50 0.0014 gwei) — native transfer ≈ $0.0002"],
    },
  ],
  [
    {
      cmd: "chainq protocols aave markets -n base -l 3",
      out: [
        "Aave v3 on Base: $695.05M total market size, 1 market (Base)",
        "USDC [Base]: supply 3.14%  borrow 4.23%  supplied $179.26M  util 82.86%",
        "WETH [Base]: supply 1.59%  borrow 2.29%  supplied $164.83M  util 81.61%",
        "cbBTC [Base]: supply 0.02%  borrow 0.73%  supplied $150.05M  util 4.50%",
      ],
    },
    {
      cmd: "chainq protocols pendle markets -l 2",
      out: [
        "SIERRA (exp 2026-08-06, 30d): implied APY 10.03%  LP APY 6.95%  liquidity $19.82M",
        "USDat (exp 2026-08-27, 51d): implied APY 7.88%  LP APY 2.98%  liquidity $8.52M",
      ],
    },
  ],
  [
    {
      cmd: "chainq protocols hl funding -l 3",
      out: [
        "BLUR-PERP funding: -0.4023%/h (-3524.5% APR)  mark $0.020041  OI $1.56M",
        "STBL-PERP funding: +0.0140%/h (+122.3% APR)  mark $0.024626  OI $2.40M",
        "AERO-PERP funding: +0.0135%/h (+118.1% APR)  mark $0.57497  OI $14.41M",
      ],
    },
    {
      cmd: "chainq nft floor pudgypenguins",
      out: ["pudgypenguins: floor 4.62 ETH (~$8,266.80)  24h vol 36.4067 ETH  owners 5,087"],
    },
    {
      cmd: "chainq price eth -q",
      out: ["1788.78"],
    },
  ],
  [
    {
      cmd: "chainq stables --min-mcap 5e9 -l 3",
      out: [
        "Total stablecoin mcap: $312.48B (390 tracked)",
        "1. USDT (Tether): $184.21B  price $0.999174  7d -0.42%  [fiat-backed]",
        "2. USDC (USD Coin): $73.16B  price $0.999773  7d -0.86%  [fiat-backed]",
        "3. USDS (Sky Dollar): $7.97B  price $0.999716  7d -2.96%  [crypto-backed]",
      ],
    },
    {
      cmd: "chainq trending -l 3",
      out: [
        "1. ANSEM (The Black Bull): $0.413151  24h +29.51%  mcap $172.11M",
        "2. LIT (Lighter): $2.67  24h +11.62%  mcap $667.21M",
        "3. VVV (Venice Token): $12.16  24h +3.21%  mcap $574.08M",
      ],
    },
  ],
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const renderStatic = (body: HTMLElement, session: Session) => {
  body.innerHTML = session
    .map(
      (b) =>
        `<div><span class="t-prompt">$ </span><span class="t-cmd">${esc(b.cmd)}</span></div>` +
        b.out.map((l) => `<div class="t-out">${colorize(l)}</div>`).join(""),
    )
    .join("");
};

const runTerminal = async (body: HTMLElement) => {
  if (reducedMotion) {
    renderStatic(body, sessions[0]);
    return;
  }
  let i = 0;
  for (;;) {
    const session = sessions[i % sessions.length];
    body.innerHTML = "";
    for (const block of session) {
      const cmdLine = document.createElement("div");
      cmdLine.innerHTML =
        '<span class="t-prompt">$ </span><span class="t-cmd"></span><span class="t-cursor"></span>';
      body.appendChild(cmdLine);
      const cmdSpan = cmdLine.querySelector(".t-cmd") as HTMLElement;
      for (const ch of block.cmd) {
        cmdSpan.textContent += ch;
        await sleep(22 + Math.random() * 30);
      }
      await sleep(320);
      cmdLine.querySelector(".t-cursor")?.remove();
      for (const line of block.out) {
        const el = document.createElement("div");
        el.className = "t-out";
        el.innerHTML = colorize(line);
        body.appendChild(el);
        await sleep(110);
      }
      await sleep(700);
    }
    const idle = document.createElement("div");
    idle.innerHTML = '<span class="t-prompt">$ </span><span class="t-cursor"></span>';
    body.appendChild(idle);
    await sleep(3400);
    i++;
  }
};

const installs = [
  { key: "curl", cmd: "curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh" },
  { key: "windows", cmd: 'powershell -c "irm https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.ps1 | iex"' },
  { key: "brew", cmd: "brew install sergio-prog/tap/chainq" },
  { key: "uv", cmd: "uv tool install chainq" },
  { key: "pipx", cmd: "pipx install chainq" },
];

const buildInstall = () => {
  const tabs = document.getElementById("src-tabs")!;
  const cmd = document.getElementById("install-cmd")!;
  const copy = document.getElementById("install-copy")!;
  const select = (idx: number) => {
    tabs.querySelectorAll(".src-tab").forEach((b, i) => {
      b.setAttribute("aria-selected", String(i === idx));
    });
    cmd.textContent = installs[idx].cmd;
    copy.dataset.copy = installs[idx].cmd;
  };
  installs.forEach((it, i) => {
    const btn = document.createElement("button");
    btn.className = "src-tab";
    btn.setAttribute("role", "tab");
    btn.textContent = it.key;
    btn.addEventListener("click", () => select(i));
    tabs.appendChild(btn);
  });
  select(0);
};

const wireCopyButtons = () => {
  document.body.addEventListener("click", async (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>(".copy-btn");
    if (!btn) return;
    await navigator.clipboard.writeText(btn.dataset.copy ?? "");
    btn.textContent = "copied";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = "copy";
      btn.classList.remove("copied");
    }, 1400);
  });
};

buildInstall();
wireCopyButtons();
runTerminal(document.getElementById("terminal-body")!);
