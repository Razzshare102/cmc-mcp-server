"""Tests for composite tool aggregation logic (mocked HTTP)."""

import httpx
import pytest

from cmc_mcp import tools_impl as t
from cmc_mcp.client import CMCClient


def _ok(data):
    return {"status": {"error_code": 0}, "data": data}


def _listing(symbol, pct_24h, price=100.0):
    return {
        "id": hash(symbol) % 10000,
        "name": symbol,
        "symbol": symbol,
        "cmc_rank": 1,
        "quote": {
            "USD": {
                "price": price,
                "market_cap": 1_000_000,
                "volume_24h": 50_000,
                "percent_change_24h": pct_24h,
                "percent_change_7d": pct_24h * 2,
            }
        },
    }


def _quote(symbol, pct_24h):
    return {
        "id": 1,
        "name": symbol,
        "symbol": symbol,
        "cmc_rank": 1,
        "quote": {
            "USD": {
                "price": 100.0,
                "market_cap": 1_000_000,
                "volume_24h": 50_000,
                "percent_change_1h": 0.1,
                "percent_change_24h": pct_24h,
                "percent_change_7d": pct_24h * 2,
                "last_updated": "2026-11-19T00:00:00.000Z",
            }
        },
    }


def market_client():
    """Client whose listings return a known set of movers."""

    def handler(request):
        path = request.url.path
        if path.endswith("/v3/cryptocurrency/listings/latest"):
            coins = [
                _listing("AAA", 25.0),
                _listing("BBB", 12.5),
                _listing("CCC", 3.0),
                _listing("DDD", -2.0),
                _listing("EEE", -9.5),
                _listing("FFF", -18.0),
            ]
            return httpx.Response(200, json=_ok(coins))
        if path.endswith("/v1/global-metrics/quotes/latest"):
            return httpx.Response(
                200,
                json=_ok(
                    {
                        "active_cryptocurrencies": 10000,
                        "btc_dominance": 58.1,
                        "eth_dominance": 12.4,
                        "quote": {
                            "USD": {
                                "total_market_cap": 2_100_000_000_000,
                                "total_volume_24h": 80_000_000_000,
                                "last_updated": "2026-11-19T00:00:00.000Z",
                            }
                        },
                    }
                ),
            )
        if path.endswith("/v3/fear-and-greed/latest"):
            return httpx.Response(
                200,
                json=_ok([{"value": 24, "value_classification": "Fear", "timestamp": "2026-11-19"}]),
            )
        if path.endswith("/v3/index/cmc100-latest"):
            return httpx.Response(
                200,
                json=_ok({"value": 210.5, "percent_change_24h": -1.2, "last_updated": "2026-11-19"}),
            )
        if path.endswith("/v1/altcoin-season-index/latest"):
            return httpx.Response(200, json=_ok({"index": 31, "timestamp": "2026-11-19"}))
        raise AssertionError(f"unexpected path {path}")

    return CMCClient(transport=httpx.MockTransport(handler))


async def test_get_price_handles_list_shaped_response():
    """Live /v2/simple/price returns data as a list with a quotes array."""

    def handler(request):
        return httpx.Response(
            200,
            json=_ok(
                [
                    {
                        "id": 1,
                        "name": "Bitcoin",
                        "symbol": "BTC",
                        "quotes": [
                            {"symbol": "USD", "price": 63695.07, "last_updated": "2026-11-19"}
                        ],
                    }
                ]
            ),
        )

    client = CMCClient(transport=httpx.MockTransport(handler))
    result = await t.get_price(client, "BTC")
    assert result["prices"]["BTC"]["price"] == 63695.07
    await client.close()


async def test_listing_summary_handles_list_shaped_quote():
    """Live listings/latest returns quote as a list, not a dict."""

    def handler(request):
        return httpx.Response(
            200,
            json=_ok(
                [
                    {
                        "id": 1,
                        "name": "Bitcoin",
                        "symbol": "BTC",
                        "cmc_rank": 1,
                        "quote": [
                            {
                                "symbol": "USD",
                                "price": 63680.0,
                                "market_cap": 1_200_000_000_000,
                                "volume_24h": 30_000_000_000,
                                "percent_change_24h": -1.5,
                                "percent_change_7d": -3.0,
                            }
                        ],
                    }
                ]
            ),
        )

    client = CMCClient(transport=httpx.MockTransport(handler))
    result = await t.list_top_cryptos(client, limit=1)
    coin = result["coins"][0]
    assert coin["price_usd"] == 63680.0
    assert coin["percent_change_24h"] == -1.5
    await client.close()


async def test_altcoin_season_and_cmc100_live_field_names():
    def handler(request):
        path = request.url.path
        if path.endswith("/v1/altcoin-season-index/latest"):
            return httpx.Response(
                200,
                json=_ok(
                    {
                        "altcoin_index": 53,
                        "snapshot_time": "2026-11-19T13:18:36Z",
                        "altcoin_marketcap": 893900627748.62,
                    }
                ),
            )
        if path.endswith("/v3/index/cmc100-latest"):
            return httpx.Response(
                200,
                json=_ok(
                    {
                        "value": 124.49,
                        "value_24h_percentage_change": -0.10,
                        "last_update": "2026-11-19T13:20:00.000Z",
                    }
                ),
            )
        raise AssertionError(f"unexpected path {path}")

    client = CMCClient(transport=httpx.MockTransport(handler))
    season = await t.get_altcoin_season(client)
    assert season["index"] == 53
    assert season["timestamp"] == "2026-11-19T13:18:36Z"
    cmc100 = await t.get_cmc100(client)
    assert cmc100["value"] == 124.49
    assert cmc100["percent_change_24h"] == -0.10
    await client.close()


async def test_market_brief_derives_gainers_and_losers():
    client = market_client()
    brief = await t.market_brief(client)
    assert brief["mode"] == "keyless"
    assert [c["symbol"] for c in brief["top_gainers_24h"]] == ["AAA", "BBB", "CCC", "DDD", "EEE"]
    assert [c["symbol"] for c in brief["top_losers_24h"]] == ["FFF", "EEE", "DDD", "CCC", "BBB"]
    assert brief["global_metrics"]["btc_dominance_pct"] == 58.1
    assert brief["fear_greed"]["entries"][0]["value_classification"] == "Fear"
    assert brief["cmc100"]["value"] == 210.5
    assert brief["altcoin_season"]["index"] == 31
    await client.close()


async def test_find_movers_gainers_and_losers():
    client = market_client()
    gainers = await t.find_movers(client, direction="gainers", limit=2)
    assert [c["symbol"] for c in gainers["movers"]] == ["AAA", "BBB"]
    losers = await t.find_movers(client, direction="losers", limit=2)
    assert [c["symbol"] for c in losers["movers"]] == ["FFF", "EEE"]
    with pytest.raises(ValueError, match="direction"):
        await t.find_movers(client, direction="sideways")
    await client.close()


async def test_get_quotes_dedupes_same_symbol_variants():
    """Keyless quotes/latest returns every token sharing a symbol —
    keep the real one (largest market cap, non-null price)."""

    def handler(request):
        return httpx.Response(
            200,
            json=_ok(
                [
                    _quote("BTC", -0.5),  # real BTC (mock: mcap 1,000,000)
                    {
                        "id": 99999,
                        "name": "Bitcoin Dust",
                        "symbol": "BTC",
                        "cmc_rank": 9000,
                        "quote": {
                            "USD": {
                                "price": 0.0000025,
                                "market_cap": 100,
                                "volume_24h": 0,
                                "percent_change_1h": 0,
                                "percent_change_24h": 0.67,
                                "percent_change_7d": -7.5,
                                "last_updated": "2026-11-19T00:00:00.000Z",
                            }
                        },
                    },
                ]
            ),
        )

    client = CMCClient(transport=httpx.MockTransport(handler))
    result = await t.get_quotes(client, symbols="BTC")
    assert len(result["quotes"]) == 1
    assert result["quotes"][0]["price_usd"] == 100.0  # the real BTC, not dust
    await client.close()


async def test_compare_coins_picks_best_24h():
    def handler(request):
        path = request.url.path
        assert path.endswith("/v3/cryptocurrency/quotes/latest")
        return httpx.Response(
            200,
            json=_ok({"BTC": _quote("BTC", 1.5), "ETH": _quote("ETH", 4.2), "SOL": _quote("SOL", -0.5)}),
        )

    client = CMCClient(transport=httpx.MockTransport(handler))
    result = await t.compare_coins(client, "BTC,ETH,SOL")
    assert [c["symbol"] for c in result["coins"]] == ["BTC", "ETH", "SOL"]
    assert result["best_24h"] == "ETH"
    with pytest.raises(ValueError, match="2-5 symbols"):
        await t.compare_coins(client, "BTC")
    await client.close()


async def test_token_due_diligence_merges_sections():
    seen = []

    def handler(request):
        path = request.url.path
        seen.append(path)
        if path.endswith("/v1/dex/token"):
            return httpx.Response(
                200, json=_ok({"symbol": "PEPE", "name": "Pepe", "platform": "ethereum"})
            )
        if path.endswith("/v1/dex/security/detail"):
            return httpx.Response(200, json=_ok({"is_honeypot": False, "risk": "low"}))
        if path.endswith("/v1/dex/token/pools"):
            return httpx.Response(200, json=_ok([{"pair": "PEPE/WETH", "liquidity": 12345}]))
        if path.endswith("/v2/simple/price"):
            return httpx.Response(
                200, json=_ok({"PEPE": {"quote": {"USD": {"price": 0.00001}}}})
            )
        raise AssertionError(f"unexpected path {path}")

    client = CMCClient(transport=httpx.MockTransport(handler))
    result = await t.token_due_diligence(client, "ethereum", "0xabc")
    assert result["token"]["token"]["symbol"] == "PEPE"
    assert result["security"]["security"]["is_honeypot"] is False
    assert result["pools"]["pools"][0]["pair"] == "PEPE/WETH"
    assert result["price"]["prices"]["PEPE"]["price"] == 0.00001
    assert any(p.endswith("/v1/dex/token") for p in seen)
    await client.close()


async def test_token_due_diligence_degrades_when_price_missing():
    def handler(request):
        path = request.url.path
        if path.endswith("/v1/dex/token"):
            return httpx.Response(200, json=_ok({"name": "Unknown Token"}))  # no symbol
        if path.endswith("/v1/dex/security/detail"):
            return httpx.Response(200, json=_ok({"risk": "unknown"}))
        if path.endswith("/v1/dex/token/pools"):
            return httpx.Response(200, json=_ok([]))
        raise AssertionError(f"unexpected path {path}")

    client = CMCClient(transport=httpx.MockTransport(handler))
    result = await t.token_due_diligence(client, "solana", "0xabc")
    assert result["price"] is None  # no symbol -> no price call attempted
    await client.close()


async def test_market_brief_degrades_when_a_section_fails():
    def handler(request):
        path = request.url.path
        if path.endswith("/v1/global-metrics/quotes/latest"):
            return httpx.Response(200, json=_ok({"active_cryptocurrencies": 5, "quote": {"USD": {}}}))
        if path.endswith("/v3/fear-and-greed/latest"):
            return httpx.Response(200, json={"status": {"error_code": 1022, "error_message": "limit"}, "data": None})
        if path.endswith("/v3/index/cmc100-latest"):
            return httpx.Response(200, json=_ok({"value": 1}))
        if path.endswith("/v1/altcoin-season-index/latest"):
            return httpx.Response(200, json=_ok({"index": 50}))
        if path.endswith("/v3/cryptocurrency/listings/latest"):
            return httpx.Response(200, json=_ok([_listing("AAA", 5.0)]))
        raise AssertionError(f"unexpected path {path}")

    # Patch sleep so the 1022 backoff in the fear/greed call is instant.
    import asyncio

    orig_sleep = asyncio.sleep

    async def fake_sleep(delay):
        return None

    asyncio.sleep = fake_sleep  # type: ignore[assignment]
    try:
        client = CMCClient(transport=httpx.MockTransport(handler))
        brief = await t.market_brief(client)
        assert "_error" in brief["fear_greed"]  # failed section degrades, not crash
        assert brief["top_gainers_24h"][0]["symbol"] == "AAA"
        await client.close()
    finally:
        asyncio.sleep = orig_sleep
