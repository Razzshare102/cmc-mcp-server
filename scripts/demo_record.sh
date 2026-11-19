#!/usr/bin/env bash
# Recordable demo of the CMC MCP server via the MCP Inspector CLI.
# Runs the 3 prompts from DEMO.md against the REAL keyless CMC API and
# prints real data. No API key is used (keyless mode).
# Usage: bash scripts/demo_record.sh   (run inside a terminal being recorded)
# Env: CMC_MCP_PYTHON (default: /home/hatch/workspace/cmc-mcp-venv/bin/python)
#      HTTPS_PROXY / SSL_CERT_FILE are passed through to the inspector.

set -u
cd "$(dirname "$0")/.."

PY="${CMC_MCP_PYTHON:-/home/hatch/workspace/cmc-mcp-venv/bin/python}"
export FASTMCP_CHECK_FOR_UPDATES=off

INSP=(npx --yes @modelcontextprotocol/inspector --cli
  -e "HTTPS_PROXY=$HTTPS_PROXY" -e "SSL_CERT_FILE=$SSL_CERT_FILE"
  -e FASTMCP_CHECK_FOR_UPDATES=off
  "$PY" -m cmc_mcp.server)

banner() { echo; echo "================================================================"; echo "$1"; echo "================================================================"; echo; }
say() { echo; echo ">>> $1"; echo; }

# Retry a tool call up to 3 times until the result has no error.
# $1 = step label, $2 = success marker (grep pattern), rest = inspector args
run_step() {
  local label="$1" marker="$2"; shift 2
  local out="/tmp/cmc-demo-$(echo "$label" | tr ' ' '_').txt"
  local i
  for i in 1 2 3; do
    say "$label (attempt $i)"
    # stdin from /dev/null: the inspector + MCP server must never touch the
    # recording terminal (it queries terminal attributes and can freeze the
    # display). Tool calls need no stdin.
    # setsid: detach from the controlling terminal entirely, so the
    # inspector cannot open /dev/tty or switch screen buffers.
    setsid "${INSP[@]}" "$@" < /dev/null > "$out" 2>&1
    if grep -q "$marker" "$out" && ! grep -q '"isError": true' "$out"; then
      # Show the first 50 lines only: some calls return very long JSON
      # and a wall of scrolling text hides the result on video.
      head -50 "$out"
      local lines
      lines=$(wc -l < "$out")
      echo "... (showing 50 of $lines lines — full live output verified)"
      return 0
    fi
    echo "--- attempt $i did not return live data, retrying... ---"
    sleep 5
  done
  echo "--- $label: still no live data after 3 attempts (showing last output) ---"
  head -20 "$out"
  return 1
}

clear
banner "CMC PULSE MCP  --  LIVE DEMO (no API key)"
echo "Server : cmc-mcp-server  (stdio, FastMCP)"
echo "API    : CoinMarketCap keyless public API"
echo "Key    : CMC_API_KEY=${CMC_API_KEY:-<not set>}"
echo "Repo   : github.com/Razzshare102/cmc-mcp-server"
sleep 4

banner "1) THE SERVER LISTS 20 TOOLS"
setsid "${INSP[@]}" --method tools/list < /dev/null 2>&1 | grep '"name"' | sed 's/^ *//'
echo
echo "20 tools: prices, quotes, listings, global metrics, Fear & Greed,"
echo "CMC100, Altcoin Season, DEX data, K-line candles + 4 composite tools."
sleep 4

banner "2) LIVE PRICES — get_price BTC, ETH, SOL"
run_step "get_price" '"price":' --method tools/call --tool-name get_price \
  --tool-arg symbols=BTC,ETH,SOL --tool-arg convert=USD
sleep 4

banner "3) MARKET BRIEF — one call, whole market"
run_step "market_brief" '"isError": false' --method tools/call \
  --tool-name market_brief
python3 - <<'EOF' 2>/dev/null || true
import re
raw = open('/tmp/cmc-demo-market_brief.txt').read()
for label, pat in [
    ('total_market_cap_usd', r'"total_market_cap_usd":\s*([0-9.]+)'),
    ('btc_dominance_pct', r'"btc_dominance_pct":\s*([0-9.]+)'),
    ('fear_greed', r'"fear_greed":\{[^}]*"entries":\[\{"value":(\d+)'),
    ('cmc100', r'"cmc100":\{[^}]*"value":([0-9.]+)'),
    ('altcoin_season', r'"altcoin_season":\{[^}]*"index":(\d+)'),
]:
    m = re.search(pat, raw)
    if m:
        print(f"  {label}: {m.group(1)}")
EOF
sleep 4

banner "4) TOKEN DUE DILIGENCE — USDC on Ethereum (one call)"
run_step "token_due_diligence" 'USD Coin' --method tools/call \
  --tool-name token_due_diligence --tool-arg platform=ethereum \
  --tool-arg address=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
sleep 4

banner "DONE — github.com/Razzshare102/cmc-mcp-server"
echo "Keyless-first: no API key needed to start."
echo "Add CMC_API_KEY for higher limits + the full catalog."
sleep 3
