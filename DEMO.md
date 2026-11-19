# Demo — CMC MCP Server

Record a 2–3 minute screen recording of the server working, for the
DoraHacks submission. No API key is needed for this demo (keyless mode).

## 0. Recording method — terminal capture (reproducible)

The demo is recorded as a terminal session, not through the Inspector
web UI, because that is what can be captured reliably headlessly:

```bash
bash scripts/record_demo_tmux.sh   # runs scripts/demo_record.sh in tmux,
                                   # captures the real screen every 0.5s
python3 scripts/render_demo_frames.py
ffmpeg -y -framerate 2 -i /tmp/demo_frames/f%04d.png \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p cmc-demo.mp4
```

The video is a faithful rendering of the real terminal transcript —
every command and every number in it is a genuine live call, nothing
is staged. (An Xvfb + xterm + ffmpeg screen grab was tried first: the
Inspector CLI disturbs the X terminal and the display froze on the
tool list while the session kept running in the background.)

The script runs the three prompts below via the Inspector CLI
(`scripts/demo_record.sh`), prints `CMC_API_KEY=<not set>` up front,
retries each live call up to 3 times, and shows only the first 50
lines of long outputs on screen.

## 1. Start the MCP Inspector

From the repo root:

```bash
FASTMCP_CHECK_FOR_UPDATES=off npx -y @modelcontextprotocol/inspector \
  -e HTTPS_PROXY="$HTTPS_PROXY" -e SSL_CERT_FILE="$SSL_CERT_FILE" \
  /path/to/cmc-mcp-server/.venv/bin/python -m cmc_mcp.server
```

The `-e` flags matter: the inspector does not inherit your shell
environment, so the server would start without your proxy / CA-bundle
variables and every live call would fail TLS. Pass through whatever
your network needs (omit the flags if you connect directly).

The inspector opens in your browser (default http://localhost:6274).
Click **Connect**, then open the **Tools** tab — you should see all
20 tools listed.

> If `npx` is unavailable, use the stdio verifier instead:
> `python scripts/verify_tools.py` (lists all 20 tools, no UI).

## 2. Demo prompts (run in order)

### Prompt 1 — Price check (30s)

Call `get_price` with:

```json
{ "symbols": "BTC,ETH,SOL", "convert": "USD" }
```

Say: *"Live prices for the top three coins, straight from CoinMarketCap —
no API key configured."*

### Prompt 2 — Market brief (60s)

Call `market_brief` with no arguments.

Say: *"One call, whole market: total cap, Fear & Greed, CMC100, Altcoin
Season Index, and today's top gainers and losers. This is the composite
tool — five endpoints behind a single call."*

### Prompt 3 — Token due diligence (60s)

Call `token_due_diligence` with any real DEX token contract address, e.g.
one copied from a token's CoinMarketCap page:

```json
{ "platform": "ethereum", "address": "<token contract address>" }
```

Say: *"Token detail, security checks, liquidity pools and price in one
call — the due-diligence workflow an agent would otherwise do in four
round trips."*

Note: in keyless mode the DEX security sub-check can return
`CoinMarketCap error 400 for /v1/dex/security/detail: BAD_REQUEST`
(observed for USDC on Ethereum, 19 Nov 2026). The composite still
returns the token, pools and price; only the security section carries
the error. With a key the endpoint is expected to work — if you have
one, set `CMC_API_KEY` before recording.

## 3. What the recording must show

- The inspector's tool list (20 tools) — visible evidence the server runs.
- At least one tool call returning **real data** (a price with a real
  number, not a mock).
- The keyless setup: no key in the environment — point at the terminal
  showing the server started with no `CMC_API_KEY` set.

Keep the recording under 3 minutes and upload it unlisted or public;
paste the link into the DoraHacks submission form.
