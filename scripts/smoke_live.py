"""Live smoke test against the REAL CoinMarketCap keyless API.

Usage:
    FASTMCP_CHECK_FOR_UPDATES=off python scripts/smoke_live.py

Calls get_price (BTC), get_fear_greed and get_global_metrics with the
client's exponential backoff and prints real values. The shared-IP
anonymous pool is often exhausted, so individual calls may fail with
error 1022 — that outcome is reported, not hidden.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cmc_mcp import tools_impl as t  # noqa: E402
from cmc_mcp.client import CMCClient, CMCError  # noqa: E402


async def main() -> int:
    client = CMCClient()  # keyless unless CMC_API_KEY is set
    print(f"mode: {client.mode} (base: {client.base_url})")
    results = {}

    checks = [
        ("get_price BTC", lambda: t.get_price(client, "BTC")),
        ("get_fear_greed", lambda: t.get_fear_greed(client)),
        ("get_global_metrics", lambda: t.get_global_metrics(client)),
    ]
    for name, factory in checks:
        try:
            value = await factory()
            results[name] = {"ok": True, "value": value}
            print(f"\n### {name}: OK")
            print(json.dumps(value, indent=2)[:1500])
        except CMCError as exc:
            results[name] = {"ok": False, "error": str(exc)}
            print(f"\n### {name}: FAILED — {exc}")

    await client.close()
    ok = sum(1 for r in results.values() if r["ok"])
    print(f"\nSMOKE: {ok}/{len(results)} live calls succeeded")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
