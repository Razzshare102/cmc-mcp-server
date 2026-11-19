"""Verify the MCP server over stdio: initialize + tools/list via JSON-RPC.

Usage:
    FASTMCP_CHECK_FOR_UPDATES=off python scripts/verify_tools.py

Starts the server as a subprocess over stdio using the MCP Python SDK
client and prints every tool name. Exits non-zero if the count is not 20.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXPECTED_TOOLS = {
    "get_price",
    "get_quotes",
    "list_top_cryptos",
    "get_coin_info",
    "get_global_metrics",
    "get_fear_greed",
    "get_cmc100",
    "get_altcoin_season",
    "convert_price",
    "search_dex_token",
    "get_dex_token",
    "get_dex_token_security",
    "get_dex_pools",
    "get_dex_pair_quotes",
    "get_kline_candles",
    "get_trending_gainers_losers",
    "market_brief",
    "token_due_diligence",
    "compare_coins",
    "find_movers",
}


async def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    venv_python = Path.home() / "workspace" / "cmc-mcp-venv" / "bin" / "python"
    env = dict(os.environ)
    env["FASTMCP_CHECK_FOR_UPDATES"] = "off"
    params = StdioServerParameters(
        command=str(venv_python),
        args=["-m", "cmc_mcp.server"],
        env=env,
        cwd=str(repo),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            names = sorted(tool.name for tool in result.tools)
            print(f"tools/list returned {len(names)} tools:")
            for name in names:
                print(f"  - {name}")
            missing = EXPECTED_TOOLS - set(names)
            extra = set(names) - EXPECTED_TOOLS
            if missing:
                print(f"MISSING: {sorted(missing)}")
            if extra:
                print(f"UNEXPECTED: {sorted(extra)}")
            if len(names) == 20 and not missing and not extra:
                print("VERIFY: OK — all 20 expected tools listed")
                return 0
            print("VERIFY: FAILED")
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
