"""Tests for the CMC client: keyless/keyed modes, 1022 backoff, keyed-only gate."""

import httpx
import pytest

from cmc_mcp.client import (
    KEYED_BASE,
    KEYLESS_BASE,
    CMCClient,
    CMCError,
    KeyRequiredError,
)


def _ok(data):
    return {"status": {"timestamp": "2026-11-19T00:00:00.000Z", "error_code": 0}, "data": data}


def _err(code, message):
    return {"status": {"error_code": code, "error_message": message}, "data": None}


def make_client(handler, api_key=None):
    return CMCClient(api_key=api_key, transport=httpx.MockTransport(handler))


async def test_keyless_uses_public_base_and_no_auth_header():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=_ok({"BTC": {"quote": {"USD": {"price": 63793.19}}}}))

    client = make_client(handler)
    assert client.keyless is True
    assert client.base_url == KEYLESS_BASE
    await client.simple_price("BTC")
    assert seen["url"].startswith(KEYLESS_BASE + "/v2/simple/price")
    assert "x-cmc_pro_api_key" not in seen["headers"]
    await client.close()


async def test_keyed_uses_keyed_base_and_sends_header():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=_ok({"BTC": {"quote": {"USD": {"price": 63793.19}}}}))

    client = make_client(handler, api_key="test-key-123")
    assert client.keyless is False
    assert client.base_url == KEYED_BASE
    await client.simple_price("BTC")
    assert seen["url"].startswith(KEYED_BASE + "/v2/simple/price")
    assert seen["headers"].get("x-cmc_pro_api_key") == "test-key-123"
    await client.close()


async def test_backoff_retries_1022_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(200, json=_err(1022, "You've reached the limit for anonymous access"))
        return httpx.Response(200, json=_ok({"BTC": {"quote": {"USD": {"price": 63793.19}}}}))

    client = make_client(handler)
    data = await client.simple_price("BTC")
    assert data["BTC"]["quote"]["USD"]["price"] == 63793.19
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff
    await client.close()


async def test_backoff_gives_up_after_retries_with_key_hint(monkeypatch):
    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    def handler(request):
        return httpx.Response(200, json=_err(1022, "You've reached the limit for anonymous access"))

    client = make_client(handler)
    with pytest.raises(CMCError, match="free API key"):
        await client.simple_price("BTC")
    await client.close()


async def test_http_429_retried(monkeypatch):
    calls = {"n": 0}

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json=_err(429, "Too many requests"))
        return httpx.Response(200, json=_ok({"BTC": {"quote": {"USD": {"price": 1.0}}}}))

    client = make_client(handler)
    await client.simple_price("BTC")
    assert calls["n"] == 2
    await client.close()


async def test_non_retryable_error_raises_immediately():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=_err(1002, "API key invalid"))

    client = make_client(handler, api_key="bad-key")
    with pytest.raises(CMCError, match="1002"):
        await client.simple_price("BTC")
    assert calls["n"] == 1
    await client.close()


async def test_string_error_code_zero_is_success():
    """Some endpoints return error_code as the string "0" — still success."""

    def handler(request):
        return httpx.Response(
            200,
            json={"status": {"error_code": "0", "error_message": ""}, "data": {"BTC": {"quote": {"USD": {"price": 63793.19}}}}},
        )

    client = make_client(handler)
    data = await client.simple_price("BTC")
    assert data["BTC"]["quote"]["USD"]["price"] == 63793.19
    await client.close()


async def test_string_error_code_1022_is_retried(monkeypatch):
    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    def handler(request):
        return httpx.Response(
            200,
            json={"status": {"error_code": "1022", "error_message": "limit"}, "data": None},
        )

    client = make_client(handler)
    with pytest.raises(CMCError, match="free API key"):
        await client.simple_price("BTC")
    await client.close()


async def test_trending_gainers_losers_keyed_only_error_in_keyless_mode():
    def handler(request):
        raise AssertionError("keyless mode must not make the HTTP call")

    client = make_client(handler)  # keyless
    with pytest.raises(KeyRequiredError, match="requires a CoinMarketCap API key"):
        await client.trending_gainers_losers()
    await client.close()


async def test_trending_gainers_losers_works_when_keyed():
    def handler(request):
        assert request.url.path.endswith("/v1/cryptocurrency/trending/gainers-losers")
        return httpx.Response(200, json=_ok([{"symbol": "BTC"}]))

    client = make_client(handler, api_key="test-key-123")
    data = await client.trending_gainers_losers()
    assert data == [{"symbol": "BTC"}]
    await client.close()
