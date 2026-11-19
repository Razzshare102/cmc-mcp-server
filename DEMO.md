# Demo — CMC MCP Server

Record a 2–3 minute screen recording of the server working, for the
DoraHacks submission. No API key is needed for this demo (keyless mode).

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

## 3. What the recording must show

- The inspector's tool list (20 tools) — visible evidence the server runs.
- At least one tool call returning **real data** (a price with a real
  number, not a mock).
- The keyless setup: no key in the environment — point at the terminal
  showing the server started with no `CMC_API_KEY` set.

Keep the recording under 3 minutes and upload it unlisted or public;
paste the link into the DoraHacks submission form.
