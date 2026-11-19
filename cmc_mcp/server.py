"""CoinMarketCap MCP server (keyless-first).

Run with stdio transport (the default)::

    FASTMCP_CHECK_FOR_UPDATES=off python -m cmc_mcp.server

Keyless mode (default, no API key) uses the public CoinMarketCap
endpoint; setting ``CMC_API_KEY`` switches to keyed mode with higher
limits and unlocks the full catalog, including trending gainers/losers.
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import tools_impl as t
from .client import CMCClient

mcp = FastMCP("cmc-mcp-server")

_CLIENT: CMCClient | None = None


def _client() -> CMCClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = CMCClient()
    return _CLIENT


# -- Keyless tools ---------------------------------------------------------------


@mcp.tool
async def get_price(symbols: str, convert: str = "USD") -> dict:
    """Get the current price of one or more cryptocurrencies.

    CMC endpoint: /v2/simple/price. Keyless.
    Example: symbols="BTC,ETH", convert="USD".
    """
    return await t.get_price(_client(), symbols, convert)


@mcp.tool
async def get_quotes(symbols: str = "", ids: str = "", convert: str = "USD") -> dict:
    """Get full quotes (price, market cap, volume, % changes) for coins.

    CMC endpoint: /v3/cryptocurrency/quotes/latest. Keyless.
    Provide symbols (e.g. "BTC,ETH") or CMC ids (e.g. "1,1027").
    """
    return await t.get_quotes(_client(), symbols, ids, convert)


@mcp.tool
async def list_top_cryptos(limit: int = 20, sort: str = "market_cap", convert: str = "USD") -> dict:
    """List top cryptocurrencies, ranked by market cap, volume or % change.

    CMC endpoint: /v3/cryptocurrency/listings/latest. Keyless.
    sort can be market_cap, volume_24h, percent_change_24h, percent_change_7d, ...
    """
    return await t.list_top_cryptos(_client(), limit, sort, convert)


@mcp.tool
async def get_coin_info(symbols: str = "", ids: str = "") -> dict:
    """Get metadata (description, links, logo, category) for coins.

    CMC endpoint: /v2/cryptocurrency/info. Keyless.
    Provide symbols (e.g. "BTC") or CMC ids.
    """
    return await t.get_coin_info(_client(), symbols, ids)


@mcp.tool
async def get_global_metrics(convert: str = "USD") -> dict:
    """Get total crypto market cap, 24h volume, BTC/ETH dominance.

    CMC endpoint: /v1/global-metrics/quotes/latest. Keyless.
    """
    return await t.get_global_metrics(_client(), convert)


@mcp.tool
async def get_fear_greed(limit: int = 1, historical: bool = False) -> dict:
    """Get the Crypto Fear & Greed index (latest, or historical values).

    CMC endpoints: /v3/fear-and-greed/latest and
    /v3/fear-and-greed/historical. Keyless.
    """
    return await t.get_fear_greed(_client(), limit, historical)


@mcp.tool
async def get_cmc100() -> dict:
    """Get the CMC100 index value (top 100 coins, market-cap weighted).

    CMC endpoint: /v3/index/cmc100-latest. Keyless.
    """
    return await t.get_cmc100(_client())


@mcp.tool
async def get_altcoin_season() -> dict:
    """Get the Altcoin Season Index (0-100; >75 = altcoin season).

    CMC endpoint: /v1/altcoin-season-index/latest. Keyless.
    """
    return await t.get_altcoin_season(_client())


@mcp.tool
async def convert_price(amount: float, symbol: str = "BTC", convert: str = "USD") -> dict:
    """Convert an amount of one asset into another currency or crypto.

    CMC endpoint: /v2/tools/price-conversion. Keyless.
    Example: amount=0.5, symbol="BTC", convert="ETH".
    """
    return await t.convert_price(_client(), amount, symbol, convert)


@mcp.tool
async def search_dex_token(query: str) -> dict:
    """Search DEX tokens and pairs by name, symbol or address fragment.

    CMC endpoint: /v1/dex/search. Keyless.
    """
    return await t.search_dex_token(_client(), query)


@mcp.tool
async def get_dex_token(platform: str, address: str) -> dict:
    """Get DEX token detail for a contract address on a platform/chain.

    CMC endpoint: /v1/dex/token. Keyless.
    Example: platform="ethereum", address="0x...".
    """
    return await t.get_dex_token(_client(), platform, address)


@mcp.tool
async def get_dex_token_security(platform: str, address: str) -> dict:
    """Get security/audit detail for a DEX token (honeypot, mint, taxes...).

    CMC endpoint: /v1/dex/security/detail. Keyless.
    """
    return await t.get_dex_token_security(_client(), platform, address)


@mcp.tool
async def get_dex_pools(platform: str, address: str) -> dict:
    """Get liquidity pools for a DEX token.

    CMC endpoint: /v1/dex/token/pools. Keyless.
    """
    return await t.get_dex_pools(_client(), platform, address)


@mcp.tool
async def get_dex_pair_quotes(network_id: int, contract_address: str) -> dict:
    """Get quotes for DEX pairs on a network.

    CMC endpoint: /v4/dex/pairs/quotes/latest. Keyless.
    Example: network_id=1 (Ethereum), contract_address="0x...".
    """
    return await t.get_dex_pair_quotes(_client(), network_id, contract_address)


@mcp.tool
async def get_kline_candles(platform: str, address: str, interval: str = "1d") -> dict:
    """Get OHLCV candles for a DEX token.

    CMC endpoint: /v1/k-line/candles. Keyless.
    interval examples: "15m", "1h", "4h", "1d", "1w".
    """
    return await t.get_kline_candles(_client(), platform, address, interval)


# -- Keyed-only tool ---------------------------------------------------------------


@mcp.tool
async def get_trending_gainers_losers(
    start: int = 1, limit: int = 10, convert: str = "USD", sort_dir: str = "desc"
) -> dict:
    """Get trending gainers and losers.

    CMC endpoint: /v1/cryptocurrency/trending/gainers-losers. KEYED ONLY —
    in keyless mode this returns a clear error explaining a free API key
    unlocks it. Use find_movers for the keyless equivalent.
    """
    return await t.get_trending_gainers_losers(_client(), start, limit, convert, sort_dir)


# -- Composite tools (one-call agent workflows) -----------------------------------


@mcp.tool
async def market_brief() -> dict:
    """One-call market brief: global metrics + Fear & Greed + CMC100 +
    Altcoin Season Index + top 5 gainers/losers of the last 24h.

    CMC endpoints: /v1/global-metrics/quotes/latest,
    /v3/fear-and-greed/latest, /v3/index/cmc100-latest,
    /v1/altcoin-season-index/latest, /v3/cryptocurrency/listings/latest.
    Keyless.
    """
    return await t.market_brief(_client())


@mcp.tool
async def token_due_diligence(platform: str, address: str) -> dict:
    """One-call due diligence for a DEX token: token detail + security
    checks + liquidity pools + current price.

    CMC endpoints: /v1/dex/token, /v1/dex/security/detail,
    /v1/dex/token/pools, /v2/simple/price. Keyless.
    """
    return await t.token_due_diligence(_client(), platform, address)


@mcp.tool
async def compare_coins(symbols: str) -> dict:
    """Side-by-side quotes for 2-5 coins, with the best 24h performer.

    CMC endpoint: /v3/cryptocurrency/quotes/latest. Keyless.
    Example: symbols="BTC,ETH,SOL".
    """
    return await t.compare_coins(_client(), symbols)


@mcp.tool
async def find_movers(direction: str = "gainers", limit: int = 10) -> dict:
    """Find today's biggest gainers or losers (top 100 by 24h % change).

    CMC endpoint: /v3/cryptocurrency/listings/latest sorted by
    percent_change_24h. Keyless. (The trending gainers/losers endpoint
    is keyed-only; this is the keyless equivalent.)
    """
    return await t.find_movers(_client(), direction, limit)


def main() -> None:
    """Run the MCP server over stdio (default transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
