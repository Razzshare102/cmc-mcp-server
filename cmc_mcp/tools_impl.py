"""Tool implementations for the CMC MCP server.

Each function is a plain async function taking a :class:`CMCClient` so
tests can exercise the logic directly; :mod:`cmc_mcp.server` wraps them
as FastMCP tools. Every docstring names the CMC endpoint it calls.
"""

from __future__ import annotations

import asyncio

from .client import CMCClient, CMCError

VALID_LISTING_SORTS = {
    "market_cap",
    "market_cap_strict",
    "name",
    "price",
    "circulating_supply",
    "total_supply",
    "max_supply",
    "num_market_pairs",
    "volume_24h",
    "percent_change_1h",
    "percent_change_24h",
    "percent_change_7d",
    "market_cap_by_total_supply_strict",
    "volume_7d",
    "volume_30d",
}


def _usd_quote(item: dict) -> dict:
    """Extract the USD quote from a coin entry.

    CMC is inconsistent: most endpoints return ``quote`` as a dict
    (``{"USD": {...}}``), but listings/latest returns it as a LIST
    (``[{"symbol": "USD", ...}]``). Handle both.
    """
    quote = item.get("quote")
    if isinstance(quote, dict):
        return quote.get("USD") or {}
    if isinstance(quote, list):
        return next(
            (q for q in quote if q.get("symbol") == "USD"),
            quote[0] if quote else {},
        )
    return {}


def _quote_summary(quote: dict) -> dict:
    """Compact per-coin summary from a quotes/latest entry."""
    usd = _usd_quote(quote)
    return {
        "id": quote.get("id"),
        "name": quote.get("name"),
        "symbol": quote.get("symbol"),
        "rank": quote.get("cmc_rank"),
        "price_usd": usd.get("price"),
        "market_cap_usd": usd.get("market_cap"),
        "volume_24h_usd": usd.get("volume_24h"),
        "percent_change_1h": usd.get("percent_change_1h"),
        "percent_change_24h": usd.get("percent_change_24h"),
        "percent_change_7d": usd.get("percent_change_7d"),
        "last_updated": usd.get("last_updated"),
    }


def _listing_summary(item: dict) -> dict:
    usd = _usd_quote(item)
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "symbol": item.get("symbol"),
        "rank": item.get("cmc_rank"),
        "price_usd": usd.get("price"),
        "market_cap_usd": usd.get("market_cap"),
        "volume_24h_usd": usd.get("volume_24h"),
        "percent_change_24h": usd.get("percent_change_24h"),
        "percent_change_7d": usd.get("percent_change_7d"),
    }


def _real_movers(coins: list) -> list:
    """Coins with a real % change and a non-zero market cap.

    Listings sorted by percent_change_24h surface micro-caps with
    market_cap 0 and +thousands-% moves first; those are noise, not movers.
    """
    return [
        c
        for c in coins
        if c.get("percent_change_24h") is not None
        and (c.get("market_cap_usd") or 0) > 0
    ]


# -- Keyless tools ---------------------------------------------------------------

async def get_price(client: CMCClient, symbols: str, convert: str = "USD") -> dict:
    """CMC endpoint: /v2/simple/price — simple price for symbols."""
    data = await client.simple_price(symbols, convert)
    # /v2/simple/price returns data as a LIST of coins, each with a
    # "quotes" array (one entry per convert currency).
    if isinstance(data, list):
        items = data
    else:
        items = [
            {"symbol": sym, "quote": entry.get("quote", {})}
            for sym, entry in data.items()
        ]
    out = {}
    for item in items:
        symbol = item.get("symbol")
        quotes = item.get("quotes")
        quote: dict = {}
        if isinstance(quotes, list) and quotes:
            quote = next(
                (q for q in quotes if q.get("symbol") == convert),
                quotes[0],
            )
        elif isinstance(quotes, dict):
            quote = quotes.get(convert) or quotes.get("USD") or {}
        elif isinstance(item.get("quote"), dict):
            quote = item["quote"].get(convert) or item["quote"].get("USD") or {}
        out[symbol] = {
            "price": quote.get("price"),
            "percent_change_24h": quote.get("percent_change_24h"),
            "last_updated": quote.get("last_updated"),
        }
    return {"mode": client.mode, "convert": convert, "prices": out}


def _quote_rank(summary: dict) -> tuple:
    """Rank a quote summary for same-symbol deduplication: a real price
    first, then the largest market cap."""
    price_ok = 1 if summary.get("price_usd") is not None else 0
    return (price_ok, summary.get("market_cap_usd") or 0)


async def get_quotes(
    client: CMCClient, symbols: str = "", ids: str = "", convert: str = "USD"
) -> dict:
    """CMC endpoint: /v3/cryptocurrency/quotes/latest — full quotes."""
    data = await client.quotes_latest(symbols or None, ids or None, convert)
    coins = data if isinstance(data, list) else list(data.values())
    summaries = [_quote_summary(c) for c in coins]
    if not ids:
        # The keyless endpoint returns EVERY token sharing a symbol
        # (wrapped variants, other chains — some with null prices).
        # Keep the most significant one per symbol.
        best: dict[str, dict] = {}
        for summary in summaries:
            symbol = summary.get("symbol")
            if not symbol:
                continue
            current = best.get(symbol)
            if current is None or _quote_rank(summary) > _quote_rank(current):
                best[symbol] = summary
        summaries = list(best.values())
    return {"mode": client.mode, "quotes": summaries}


async def list_top_cryptos(
    client: CMCClient, limit: int = 20, sort: str = "market_cap", convert: str = "USD",
    sort_dir: str = "desc",
) -> dict:
    """CMC endpoint: /v3/cryptocurrency/listings/latest — ranked listings."""
    if sort not in VALID_LISTING_SORTS:
        raise ValueError(
            f"Unknown sort '{sort}'. Valid: {', '.join(sorted(VALID_LISTING_SORTS))}"
        )
    data = await client.listings_latest(limit=limit, sort=sort, convert=convert, sort_dir=sort_dir)
    return {"mode": client.mode, "sort": sort, "coins": [_listing_summary(c) for c in data]}


async def get_coin_info(
    client: CMCClient, symbols: str = "", ids: str = ""
) -> dict:
    """CMC endpoint: /v2/cryptocurrency/info — coin metadata."""
    if not symbols and not ids:
        raise ValueError("Provide symbols or ids (e.g. symbols='BTC,ETH').")
    data = await client.coin_info(symbols or None, ids or None)
    coins = data if isinstance(data, list) else list(data.values())
    return {
        "mode": client.mode,
        "coins": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "symbol": c.get("symbol"),
                "category": c.get("category"),
                "description": (c.get("description") or "")[:500],
                "urls": c.get("urls"),
                "logo": c.get("logo"),
                "date_added": c.get("date_added"),
            }
            for c in coins
        ],
    }


async def get_global_metrics(client: CMCClient, convert: str = "USD") -> dict:
    """CMC endpoint: /v1/global-metrics/quotes/latest — market totals."""
    data = await client.global_metrics(convert)
    quote = _usd_quote(data)
    return {
        "mode": client.mode,
        "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        "total_market_cap_usd": quote.get("total_market_cap"),
        "total_volume_24h_usd": quote.get("total_volume_24h"),
        "btc_dominance_pct": data.get("btc_dominance"),
        "eth_dominance_pct": data.get("eth_dominance"),
        "last_updated": quote.get("last_updated"),
    }


async def get_fear_greed(
    client: CMCClient, limit: int = 1, historical: bool = False
) -> dict:
    """CMC endpoints: /v3/fear-and-greed/latest (+ /v3/fear-and-greed/historical)."""
    if historical:
        data = await client.fear_greed_historical(limit=limit)
    else:
        data = await client.fear_greed(limit=limit)
    entries = data if isinstance(data, list) else [data]
    return {
        "mode": client.mode,
        "entries": [
            {
                "value": e.get("value"),
                "value_classification": e.get("value_classification"),
                "timestamp": e.get("timestamp"),
            }
            for e in entries
        ],
    }


async def get_cmc100(client: CMCClient) -> dict:
    """CMC endpoint: /v3/index/cmc100-latest — CMC100 index."""
    data = await client.cmc100()
    return {
        "mode": client.mode,
        "value": data.get("value"),
        # Live field is value_24h_percentage_change; keep the doc name too.
        "percent_change_24h": data.get("value_24h_percentage_change", data.get("percent_change_24h")),
        "last_updated": data.get("last_update", data.get("last_updated")),
    }


async def get_altcoin_season(client: CMCClient) -> dict:
    """CMC endpoint: /v1/altcoin-season-index/latest — Altcoin Season Index."""
    data = await client.altcoin_season()
    return {
        "mode": client.mode,
        # Live fields are altcoin_index / snapshot_time.
        "index": data.get("altcoin_index", data.get("index")),
        "timestamp": data.get("snapshot_time", data.get("timestamp")),
    }


async def convert_price(
    client: CMCClient, amount: float, symbol: str = "BTC", convert: str = "USD"
) -> dict:
    """CMC endpoint: /v2/tools/price-conversion — convert amounts."""
    data = await client.price_conversion(amount, symbol=symbol, convert=convert)
    quote = (data.get("quote") or {}).get(convert) or {}
    return {
        "mode": client.mode,
        "from": {"amount": amount, "symbol": symbol},
        "to": {"amount": quote.get("price"), "currency": convert},
        "last_updated": quote.get("last_updated"),
    }


async def search_dex_token(client: CMCClient, query: str) -> dict:
    """CMC endpoint: /v1/dex/search — search DEX tokens/pairs."""
    data = await client.dex_search(query)
    return {"mode": client.mode, "results": data}


async def get_dex_token(client: CMCClient, platform: str, address: str) -> dict:
    """CMC endpoint: /v1/dex/token — DEX token detail."""
    data = await client.dex_token(platform, address)
    return {"mode": client.mode, "token": data}


async def get_dex_token_security(client: CMCClient, platform: str, address: str) -> dict:
    """CMC endpoint: /v1/dex/security/detail — DEX token security detail."""
    data = await client.dex_security(platform, address)
    return {"mode": client.mode, "security": data}


async def get_dex_pools(client: CMCClient, platform: str, address: str) -> dict:
    """CMC endpoint: /v1/dex/token/pools — liquidity pools for a DEX token."""
    data = await client.dex_pools(platform, address)
    return {"mode": client.mode, "pools": data}


async def get_dex_pair_quotes(
    client: CMCClient, network_id: int, contract_address: str
) -> dict:
    """CMC endpoint: /v4/dex/pairs/quotes/latest — DEX pair quotes."""
    data = await client.dex_pair_quotes(network_id, contract_address)
    return {"mode": client.mode, "pairs": data}


async def get_kline_candles(
    client: CMCClient, platform: str, address: str, interval: str = "1d"
) -> dict:
    """CMC endpoint: /v1/k-line/candles — OHLCV candles for a DEX token."""
    data = await client.kline_candles(platform, address, interval)
    return {"mode": client.mode, "interval": interval, "candles": data}


# -- Keyed-only tool ---------------------------------------------------------------

async def get_trending_gainers_losers(
    client: CMCClient,
    start: int = 1,
    limit: int = 10,
    convert: str = "USD",
    sort_dir: str = "desc",
) -> dict:
    """CMC endpoint: /v1/cryptocurrency/trending/gainers-losers (KEYED ONLY).

    Fails gracefully in keyless mode — see CMCClient.trending_gainers_losers.
    """
    data = await client.trending_gainers_losers(start, limit, convert, sort_dir)
    return {"mode": client.mode, "trending": data}


# -- Composite tools (the differentiator) ------------------------------------------

async def _safe(coro):
    """Run a coroutine, returning {'_error': str} instead of raising."""
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001 — briefs degrade gracefully
        return {"_error": str(exc)}


async def market_brief(client: CMCClient) -> dict:
    """Composite (one call): global metrics + fear/greed + CMC100 +
    altcoin season + top 5 gainers/losers from listings sorted by
    percent_change_24h.

    CMC endpoints: /v1/global-metrics/quotes/latest,
    /v3/fear-and-greed/latest, /v3/index/cmc100-latest,
    /v1/altcoin-season-index/latest, /v3/cryptocurrency/listings/latest.
    """
    metrics, fear, cmc100, season, listings_desc, listings_asc = await asyncio.gather(
        _safe(get_global_metrics(client)),
        _safe(get_fear_greed(client)),
        _safe(get_cmc100(client)),
        _safe(get_altcoin_season(client)),
        _safe(list_top_cryptos(client, limit=100, sort="percent_change_24h", sort_dir="desc")),
        _safe(list_top_cryptos(client, limit=100, sort="percent_change_24h", sort_dir="asc")),
    )
    gainers: list = []
    losers: list = []
    if isinstance(listings_desc, dict) and listings_desc.get("coins"):
        gainers = sorted(
            _real_movers(listings_desc["coins"]),
            key=lambda c: c["percent_change_24h"],
            reverse=True,
        )[:5]
    if isinstance(listings_asc, dict) and listings_asc.get("coins"):
        losers = sorted(
            _real_movers(listings_asc["coins"]),
            key=lambda c: c["percent_change_24h"],
        )[:5]
    return {
        "mode": client.mode,
        "global_metrics": metrics,
        "fear_greed": fear,
        "cmc100": cmc100,
        "altcoin_season": season,
        "top_gainers_24h": gainers,
        "top_losers_24h": losers,
    }


async def token_due_diligence(
    client: CMCClient, platform: str, address: str
) -> dict:
    """Composite (one call): DEX token detail + security + pools + price.

    CMC endpoints: /v1/dex/token, /v1/dex/security/detail,
    /v1/dex/token/pools, /v2/simple/price.
    """
    token = await _safe(get_dex_token(client, platform, address))
    security, pools = await asyncio.gather(
        _safe(get_dex_token_security(client, platform, address)),
        _safe(get_dex_pools(client, platform, address)),
    )
    price: dict | None = None
    symbol = None
    if isinstance(token, dict):
        inner = token.get("token") or {}
        symbol = inner.get("symbol") or inner.get("base_symbol")
    if symbol:
        price = await _safe(get_price(client, symbol))
    return {
        "mode": client.mode,
        "platform": platform,
        "address": address,
        "token": token,
        "security": security,
        "pools": pools,
        "price": price,
    }


async def compare_coins(client: CMCClient, symbols: str) -> dict:
    """Composite (one call): side-by-side quotes for 2-5 symbols.

    CMC endpoint: /v3/cryptocurrency/quotes/latest.
    """
    parts = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not 2 <= len(parts) <= 5:
        raise ValueError("compare_coins needs 2-5 symbols, e.g. 'BTC,ETH,SOL'.")
    quotes = await get_quotes(client, symbols=",".join(parts))
    coins = quotes["quotes"]
    by_symbol = {c["symbol"]: c for c in coins}
    ordered = [by_symbol[s] for s in parts if s in by_symbol]
    best_24h = max(ordered, key=lambda c: c.get("percent_change_24h") or 0) if ordered else None
    return {
        "mode": client.mode,
        "coins": ordered,
        "best_24h": (best_24h or {}).get("symbol"),
    }


async def find_movers(
    client: CMCClient, direction: str = "gainers", limit: int = 10
) -> dict:
    """Composite (one call): gainers/losers from listings sorted by
    percent_change_24h. (Does NOT use
    /v1/cryptocurrency/trending/gainers-losers — that endpoint is
    keyed-only.)

    CMC endpoint: /v3/cryptocurrency/listings/latest.
    """
    if direction not in ("gainers", "losers"):
        raise ValueError("direction must be 'gainers' or 'losers'.")
    # Gainers come from the desc sort, losers from the asc sort — a single
    # desc page contains no negative movers at all.
    sort_dir = "desc" if direction == "gainers" else "asc"
    listings = await list_top_cryptos(
        client, limit=100, sort="percent_change_24h", sort_dir=sort_dir
    )
    ranked = sorted(
        _real_movers(listings["coins"]),
        key=lambda c: c["percent_change_24h"],
        reverse=(direction == "gainers"),
    )
    picked = ranked[:limit]
    return {"mode": client.mode, "direction": direction, "movers": picked}
