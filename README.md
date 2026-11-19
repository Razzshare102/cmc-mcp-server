# CMC MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that puts
live [CoinMarketCap](https://coinmarketcap.com/api/) data in front of any
LLM — **no API key required to start**.

Built for the **Build with CMC: API Hackathon Round 2** (DoraHacks,
AI Agents and Automation track).

## Why this is different from CMC's official MCP

CoinMarketCap ships an official hosted MCP server. It is useful, but:

| | Official CMC MCP | This server |
|---|---|---|
| API key | **Required** — you must create an account and key first | **Keyless-first** — works with zero setup via CMC's public keyless endpoint |
| Tools | 12 plain one-endpoint tools | **20 tools**, including 4 composite one-call workflows |
| Hosting | Hosted by CMC (remote) | **Local, self-hosted stdio** — runs on your machine, your data stays yours |
| Agent workflows | One tool call per question | `market_brief`, `token_due_diligence`, `compare_coins`, `find_movers` answer a whole question in one call |

The composite tools are the point: an agent asking "how is the market today?"
should not need five round trips. `market_brief` does global metrics, Fear &
Greed, CMC100, Altcoin Season and the top 5 gainers/losers in a single call.

## Honest limits (keyless mode)

The keyless endpoint runs on a shared anonymous pool. When the pool is
exhausted, CMC returns **error 1022** ("You've reached the limit for
anonymous access"). This server retries those calls with exponential backoff
(1s / 2s / 4s / 8s) and, if the limit persists, tells you so plainly.

A **free API key removes the limit** and unlocks the full catalog — including
`get_trending_gainers_losers`, which is keyed-only and fails gracefully in
keyless mode. Get one at <https://coinmarketcap.com/api/> and set
`CMC_API_KEY`. Never commit a key to a repo.

Live smoke test (2026-11-19, keyless, from a shared host): 3/3 calls
succeeded — BTC $63,680.62, Fear & Greed 12 ("Extreme fear"), total market
cap $2.175T, BTC dominance 58.9%.

## Tools

Every tool names the CMC endpoint it calls.

| Tool | CMC endpoint | Mode |
|---|---|---|
| `get_price` | `/v2/simple/price` | keyless |
| `get_quotes` | `/v3/cryptocurrency/quotes/latest` | keyless |
| `list_top_cryptos` | `/v3/cryptocurrency/listings/latest` | keyless |
| `get_coin_info` | `/v2/cryptocurrency/info` | keyless |
| `get_global_metrics` | `/v1/global-metrics/quotes/latest` | keyless |
| `get_fear_greed` | `/v3/fear-and-greed/latest` (+ `/v3/fear-and-greed/historical`) | keyless |
| `get_cmc100` | `/v3/index/cmc100-latest` | keyless |
| `get_altcoin_season` | `/v1/altcoin-season-index/latest` | keyless |
| `convert_price` | `/v2/tools/price-conversion` | keyless |
| `search_dex_token` | `/v1/dex/search` | keyless |
| `get_dex_token` | `/v1/dex/token` | keyless |
| `get_dex_token_security` | `/v1/dex/security/detail` | keyless |
| `get_dex_pools` | `/v1/dex/token/pools` | keyless |
| `get_dex_pair_quotes` | `/v4/dex/pairs/quotes/latest` | keyless |
| `get_kline_candles` | `/v1/k-line/candles` | keyless |
| `get_trending_gainers_losers` | `/v1/cryptocurrency/trending/gainers-losers` | **keyed only** |
| `market_brief` | global metrics + fear/greed + CMC100 + altcoin season + listings | keyless |
| `token_due_diligence` | dex token + security + pools + price | keyless |
| `compare_coins` | `/v3/cryptocurrency/quotes/latest` (2–5 symbols) | keyless |
| `find_movers` | `/v3/cryptocurrency/listings/latest` sorted by `percent_change_24h` | keyless |

Note: `find_movers` deliberately does **not** use
`/v1/cryptocurrency/trending/gainers-losers` — that endpoint is keyed-only.
It derives gainers/losers from the keyless listings endpoint instead.

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/<you>/cmc-mcp-server.git
cd cmc-mcp-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Keyless mode needs nothing else. For keyed mode:

```bash
export CMC_API_KEY="your-free-key"   # never commit this
```

Run the server (stdio transport):

```bash
FASTMCP_CHECK_FOR_UPDATES=off python -m cmc_mcp.server
```

`FASTMCP_CHECK_FOR_UPDATES=off` skips FastMCP's startup version check, which
fails on proxied/sandbox networks.

### Claude Code

```bash
claude mcp add cmc -- python -m cmc_mcp.server
```

Or add to `~/.claude.json` / `.mcp.json`:

```json
{
  "mcpServers": {
    "cmc": {
      "command": "python",
      "args": ["-m", "cmc_mcp.server"],
      "cwd": "/path/to/cmc-mcp-server",
      "env": {
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "CMC_API_KEY": "your-free-key"
      }
    }
  }
}
```

Omit `CMC_API_KEY` entirely for keyless mode.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cmc": {
      "command": "/path/to/cmc-mcp-server/.venv/bin/python",
      "args": ["-m", "cmc_mcp.server"],
      "cwd": "/path/to/cmc-mcp-server",
      "env": { "FASTMCP_CHECK_FOR_UPDATES": "off" }
    }
  }
}
```

### Codex

```bash
codex mcp add cmc -- python -m cmc_mcp.server
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.cmc]
command = "python"
args = ["-m", "cmc_mcp.server"]
cwd = "/path/to/cmc-mcp-server"
```

## Example session

> **You:** What's the Bitcoin price, and how is the market doing overall?
>
> **Agent** → `get_price(symbols="BTC")`
> → `{ "prices": { "BTC": { "price": 63680.62, ... } } }`
>
> **Agent** → `market_brief()`
> → total market cap $2.175T, 24h volume $72.4B, BTC dominance 58.9%,
> Fear & Greed 12 ("Extreme fear"), plus the CMC100 value, Altcoin Season
> Index and the day's top gainers/losers.
>
> **Agent:** Bitcoin is at **$63,680.62**. The market is in **extreme fear**
> (12/100) with a $2.18T total cap; BTC dominance is 58.9%.

## Demo

See [DEMO.md](DEMO.md) for the exact MCP Inspector command and three
scripted demo prompts (price check → market brief → token due diligence).

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

20 tests, all mocked (no network): keyless vs keyed base URL and header,
exponential backoff on error 1022 (then success), graceful keyed-only error,
and the aggregation logic of every composite tool.

Live smoke test against the real keyless API:

```bash
python scripts/smoke_live.py
```

Verify the server lists all 20 tools over stdio:

```bash
python scripts/verify_tools.py
```

## What the API made possible / where it got in the way

- The keyless catalog is generous: prices, quotes, listings, global metrics,
  Fear & Greed, CMC100, altcoin season and the whole DEX surface all work
  with no account — that is what makes a zero-setup MCP server possible.
- The anonymous pool is shared and often exhausted (error 1022); the server
  retries with backoff, but a free key is the real fix for sustained use.
- CMC is inconsistent about `error_code`'s type: some endpoints return the
  integer `0`, others the string `"0"`; the client normalises both. The
  `/v2/simple/price` response also ships `data` as a list with a `quotes`
  array rather than a symbol-keyed map — the server handles both shapes.
- `listings/latest` and `quotes/latest` return `quote` as a **list**, not a
  dict, and `quotes/latest` with several symbols returns *every* token
  sharing a symbol (wrapped variants, other chains — some with null prices).
  The server keeps the largest-market-cap entry per symbol.
- `trending/gainers-losers` is keyed-only, so the keyless `find_movers`
  derives movers from listings instead — same answer, one extra sort.
  Even with a key the endpoint is plan-gated: a free Basic key is refused
  with error 1006 ("plan doesn't support this endpoint", verified
  19 Nov 2026), so `find_movers` stays the reliable fallback until the
  plan is upgraded — the hackathon Startup tier should unlock it.

## License

MIT — see [LICENSE](LICENSE).
